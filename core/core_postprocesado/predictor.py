# -*- coding: utf-8 -*-
"""
Predictor de anomalías para COLADA – VAE e Isolation Forest
============================================================

Proporciona funciones para:
- Cargar modelos VAE entrenados.
- Leer stacks multibanda GeoTIFF.
- Extraer parches con solapamiento.
- Inferir mapas de anomalía mediante VAE.
- Suavizado y umbralizado adaptativo.
- Guardado de rasters y vectorización de anomalías.
- Predicción con Isolation Forest (aprendizaje sin etiquetas).
"""

import os
import threading
import gc
import numpy as np
import torch
import rasterio
from scipy.ndimage import gaussian_filter
from typing import Tuple, Optional, Dict, List, Callable, Any, Generator

from ...config import (
    TAMANO_PARCHE,
    SOLAPAMIENTO,
    SIGMA_GAUSSIANO,
    UMBRAL_PERCENTIL,
    TAMANIO_LOTE,
    VAE_IN_CHANNELS,
    VAE_LATENT_DIM,
    VAE_FEATURES,
    USAR_GPU,
    VENTANA_ADAPTATIVA,
    ASPECT_RATIO_MAX,
    CIRCULARITY_MIN,
    MIN_AREA_ANOMALIA_M2,
    ISOLATION_FOREST_N_ESTIMATORS,
    ISOLATION_FOREST_CONTAMINATION,
    ISOLATION_FOREST_MAX_SAMPLES,
)
from .vae import AutoencoderVariacional
from ...utils.logging import get_logger

logger = get_logger('Colada')


# ============================================================================
# Utilidades de dispositivo
# ============================================================================

def _get_device(dispositivo: Optional[str] = None) -> torch.device:
    """
    Determina el dispositivo de ejecución (CPU/CUDA).

    Args:
        dispositivo: 'cpu', 'cuda' o None. Si es None, auto-detectar.

    Returns:
        Dispositivo torch.
    """
    if dispositivo is None:
        dispositivo = "cuda" if USAR_GPU and torch.cuda.is_available() else "cpu"
    dispositivo = dispositivo.strip().lower()
    if "cuda" in dispositivo and not torch.cuda.is_available():
        logger.warning("NVIDIA CUDA no detectado, cambiando a CPU")
        dispositivo = "cpu"
    return torch.device(dispositivo)


# ============================================================================
# Carga de modelo VAE
# ============================================================================

def cargar_modelo_vae(
    ruta: str,
    dispositivo: Optional[str] = None
) -> Tuple[AutoencoderVariacional, Tuple[int, int, int, int], Optional[Dict[str, np.ndarray]]]:
    """
    Carga un modelo VAE entrenado desde un archivo .pth.

    Args:
        ruta: Ruta al archivo del modelo.
        dispositivo: 'cpu', 'cuda' o None (auto).

    Returns:
        Tupla (modelo, meta, norm_params) donde meta es (in_channels, latent_dim, features, tamanio_parche).
    """
    dev = _get_device(dispositivo)
    checkpoint = torch.load(ruta, map_location="cpu", weights_only=False)

    if "model_params" in checkpoint:
        meta = checkpoint["model_params"]
        state = checkpoint["state_dict"]
    else:
        logger.warning("Cargando arquitectura legacy (sin model_params)")
        meta = {
            "in_channels": VAE_IN_CHANNELS,
            "latent_dim": VAE_LATENT_DIM,
            "features": VAE_FEATURES,
            "tamanio_parche": TAMANO_PARCHE,
        }
        state = checkpoint

    norm_params = checkpoint.get("norm_params", None)
    modelo = AutoencoderVariacional(**meta)
    modelo.load_state_dict(state)
    modelo.to(dev)
    modelo.eval()

    meta_tuple = (meta["in_channels"], meta["latent_dim"], meta["features"], meta["tamanio_parche"])
    return modelo, meta_tuple, norm_params


# ============================================================================
# Lectura de stacks multibanda
# ============================================================================

