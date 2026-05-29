# -*- coding: utf-8 -*-
"""
Entrenamiento del VAE para COLADA – Versión Definitiva
======================================================

Entrena un Autoencoder Variacional (VAE) sobre parches de terreno.
Incorpora soporte elegante para intercambiar la pérdida entre SSIM y Trimmed MSE,
ideal para resaltar anomalías (yacimientos/túmulos) según la morfología.

El flujo de entrenamiento incluye:
- Cálculo de percentiles globales para normalización robusta.
- Muestreo aleatorio de parches por época.
- Validación con parches estáticos.
- Early stopping y guardado del mejor modelo.
- Soporte para cancelación y callbacks de progreso.
"""

import os
import gc
import threading
import sys
import time
from typing import Dict, List, Optional, Callable, Tuple, Any
from collections import OrderedDict

import numpy as np
import torch
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import rasterio
from rasterio.windows import Window
from pytorch_msssim import ssim

from ...config import (
    VAE_IN_CHANNELS,
    VAE_LATENT_DIM,
    VAE_FEATURES,
    TAMANO_PARCHE,
    EPOCAS,
    BATCH_SIZE,
    LEARNING_RATE,
    K_TRIM,
    KL_WEIGHT,
    VAL_SPLIT,
    PATIENCE,
    USAR_GPU,
    SEED,
    PATHS_PER_EPOCH,
    MAX_CACHE_SIZE,
    NUM_WORKERS_DATALOADER,
    SSIM_DATA_RANGE,
    SSIM_SIZE_AVERAGE,
    CLIP_GRAD_NORM,
    VALIDATION_PATCHES_FACTOR,
    VALIDATION_PATCHES_MAX,
    PERCENTILES_LOW,
    PERCENTILES_HIGH,
    PERCENTILES_SAMPLES_PER_FILE,
)
from .vae import AutoencoderVariacional
from ...utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Funciones de pérdida
# ============================================================================