def leer_stack_multibanda(
    ruta: str,
    expected_channels: Optional[int] = None
) -> Tuple[np.ndarray, Tuple[float, float, float, float, float, float], Tuple[int, int], str]:
    """
    Lee un GeoTIFF multibanda y devuelve información geoespacial.

    Args:
        ruta: Ruta al archivo GeoTIFF.
        expected_channels: Número esperado de bandas (opcional). Si se proporciona,
                           se truncan las bandas sobrantes.

    Returns:
        Tupla (array, geotransform, (ancho, alto), proyección_wkt)
    """
    with rasterio.open(ruta) as src:
        arr = src.read()  # shape (bandas, alto, ancho)
        geotrans = src.transform
        crs = src.crs

    if arr.ndim == 2:
        arr = np.expand_dims(arr, 0)

    if expected_channels is not None and arr.shape[0] > expected_channels:
        arr = arr[:expected_channels, :, :]
        logger.debug(f"Truncadas bandas a {expected_channels}")

    # Tupla geotransform en formato (xmin, res_x, rot_x, ymax, rot_y, -res_y)
    geotrans_tuple = (geotrans.c, geotrans.a, geotrans.b, geotrans.f, geotrans.d, geotrans.e)
    return arr, geotrans_tuple, (src.width, src.height), crs.to_wkt()


# ============================================================================
# Extracción de parches con solapamiento (generador)
# ============================================================================

def extraer_parches_generator(
    imagen: np.ndarray,
    tamanio: int = TAMANO_PARCHE,
    solape: int = SOLAPAMIENTO,
    norm_params: Optional[Dict[str, np.ndarray]] = None,
) -> Generator[Tuple[np.ndarray, Tuple[int, int], int, int], None, None]:
    """
    Generador que extrae parches deslizantes de una imagen multibanda.

    Args:
        imagen: Array (canales, alto, ancho).
        tamanio: Tamaño del parche en píxeles.
        solape: Solapamiento entre parches en píxeles.
        norm_params: Parámetros de normalización (p1, p99) para estandarizar.

    Yields:
        Tupla (parche_normalizado, (fila_inicio, col_inicio), idx, total_parches)
    """
    canales, filas, cols = imagen.shape
    paso = tamanio - solape
    if paso <= 0:
        paso = 1

    inicios_y = list(range(0, filas - tamanio + 1, paso))
    if not inicios_y or inicios_y[-1] != filas - tamanio:
        inicios_y.append(filas - tamanio)

    inicios_x = list(range(0, cols - tamanio + 1, paso))
    if not inicios_x or inicios_x[-1] != cols - tamanio:
        inicios_x.append(cols - tamanio)

    total = len(inicios_y) * len(inicios_x)
    idx = 0

    for y in inicios_y:
        for x in inicios_x:
            idx += 1
            parche = imagen[:, y:y + tamanio, x:x + tamanio].astype(np.float32)

            # Normalización por percentiles globales
            if norm_params is not None:
                p1 = norm_params["p1"]
                p99 = norm_params["p99"]
                denom = p99 - p1
                denom[denom < 1e-8] = 1.0
                for c in range(parche.shape[0]):
                    parche[c] = (parche[c] - p1[c]) / denom[c]
                parche = np.clip(parche, 0.0, 1.0)
            else:
                # Normalización local por banda
                for c in range(parche.shape[0]):
                    pmin, pmax = parche[c].min(), parche[c].max()
                    if pmax - pmin > 1e-8:
                        parche[c] = (parche[c] - pmin) / (pmax - pmin)
                    else:
                        parche[c] = 0.0

            yield parche, (y, x), idx, total


# ============================================================================
# Inferencia VAE (reconstrucción y mapa de error)
# ============================================================================

def inferir_y_reconstruir(
    modelo: AutoencoderVariacional,
    parches_gen: Generator,
    dimensiones: Tuple[int, int],
    dispositivo: Optional[str] = None,
    tamanio_lote: int = TAMANIO_LOTE,
    callback: Optional[Callable[[int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> np.ndarray:
    """
    Ejecuta la inferencia del VAE sobre los parches y genera un mapa de error medio.

    Args:
        modelo: Modelo VAE cargado.
        parches_gen: Generador de parches (extraer_parches_generator).
        dimensiones: (alto, ancho) de la imagen original.
        dispositivo: Dispositivo de cómputo.
        tamanio_lote: Tamaño de lote para la inferencia.
        callback: Función llamada con el porcentaje de progreso.
        cancel_event: Evento para cancelación temprana.

    Returns:
        Mapa de error (alto, ancho) en float32.

    Raises:
        InterruptedError: Si se cancela.
    """
    dev = _get_device(dispositivo)
    filas_img, cols_img = dimensiones
    mapa = np.zeros((filas_img, cols_img), dtype=np.float32)
    contador = np.zeros((filas_img, cols_img), dtype=np.float32)
    modelo.to(dev)

    lote_parches = []
    lote_coords = []
    ultimo_prog = 0
    total_patches = None

    for patch, (y, x), idx, total in parches_gen:
        if cancel_event and cancel_event.is_set():
            raise InterruptedError()

        if total_patches is None:
            total_patches = total

        lote_parches.append(patch)
        lote_coords.append((y, x))

        if len(lote_parches) >= tamanio_lote:
            batch = torch.from_numpy(np.stack(lote_parches)).float().to(dev)
            with torch.inference_mode():
                recon, _, _ = modelo(batch)
            errores = torch.abs(batch - recon).mean(dim=1).cpu().numpy()

            for k, (yy, xx) in enumerate(lote_coords):
                h, w = lote_parches[k].shape[1], lote_parches[k].shape[2]
                mapa[yy:yy + h, xx:xx + w] += errores[k][:h, :w]
                contador[yy:yy + h, xx:xx + w] += 1.0

            if callback and total_patches:
                prog = int(idx / total_patches * 100)
                if prog > ultimo_prog:
                    callback(prog)
                    ultimo_prog = prog

            lote_parches.clear()
            lote_coords.clear()

    # Último lote
    if lote_parches:
        batch = torch.from_numpy(np.stack(lote_parches)).float().to(dev)
        with torch.inference_mode():
            recon, _, _ = modelo(batch)
        errores = torch.abs(batch - recon).mean(dim=1).cpu().numpy()
        for k, (yy, xx) in enumerate(lote_coords):
            h, w = lote_parches[k].shape[1], lote_parches[k].shape[2]
            mapa[yy:yy + h, xx:xx + w] += errores[k][:h, :w]
            contador[yy:yy + h, xx:xx + w] += 1.0

    # Promedio
    contador[contador == 0] = 1.0
    mapa /= contador

    if callback:
        callback(100)

    return mapa


# ============================================================================
# Suavizado y umbralización adaptativa
# ============================================================================

def suavizar_y_umbralizar(
    mapa: np.ndarray,
    sigma: float = SIGMA_GAUSSIANO,
    umbral_pct: float = UMBRAL_PERCENTIL,
    ventana_adaptativa: int = VENTANA_ADAPTATIVA,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Aplica suavizado gaussiano y umbralización (global o adaptativa) al mapa de anomalías.

    Args:
        mapa: Mapa de anomalías (alto, ancho).
        sigma: Sigma del filtro gaussiano.
        umbral_pct: Percentil para umbralización global (si ventana_adaptativa <= 0).
        ventana_adaptativa: Tamaño de ventana para umbral adaptativo (en píxeles).
                             Si <= 0, usa umbral global.

    Returns:
        (mapa_suave, mapa_binario) donde binario es uint8 (0/1).
    """
    suave = gaussian_filter(mapa, sigma=sigma)

    if ventana_adaptativa > 0:
        from scipy.interpolate import RegularGridInterpolator

        filas, cols = suave.shape
        paso = ventana_adaptativa
        y_blocks = list(range(0, filas, paso))
        x_blocks = list(range(0, cols, paso))

        umbrales = np.zeros((len(y_blocks), len(x_blocks)), dtype=np.float32)
        for i, y0 in enumerate(y_blocks):
            y1 = min(y0 + paso, filas)
            for j, x0 in enumerate(x_blocks):
                x1 = min(x0 + paso, cols)
                bloque = suave[y0:y1, x0:x1]
                if bloque.size > 0:
                    umbrales[i, j] = np.percentile(bloque, umbral_pct)

        # Interpolar para obtener umbral por píxel
        y_centers = np.array(y_blocks, dtype=np.float32) + paso / 2
        x_centers = np.array(x_blocks, dtype=np.float32) + paso / 2
        interp = RegularGridInterpolator(
            (y_centers, x_centers),
            umbrales,
            bounds_error=False,
            fill_value=np.percentile(suave, umbral_pct)
        )
        yy, xx = np.mgrid[0:filas, 0:cols].astype(np.float32)
        umbral_mapa = interp((yy, xx))
        binario = (suave >= umbral_mapa).astype(np.uint8)
    else:
        umbral = np.percentile(suave, umbral_pct)
        binario = (suave >= umbral).astype(np.uint8)

    return suave, binario


# ============================================================================
# Guardado de ráster con colormap
# ============================================================================

def guardar_raster(
    matriz: np.ndarray,
    ruta: str,
    geotransform: Tuple[float, float, float, float, float, float],
    proyeccion: str,
    columnas: int,
    filas: int,
) -> None:
    """
    Guarda una matriz (float32) como GeoTIFF de 8 bits con colormap térmico.

    Args:
        matriz: Array 2D (float32) con el mapa de anomalías.
        ruta: Ruta de salida.
        geotransform: GeoTransform en formato (xmin, res_x, rot_x, ymax, rot_y, -res_y).
        proyeccion: WKT de la proyección.
        columnas: Número de columnas (ancho).
        filas: Número de filas (alto).
    """
    # Normalizar a 0-255
    min_val, max_val = matriz.min(), matriz.max()
    if max_val - min_val > 1e-8:
        matriz_norm = (255 * (matriz - min_val) / (max_val - min_val)).astype(np.uint8)
    else:
        matriz_norm = np.zeros_like(matriz, dtype=np.uint8)

    # Colormap térmico (azul -> cian -> verde -> amarillo -> rojo)
    colormap = {}
    for i in range(256):
        t = i / 255.0
        if t < 0.25:
            r, g, b = 0, int(255 * (t * 4)), int(128 + 127 * (t * 4))
        elif t < 0.5:
            t2 = (t - 0.25) * 4
            r, g, b = int(255 * t2), 255, int(255 - 255 * t2)
        elif t < 0.75:
            t2 = (t - 0.5) * 4
            r, g, b = 255, int(255 - 255 * t2), 0
        else:
            r, g, b = 255, 0, 0
        colormap[i] = (r, g, b, 255)

    # Transformar GeoTransform a formato from_origin
    transform = rasterio.transform.from_origin(
        geotransform[0], geotransform[3], geotransform[1], abs(geotransform[5])
    )

    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=filas,
        width=columnas,
        count=1,
        dtype=np.uint8,
        crs=proyeccion,
        transform=transform,
        compress="lzw",
    ) as dst:
        dst.write(matriz_norm, 1)
        dst.write_colormap(1, colormap)


# ============================================================================
# Vectorización de anomalías (polígonos)
# ============================================================================

def vectorizar_anomalias(
    binario: np.ndarray,
    ruta: str,
    geotransform: Tuple[float, float, float, float, float, float],
    proyeccion: str,
    min_area_m2: float,
    aspect_ratio_max: float,
    circularity_min: float,
) -> None:
    """
    Convierte un ráster binario (0/1) en polígonos GeoJSON, filtrando por área,
    relación de aspecto y circularidad.

    Args:
        binario: Array 2D uint8 (0 fondo, 1 anomalía).
        ruta: Ruta de salida del GeoJSON.
        geotransform: GeoTransform de origen.
        proyeccion: WKT de la proyección.
        min_area_m2: Área mínima en metros cuadrados.
        aspect_ratio_max: Relación de aspecto máxima (ancho/alto). 0 = desactivado.
        circularity_min: Circularidad mínima (4π·Área/Perímetro²). 0 = desactivado.
    """
    from osgeo import gdal, ogr, osr

    # Crear dataset en memoria
    mem_drv = gdal.GetDriverByName("MEM")
    ds_mem = mem_drv.Create("", binario.shape[1], binario.shape[0], 1, gdal.GDT_Byte)
    ds_mem.SetGeoTransform(geotransform)
    ds_mem.SetProjection(proyeccion)
    ds_mem.GetRasterBand(1).WriteArray(binario)

    # Crear capa vectorial de salida
    driver = ogr.GetDriverByName("GeoJSON")
    ds_out = driver.CreateDataSource(ruta)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proyeccion)
    capa = ds_out.CreateLayer("candidatos", srs, ogr.wkbPolygon)

    # Crear campos
    for f_name, f_type in [
        ("id", ogr.OFTInteger),
        ("area_m2", ogr.OFTReal),
        ("aspect_ratio", ogr.OFTReal),
        ("circularity", ogr.OFTReal),
    ]:
        capa.CreateField(ogr.FieldDefn(f_name, f_type))

    # Poligonizar
    gdal.Polygonize(ds_mem.GetRasterBand(1), None, capa, 0, [], callback=None)

    # Filtrar polígonos
    for feature in capa:
        geom = feature.GetGeometryRef()
        if geom is None:
            capa.DeleteFeature(feature.GetFID())
            continue

        area = geom.Area()
        if area < min_area_m2:
            capa.DeleteFeature(feature.GetFID())
            continue

        aspecto = 1.0
        if aspect_ratio_max > 0:
            bbox = geom.GetEnvelope()
            dx = bbox[1] - bbox[0]
            dy = bbox[3] - bbox[2]
            if min(dx, dy) > 0:
                aspecto = max(dx, dy) / min(dx, dy)
            else:
                aspecto = 100.0
            if aspecto > aspect_ratio_max:
                capa.DeleteFeature(feature.GetFID())
                continue

        circularidad = 1.0
        if circularity_min > 0:
            perim = geom.Boundary().Length()
            if perim > 0:
                circularidad = 4 * np.pi * area / (perim * perim)
            if circularidad < circularity_min:
                capa.DeleteFeature(feature.GetFID())
                continue

        feature.SetField("id", feature.GetFID())
        feature.SetField("area_m2", area)
        if aspect_ratio_max > 0:
            feature.SetField("aspect_ratio", aspecto)
        if circularity_min > 0:
            feature.SetField("circularity", circularidad)
        capa.SetFeature(feature)

    # Cerrar datasets
    ds_mem = None
    ds_out = None


# ============================================================================
# Predicción con Isolation Forest
# ============================================================================

def predecir_anomalia_isolation_forest(
    ruta_stack: str,
    archivos_entrenamiento: List[str],
    output_tif: Optional[str] = None,
    output_geojson: Optional[str] = None,
    n_estimators: int = ISOLATION_FOREST_N_ESTIMATORS,
    contamination: float = ISOLATION_FOREST_CONTAMINATION,
    max_samples: int = ISOLATION_FOREST_MAX_SAMPLES,
    umbral_pct: float = UMBRAL_PERCENTIL,
    sigma: float = SIGMA_GAUSSIANO,
    min_area_m2: float = MIN_AREA_ANOMALIA_M2,
    cpu_workers: int = 2,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> np.ndarray:
    """
    Detecta anomalías utilizando Isolation Forest.

    Args:
        ruta_stack: Ruta al stack multibanda GeoTIFF a analizar.
        archivos_entrenamiento: Lista de rutas a stacks de entrenamiento (sin anomalías).
        output_tif: Ruta opcional para guardar el mapa de anomalías suavizado.
        output_geojson: Ruta opcional para guardar los polígonos candidatos.
        n_estimators: Número de árboles del Isolation Forest.
        contamination: Proporción esperada de anomalías.
        max_samples: Número máximo de muestras por árbol.
        umbral_pct: Percentil para umbralizar el mapa de anomalías.
        sigma: Sigma del suavizado gaussiano.
        min_area_m2: Área mínima de polígono.
        cpu_workers: Número de hilos para el entrenamiento (n_jobs).
        progress_callback: Función llamada con (porcentaje, mensaje).
        cancel_event: Evento de cancelación.

    Returns:
        Mapa de anomalías suavizado (float32, shape alto x ancho).

    Raises:
        InterruptedError: Si se cancela.
        ValueError: Si no hay archivos de entrenamiento válidos.
    """
    from sklearn.ensemble import IsolationForest

    def update_progress(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)
        if cancel_event and cancel_event.is_set():
            raise InterruptedError()

    try:
        update_progress(0, "Cargando stack de análisis...")
        arr_pred, geotrans, (cols, filas), proj = leer_stack_multibanda(ruta_stack)
        expected_bands = arr_pred.shape[0]

        total_archivos = len(archivos_entrenamiento)
        if total_archivos == 0:
            raise ValueError("La lista de archivos de entrenamiento está vacía.")

        X_train = []
        samples_per_file = max_samples // total_archivos if total_archivos > 0 else max_samples
        samples_per_file = max(100, samples_per_file)

        for i, archivo in enumerate(archivos_entrenamiento):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError()

            try:
                arr, _, _, _ = leer_stack_multibanda(archivo)
                if arr.shape[0] == expected_bands:
                    n_pixels = arr.shape[1] * arr.shape[2]
                    n_sample = min(samples_per_file, n_pixels)
                    indices = np.random.choice(n_pixels, size=n_sample, replace=False)
                    # Muestrear píxeles
                    muestra = arr[:, indices // arr.shape[2], indices % arr.shape[2]].T
                    X_train.append(muestra)
            except Exception as e:
                logger.warning(f"Error leyendo {archivo} para entrenamiento IF: {e}")
                continue

            update_progress(
                int(5 + 25 * (i + 1) / total_archivos),
                f"Extrayendo muestras ({i+1}/{total_archivos})..."
            )

        if not X_train:
            raise ValueError(f"No se pudieron extraer muestras de entrenamiento con {expected_bands} bandas")

        X_train = np.vstack(X_train)
        update_progress(40, f"Entrenando Isolation Forest con {X_train.shape[0]} muestras...")

        clf = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=42,
            n_jobs=cpu_workers,
        )
        clf.fit(X_train)

        update_progress(60, "Calculando mapa de anomalías...")

        X_pred = arr_pred.reshape(expected_bands, -1).T
        total_pixels = X_pred.shape[0]
        block_size = min(100000, total_pixels)
        scores = np.zeros(total_pixels, dtype=np.float32)

        for start in range(0, total_pixels, block_size):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError()
            end = min(start + block_size, total_pixels)
            scores[start:end] = clf.decision_function(X_pred[start:end])
            pct = 60 + int(30 * end / total_pixels)
            update_progress(pct, f"Procesando píxeles: {end}/{total_pixels}")

        mapa_anomalia = -scores.reshape(arr_pred.shape[1], arr_pred.shape[2])
        update_progress(95, "Suavizando y umbralizando mapa...")
        mapa_suave, binario = suavizar_y_umbralizar(mapa_anomalia, sigma=sigma, umbral_pct=umbral_pct)

        if output_tif:
            guardar_raster(mapa_suave, output_tif, geotrans, proj, cols, filas)
        if output_geojson:
            vectorizar_anomalias(
                binario,
                output_geojson,
                geotrans,
                proj,
                min_area_m2,
                ASPECT_RATIO_MAX,
                CIRCULARITY_MIN,
            )

        update_progress(100, "Inferencia completada.")
        return mapa_suave

    except InterruptedError:
        logger.info("Predicción con Isolation Forest cancelada")
        # Retornar mapa vacío si es posible
        if 'arr_pred' in locals():
            return np.zeros((arr_pred.shape[1], arr_pred.shape[2]), dtype=np.float32)
        return np.zeros((1, 1), dtype=np.float32)
    except Exception as e:
        logger.error(f"Error en Isolation Forest: {e}", exc_info=True)
        if 'arr_pred' in locals():
            return np.zeros((arr_pred.shape[1], arr_pred.shape[2]), dtype=np.float32)
        return np.zeros((1, 1), dtype=np.float32)