def ssim_loss(recon: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """
    Pérdida basada en SSIM (Structural Similarity Index).

    Args:
        recon: Tensor reconstruido (batch, C, H, W).
        target: Tensor original (batch, C, H, W).

    Returns:
        Valor de pérdida: 1 - SSIM.
    """
    ssim_val = ssim(
        recon,
        target,
        data_range=SSIM_DATA_RANGE,
        size_average=SSIM_SIZE_AVERAGE,
    )
    return 1.0 - ssim_val


def trimmed_mse_loss(recon: torch.Tensor, target: torch.Tensor, k: float = 0.10) -> torch.Tensor:
    """
    Trimmed Mean Squared Error.
    Recorta el K% de los píxeles con mayor error (los peores reconstruidos)
    para que la red no intente aprender a reconstruir las anomalías arqueológicas.

    Args:
        recon: Tensor reconstruido (batch, C, H, W).
        target: Tensor original (batch, C, H, W).
        k: Fracción de píxeles a recortar (0.02 = 2%).

    Returns:
        Pérdida MSE promedio sobre el (1-K)% de píxeles con menor error.
    """
    mse = (recon - target) ** 2
    flat = mse.view(mse.size(0), -1)
    sorted_flat, _ = torch.sort(flat, dim=1)

    # Nos quedamos con el (1-K)% de los píxeles que mejor se reconstruyen
    trim_idx = int(sorted_flat.size(1) * (1.0 - k))
    if trim_idx == 0:
        trim_idx = 1

    trimmed = sorted_flat[:, :trim_idx]
    return trimmed.mean()


# ============================================================================
# Cálculo de percentiles globales
# ============================================================================

def calcular_percentiles_globales(
    archivos: List[str],
    in_channels: int,
    low_perc: float = PERCENTILES_LOW,
    high_perc: float = PERCENTILES_HIGH,
    samples_per_file: int = PERCENTILES_SAMPLES_PER_FILE,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Dict[str, np.ndarray]:
    """
    Calcula los percentiles globales (P1 y P99) por banda a partir de una muestra
    aleatoria de píxeles de todos los archivos.

    Args:
        archivos: Lista de rutas a archivos GeoTIFF.
        in_channels: Número esperado de bandas.
        low_perc: Percentil inferior (default 1.0).
        high_perc: Percentil superior (default 99.0).
        samples_per_file: Número de píxeles a muestrear por archivo.
        progress_callback: Función opcional para reportar progreso.

    Returns:
        Diccionario con arrays 'p1' y 'p99' de forma (in_channels,).

    Raises:
        RuntimeError: Si no hay archivos válidos.
    """
    all_data = [[] for _ in range(in_channels)]
    total = len(archivos)
    omitidos = 0

    for i, archivo in enumerate(archivos):
        if progress_callback:
            progress_callback(f"Percentiles {i+1}/{total}", int((i + 1) / total * 50))

        try:
            path = os.path.normpath(archivo).replace("\\", "/")
            with rasterio.open(path) as src:
                if src.count < in_channels:
                    omitidos += 1
                    continue

                cols, rows = src.width, src.height
                total_pixels = cols * rows
                n = min(samples_per_file, total_pixels)
                # Muestreo aleatorio de índices de píxeles
                indices = np.random.choice(total_pixels, size=n, replace=False)
                cols_idx = indices % cols
                rows_idx = indices // cols

                # Leer por bandas y filas agrupadas para eficiencia
                for b in range(1, in_channels + 1):
                    valores = []
                    # Agrupar por fila para leer ventanas completas
                    for f in np.unique(rows_idx):
                        mask_fila = rows_idx == f
                        en_fila = cols_idx[mask_fila]
                        if len(en_fila) == 0:
                            continue
                        x0 = en_fila.min()
                        ancho = en_fila.max() - x0 + 1
                        window = Window(x0, f, ancho, 1)
                        data = src.read(b, window=window)
                        if data.size > 0:
                            idx_rel = en_fila - x0
                            valores.append(data.ravel()[idx_rel])
                    if valores:
                        all_data[b - 1].append(np.concatenate(valores))

        except Exception as e:
            logger.warning(f"Error procesando {archivo} para percentiles: {e}")
            omitidos += 1
            continue

    if total - omitidos == 0:
        raise RuntimeError("Ningún archivo válido para calcular percentiles")

    p1 = np.zeros(in_channels, dtype=np.float32)
    p99 = np.zeros(in_channels, dtype=np.float32)

    for c in range(in_channels):
        if all_data[c]:
            cat = np.concatenate(all_data[c])
            p1[c] = np.percentile(cat, low_perc)
            p99[c] = np.percentile(cat, high_perc)
        else:
            p1[c] = 0.0
            p99[c] = 1.0

    if progress_callback:
        progress_callback("Percentiles calculados", 50)

    return {"p1": p1, "p99": p99}


# ============================================================================
# Dataset de parches de terreno
# ============================================================================

class TerrainPatchDataset(Dataset):
    """
    Dataset que muestrea parches aleatorios de stacks GeoTIFF.
    Soporta caché LRU de datasets abiertos, normalización por percentiles
    y aumentación de datos (rotación, volteo).
    """

    def __init__(
        self,
        archivos: List[str],
        patch_size: int = TAMANO_PARCHE,
        patches_per_epoch: int = PATHS_PER_EPOCH,
        max_cache_size: int = MAX_CACHE_SIZE,
        random_state: Optional[np.random.RandomState] = None,
        norm_params: Optional[Dict[str, np.ndarray]] = None,
        expected_channels: Optional[int] = None,
        training: bool = True,
    ) -> None:
        """
        Args:
            archivos: Lista de rutas a archivos GeoTIFF válidos.
            patch_size: Tamaño del parche cuadrado en píxeles.
            patches_per_epoch: Número de parches a muestrear por época.
            max_cache_size: Número máximo de archivos abiertos en caché.
            random_state: Generador de números aleatorios (para reproducibilidad).
            norm_params: Diccionario con 'p1' y 'p99' para normalización.
            expected_channels: Número esperado de bandas.
            training: Si es True, aplica aumentación de datos.
        """
        self.patch_size = patch_size
        self.samples = patches_per_epoch
        self.max_cache = max_cache_size
        self.rng = random_state or np.random
        self.norm = norm_params
        self.expected_channels = expected_channels
        self.training = training

        # Filtrar archivos que cumplen requisitos
        self.archivos: List[str] = []
        for f in archivos:
            path = os.path.normpath(f).replace("\\", "/")
            try:
                with rasterio.open(path) as src:
                    if src.count != expected_channels or src.width < patch_size or src.height < patch_size:
                        continue
                self.archivos.append(path)
            except Exception:
                continue

        if not self.archivos:
            raise RuntimeError("Ningún archivo tiene el tamaño o número de bandas adecuado")

        self._cache: OrderedDict[str, rasterio.DatasetReader] = OrderedDict()

    def __len__(self) -> int:
        return self.samples

    def _load(self, path: str) -> Optional[rasterio.DatasetReader]:
        """Carga un dataset con caché LRU."""
        path = os.path.normpath(path).replace("\\", "/")
        if path in self._cache:
            self._cache.move_to_end(path)
            return self._cache[path]

        try:
            src = rasterio.open(path)
            if len(self._cache) >= self.max_cache:
                oldest, _ = self._cache.popitem(last=False)
                try:
                    self._cache[oldest].close()
                except Exception:
                    pass
            self._cache[path] = src
            return src
        except Exception:
            return None

    def _apply_augmentation(self, parche: torch.Tensor) -> torch.Tensor:
        """Aplica rotaciones y volteos aleatorios."""
        if not self.training:
            return parche

        k = self.rng.randint(0, 4)
        if k > 0:
            parche = torch.rot90(parche, k, dims=[1, 2])
        if self.rng.rand() > 0.5:
            parche = torch.flip(parche, dims=[2])
        if self.rng.rand() > 0.5:
            parche = torch.flip(parche, dims=[1])
        return parche

    def _normalizar(self, parche: np.ndarray) -> np.ndarray:
        """Normaliza el parche usando percentiles globales o locales."""
        if self.norm is not None:
            p1 = self.norm["p1"]
            p99 = self.norm["p99"]
            denom = p99 - p1
            denom[denom < 1e-8] = 1.0
            for c in range(parche.shape[0]):
                parche[c] = (parche[c] - p1[c]) / denom[c]
            return np.clip(parche, 0.0, 1.0)
        else:
            # Normalización local por banda
            for c in range(parche.shape[0]):
                pmin, pmax = parche[c].min(), parche[c].max()
                if pmax - pmin > 1e-8:
                    parche[c] = (parche[c] - pmin) / (pmax - pmin)
                else:
                    parche[c] = 0.0
            return parche

    def __getitem__(self, idx: int) -> torch.Tensor:
        """Devuelve un parche aleatorio normalizado y aumentado."""
        for _ in range(10):
            f = self.rng.choice(self.archivos)
            src = self._load(f)
            if src is None:
                continue

            try:
                h, w = src.height, src.width
                y = self.rng.randint(0, max(1, h - self.patch_size + 1))
                x = self.rng.randint(0, max(1, w - self.patch_size + 1))
                window = Window(x, y, self.patch_size, self.patch_size)
                parche = src.read(window=window).astype(np.float32)
            except Exception:
                # Si falla, eliminar de caché y de la lista
                if f in self._cache:
                    del self._cache[f]
                if f in self.archivos:
                    self.archivos.remove(f)
                continue

            if parche.shape[0] != self.expected_channels:
                continue

            parche = self._normalizar(parche)
            parche_tensor = torch.from_numpy(parche)
            return self._apply_augmentation(parche_tensor)

        raise RuntimeError("Imposible obtener un parche después de varios reintentos")

    def clear_cache(self) -> None:
        """Cierra y libera todos los datasets en caché."""
        for src in self._cache.values():
            try:
                src.close()
            except Exception:
                pass
        self._cache.clear()


# ============================================================================
# Generación de parches de validación
# ============================================================================

def generar_parches_validacion(
    val_files: List[str],
    patch_size: int,
    n_patches: int,
    seed: int,
    norm_params: Optional[Dict] = None,
    expected_channels: Optional[int] = None,
) -> torch.Tensor:
    """
    Genera un conjunto fijo de parches de validación para evaluar el modelo
    de forma consistente entre épocas.

    Args:
        val_files: Lista de archivos de validación.
        patch_size: Tamaño del parche.
        n_patches: Número de parches a generar.
        seed: Semilla para reproducibilidad.
        norm_params: Parámetros de normalización.
        expected_channels: Número de bandas esperado.

    Returns:
        Tensor de forma (n_patches, channels, patch_size, patch_size).
    """
    rng = np.random.RandomState(seed)
    dataset = TerrainPatchDataset(
        val_files,
        patch_size=patch_size,
        patches_per_epoch=n_patches,
        max_cache_size=min(len(val_files), MAX_CACHE_SIZE),
        random_state=rng,
        norm_params=norm_params,
        expected_channels=expected_channels,
        training=False,
    )
    parches = []
    for i in range(n_patches):
        try:
            parches.append(dataset[i])
        except Exception:
            parches.append(torch.zeros((expected_channels, patch_size, patch_size)))
    return torch.stack(parches)


# ============================================================================
# Función principal de entrenamiento
# ============================================================================

def entrenar_vae(
    lista_archivos: List[str],
    params_modelo: Optional[Dict[str, Any]] = None,
    hiperparams: Optional[Dict[str, Any]] = None,
    ruta_salida: str = "modelo_colada.pth",
    dispositivo: Optional[str] = None,
    callback_progreso: Optional[Callable[[int, int, float, float], None]] = None,
    callback_preparacion: Optional[Callable[[str, int], None]] = None,
    callback_batch: Optional[Callable[[int, int, int, float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    seed: int = SEED,
) -> bool:
    """
    Entrena un VAE con los parámetros especificados.

    Args:
        lista_archivos: Lista de rutas a archivos GeoTIFF de entrenamiento.
        params_modelo: Diccionario con parámetros de arquitectura del VAE.
        hiperparams: Diccionario con hiperparámetros de entrenamiento.
        ruta_salida: Ruta donde guardar el modelo entrenado.
        dispositivo: 'cpu', 'cuda' o None (auto-detectar).
        callback_progreso: Función llamada al final de cada época (epoch, total, train_loss, val_loss).
        callback_preparacion: Función llamada durante la preparación (mensaje, porcentaje).
        callback_batch: Función llamada cada cierto número de batches (epoch, batch, total, loss).
        cancel_event: Evento que indica si se debe cancelar el entrenamiento.
        seed: Semilla para reproducibilidad.

    Returns:
        True si el entrenamiento se completó con éxito, False si fue cancelado o falló.
    """
    if params_modelo is None:
        params_modelo = {}
    if hiperparams is None:
        hiperparams = {}

    # Extraer parámetros del modelo
    in_channels = params_modelo.get("in_channels", VAE_IN_CHANNELS)
    latent_dim = params_modelo.get("latent_dim", VAE_LATENT_DIM)
    features = params_modelo.get("features", VAE_FEATURES)
    patch_size = params_modelo.get("tamanio_parche", TAMANO_PARCHE)

    # Extraer hiperparámetros
    epochs = hiperparams.get("epocas", EPOCAS)
    batch_size = hiperparams.get("batch_size", BATCH_SIZE)
    lr = hiperparams.get("learning_rate", LEARNING_RATE)
    kl_weight = hiperparams.get("kl_weight", KL_WEIGHT)
    val_split = hiperparams.get("val_split", VAL_SPLIT)
    patience = hiperparams.get("patience", PATIENCE)
    patches_per_epoch = hiperparams.get("patches_per_epoch", PATHS_PER_EPOCH)
    max_cache = hiperparams.get("max_cache_size", MAX_CACHE_SIZE)
    loss_fn_type = hiperparams.get("loss_function", "ssim").lower()
    k_trim = hiperparams.get("k_trim", K_TRIM)

    # Configurar DataLoader (0 workers en Windows por estabilidad)
    num_workers = 0 if sys.platform == "win32" else NUM_WORKERS_DATALOADER

    # Configurar dispositivo y precisión mixta
    dev = torch.device(dispositivo or ("cuda" if USAR_GPU and torch.cuda.is_available() else "cpu"))
    use_amp = (dev.type == "cuda")
    scaler = torch.cuda.amp.GradScaler() if use_amp else None

    if dev.type == "cuda":
        torch.backends.cudnn.benchmark = True

    # Fijar semillas
    torch.manual_seed(seed)
    np.random.seed(seed)

    # Normalizar rutas
    lista_archivos = [os.path.normpath(f).replace("\\", "/") for f in lista_archivos]

    # ---- Fase de preparación: percentiles ----
    if callback_preparacion:
        callback_preparacion("Calculando percentiles globales...", 0)

    norm_params = calcular_percentiles_globales(
        lista_archivos,
        in_channels,
        progress_callback=callback_preparacion
    )

    # ---- División entrenamiento/validación ----
    if callback_preparacion:
        callback_preparacion("Estructurando partición de datos...", 55)

    rng = np.random.RandomState(seed)
    indices = rng.permutation(len(lista_archivos))
    n_val = max(1, int(len(lista_archivos) * val_split))
    val_files = [lista_archivos[i] for i in indices[:n_val]]
    train_files = [lista_archivos[i] for i in indices[n_val:]]

    # ---- Dataset y DataLoader de entrenamiento ----
    if callback_preparacion:
        callback_preparacion("Iniciando DataLoader de entrenamiento...", 60)

    train_dataset = TerrainPatchDataset(
        train_files,
        patch_size=patch_size,
        patches_per_epoch=patches_per_epoch,
        max_cache_size=max_cache,
        random_state=np.random.RandomState(seed),
        norm_params=norm_params,
        expected_channels=in_channels,
        training=True,
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        drop_last=True,
        num_workers=num_workers,
        pin_memory=(dev.type == "cuda"),
    )
    total_batches = len(train_loader)

    # ---- Parches de validación estáticos ----
    n_val_patches = min(int(patches_per_epoch * VALIDATION_PATCHES_FACTOR), VALIDATION_PATCHES_MAX)
    if callback_preparacion:
        callback_preparacion("Reservando parches estáticos de validación...", 65)

    try:
        val_patches = generar_parches_validacion(
            val_files,
            patch_size=patch_size,
            n_patches=n_val_patches,
            seed=seed + 1,
            norm_params=norm_params,
            expected_channels=in_channels,
        ).to(dev)
    except Exception as e:
        logger.error(f"Fallo en generación de validación: {e}")
        raise

    # ---- Crear modelo y optimizador ----
    if callback_preparacion:
        callback_preparacion("Inicializando modelo VAE...", 80)

    modelo = AutoencoderVariacional(
        in_channels=in_channels,
        latent_dim=latent_dim,
        features=features,
        tamanio_parche=patch_size,
    ).to(dev)
    optimizer = optim.Adam(modelo.parameters(), lr=lr)

    # ---- Bucle de entrenamiento ----
    best_val_loss = float("inf")
    epochs_no_improve = 0

    if callback_preparacion:
        callback_preparacion("Arrancando iteraciones de aprendizaje...", 85)

    for epoch in range(1, epochs + 1):
        if cancel_event and cancel_event.is_set():
            return False

        modelo.train()
        train_dataset.clear_cache()
        epoch_loss = 0.0
        n_batches = 0

        for batch_idx, batch in enumerate(train_loader):
            if cancel_event and cancel_event.is_set():
                return False

            batch = batch.to(dev)

            if use_amp:
                with torch.cuda.amp.autocast():
                    recon, mu, logvar = modelo(batch)
                    if loss_fn_type == "mse":
                        loss_rec = trimmed_mse_loss(recon, batch, k=k_trim)
                    else:
                        loss_rec = ssim_loss(recon, batch)
                    kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / batch.size(0)
                    loss = loss_rec + kl_weight * kl_loss

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(modelo.parameters(), CLIP_GRAD_NORM)
                scaler.step(optimizer)
                scaler.update()
            else:
                recon, mu, logvar = modelo(batch)
                if loss_fn_type == "mse":
                    loss_rec = trimmed_mse_loss(recon, batch, k=k_trim)
                else:
                    loss_rec = ssim_loss(recon, batch)
                kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / batch.size(0)
                loss = loss_rec + kl_weight * kl_loss
                loss.backward()
                torch.nn.utils.clip_grad_norm_(modelo.parameters(), CLIP_GRAD_NORM)
                optimizer.step()

            optimizer.zero_grad()
            epoch_loss += loss.item()
            n_batches += 1

            if callback_batch and (batch_idx % 10 == 0 or batch_idx == total_batches - 1):
                callback_batch(epoch, batch_idx + 1, total_batches, loss.item())

        epoch_loss /= max(1, n_batches)

        # ---- Validación ----
        modelo.eval()
        val_loss = 0.0
        n_val_batches = 0

        with torch.no_grad():
            for i in range(0, len(val_patches), batch_size):
                x = val_patches[i:i + batch_size]
                if use_amp:
                    with torch.cuda.amp.autocast():
                        recon, mu, logvar = modelo(x)
                        if loss_fn_type == "mse":
                            loss_rec = trimmed_mse_loss(recon, x, k=k_trim)
                        else:
                            loss_rec = ssim_loss(recon, x)
                        kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / x.size(0)
                        val_loss += (loss_rec + kl_weight * kl_loss).item()
                else:
                    recon, mu, logvar = modelo(x)
                    if loss_fn_type == "mse":
                        loss_rec = trimmed_mse_loss(recon, x, k=k_trim)
                    else:
                        loss_rec = ssim_loss(recon, x)
                    kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / x.size(0)
                    val_loss += (loss_rec + kl_weight * kl_loss).item()
                n_val_batches += 1

        val_loss /= max(1, n_val_batches)

        # ---- Callback de progreso ----
        if callback_progreso:
            callback_progreso(epoch, epochs, epoch_loss, val_loss)

        # ---- Early stopping y guardado ----
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_no_improve = 0
            torch.save(
                {
                    "model_params": {
                        "in_channels": in_channels,
                        "latent_dim": latent_dim,
                        "features": features,
                        "tamanio_parche": patch_size,
                    },
                    "state_dict": modelo.state_dict(),
                    "norm_params": norm_params,
                },
                ruta_salida,
            )
            logger.info(f"Época {epoch}: nueva mejor pérdida de validación = {val_loss:.6f}")
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                logger.info(f"Early stopping en época {epoch} tras {patience} épocas sin mejora")
                break

        # ---- Limpieza de memoria ----
        gc.collect()
        if dev.type == "cuda":
            torch.cuda.empty_cache()

    return True