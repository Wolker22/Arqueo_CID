# -*- coding: utf-8 -*-
"""
Backend de cálculo morfométrico basado en PyTorch (Arqueo-CID)
==============================================================

Versión 4.3 – centralizado en config.py.

Proporciona aceleración GPU (CUDA) y alternativa con GDAL para hillshade y slope.
No divide en bloques; se espera que el orquestador alimente ventanas adecuadas.

Derivados implementados (15):
- hillshade, slope
- aspect_sin, aspect_cos
- curvature, curvature_vert, curvature_horiz
- tpi (multiescala), lrm, ridge_valley
- openness_pos, openness_neg, openness_aniso
- sky_view_factor
- mrvbf
"""

import math
import time
from contextlib import nullcontext
from typing import List, Optional, Tuple, Dict, Callable

import numpy as np
import torch
import torch.nn.functional as F

# Importar constantes desde la configuración central
from ...config import (
    MAX_VRAM_FRACTION,
    SIGMA_CURVATURE_DEFAULT,
    RIDGE_VALLEY_SIGMAS_DEFAULT,
    MRVBF_SCALES_DEFAULT,
    MRVBF_SLOPE_THRESHOLD_DEFAULT,
)
from ...utils.entorno import PYTORCH_CUDA_DISPONIBLE, GDAL_DISPONIBLE
from ...utils.logging import get_logger

logger = get_logger('Tizona.pytorch_backend')


class PytorchBackend:
    """
    Motor de cálculo de derivados morfométricos a partir de un MDT.

    Soporta:
    - Aceleración GPU mediante PyTorch CUDA (FP16).
    - Alternativa rápida con GDAL para hillshade y slope.
    - Cálculo de curvaturas, TPI, LRM, openness, SVF, etc.

    Attributes:
        proc: ProcesadorLiDAR asociado.
        use_gpu: Booleano indicando si usar GPU.
        device: Dispositivo torch ('cuda' o 'cpu').
        max_vram_mb: VRAM máxima utilizable (MB).
        use_gdal: Booleano para usar GDAL nativo.
        res: Resolución espacial (m/píxel).
        _gradients_cache: Caché de gradientes por dimensiones.
        sigma_curvature: Sigma para curvaturas.
        ridge_valley_sigmas: Radios para ridge/valley.
        mrvbf_scales: Escalas para MRVBF.
        mrvbf_slope_threshold: Umbral de pendiente MRVBF.
    """

    def __init__(self, procesador: 'ProcesadorLiDAR') -> None:
        """
        Args:
            procesador: Instancia de ProcesadorLiDAR con atributos de configuración.
        """
        self.proc = procesador
        usar_gpu_config = getattr(procesador, "usar_gpu", False)

        # Selección del dispositivo de cálculo
        if PYTORCH_CUDA_DISPONIBLE and usar_gpu_config:
            self.device = torch.device("cuda")
            self.use_gpu = True
            self.total_vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
            self.max_vram_mb = self.total_vram_mb * MAX_VRAM_FRACTION
            logger.info(
                f"PyTorch GPU (CUDA) – VRAM total: {self.total_vram_mb:.0f} MB, "
                f"límite de trabajo: {self.max_vram_mb:.0f} MB"
            )
        else:
            self.device = torch.device("cpu")
            self.use_gpu = False
            self.max_vram_mb = getattr(procesador, "memoria_max_mb", 4096) * 0.6
            logger.info("PyTorch CPU – sin aceleración GPU")

        self.use_gdal = GDAL_DISPONIBLE and getattr(procesador, "usar_gdal", False)
        self.res = procesador.res

        # Caché de gradientes
        self._gradients_cache: Dict[Tuple[int, int], Tuple[torch.Tensor, torch.Tensor]] = {}

        # Parámetros
        self.sigma_curvature = getattr(procesador, "sigma_curvature", SIGMA_CURVATURE_DEFAULT)
        self.ridge_valley_sigmas = getattr(procesador, "ridge_valley_radios", RIDGE_VALLEY_SIGMAS_DEFAULT)
        self.mrvbf_scales = getattr(procesador, "mrvbf_scales", MRVBF_SCALES_DEFAULT)
        self.mrvbf_slope_threshold = getattr(procesador, "mrvbf_slope_threshold", MRVBF_SLOPE_THRESHOLD_DEFAULT)

    # ------------------------------------------------------------------
    # Utilidades de conversión y memoria
    # ------------------------------------------------------------------

    def _get_autocast(self):
        """Contexto de autocasting para FP16 en CUDA."""
        if self.use_gpu:
            return torch.amp.autocast(device_type="cuda", dtype=torch.float16)
        return nullcontext()

    def clear_cache(self) -> None:
        """Limpia la caché de gradientes y libera memoria de GPU."""
        self._gradients_cache.clear()
        if self.use_gpu:
            torch.cuda.empty_cache()

    def release_gradients(self) -> None:
        """Alias de clear_cache."""
        self.clear_cache()

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        """Convierte array a tensor en el dispositivo actual, reemplazando NaN por la media."""
        arr_float = arr.astype(np.float32)
        nan_mask = np.isnan(arr_float)
        if np.any(nan_mask):
            arr_float[nan_mask] = np.nanmean(arr_float)
        # Limpiar caché si la GPU está cerca del límite
        if self.use_gpu and torch.cuda.memory_allocated() / (1024 * 1024) > self.max_vram_mb * 0.9:
            self.clear_cache()
        return torch.from_numpy(arr_float).to(self.device)

    def _to_numpy(self, t: torch.Tensor) -> np.ndarray:
        """Mueve tensor a CPU y lo convierte a numpy float32."""
        return t.cpu().float().numpy()

    # ------------------------------------------------------------------
    # Kernels y suavizado gaussiano
    # ------------------------------------------------------------------

    def _gaussian_kernel(self, size: int, sigma: float) -> torch.Tensor:
        """Crea un kernel gaussiano 2D normalizado."""
        ax = torch.arange(-size // 2 + 1.0, size // 2 + 1.0, device=self.device)
        xx, yy = torch.meshgrid(ax, ax, indexing="ij")
        kernel = torch.exp(-(xx**2 + yy**2) / (2 * sigma**2))
        return (kernel / kernel.sum()).view(1, 1, size, size)

    def _apply_gaussian_blur(
        self, z_t: torch.Tensor, sigma: float, kernel_size: Optional[int] = None
    ) -> torch.Tensor:
        """Aplica filtro gaussiano al MDT."""
        if kernel_size is None:
            kernel_size = int(np.ceil(sigma * 4))
            if kernel_size % 2 == 0:
                kernel_size += 1
        kernel = self._gaussian_kernel(kernel_size, sigma)
        z_4d = z_t.unsqueeze(0).unsqueeze(0)
        pad = kernel_size // 2
        z_pad = F.pad(z_4d, (pad, pad, pad, pad), mode="replicate")
        return F.conv2d(z_pad, kernel).squeeze()

    # ------------------------------------------------------------------
    # GDAL helpers (solo si está disponible)
    # ------------------------------------------------------------------

    def _crear_dataset_mem(self, z: np.ndarray):
        """Crea dataset GDAL en memoria (solo si GDAL disponible)."""
        if not self.use_gdal:
            return None
        from osgeo import gdal
        transform = self.proc.transform
        driver = gdal.GetDriverByName("MEM")
        ds = driver.Create("", z.shape[1], z.shape[0], 1, gdal.GDT_Float32)
        ds.SetGeoTransform((transform.c, transform.a, transform.b, transform.f, transform.d, transform.e))
        ds.GetRasterBand(1).WriteArray(z)
        return ds

    def _ejecutar_dem_processing(self, z: np.ndarray, processing: str, **kwargs) -> np.ndarray:
        """Ejecuta algoritmo GDALDEMProcessing."""
        if not self.use_gdal:
            raise RuntimeError("GDAL no disponible")
        from osgeo import gdal
        ds = self._crear_dataset_mem(z)
        result_ds = gdal.DEMProcessing("", ds, processing, format="MEM", **kwargs)
        arr = result_ds.ReadAsArray()
        ds = None
        result_ds = None
        return arr.astype(np.float32)

    # ------------------------------------------------------------------
    # Gradientes (caché por dimensiones)
    # ------------------------------------------------------------------

    def _calcular_gradientes(self, z_t: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Calcula dx, dy con caché por dimensiones."""
        key = (z_t.shape[0], z_t.shape[1])
        cached = self._gradients_cache.get(key)
        if cached is not None:
            return cached
        with self._get_autocast():
            dy, dx = torch.gradient(z_t, spacing=self.res, dim=(0, 1))
        self._gradients_cache[key] = (dx, dy)
        return dx, dy

    # ------------------------------------------------------------------
    # Hillshade
    # ------------------------------------------------------------------

    def hillshade(self, z: np.ndarray, z_factor: float, angulos: List[float], multidir: bool) -> np.ndarray:
        """
        Calcula hillshade (GDAL o PyTorch). Retorna uint8.

        Args:
            z: MDT.
            z_factor: Factor de exageración vertical.
            angulos: Lista de ángulos de iluminación.
            multidir: Si True, combina múltiples ángulos.

        Returns:
            Imagen hillshade en uint8.
        """
        if self.use_gdal:
            try:
                if multidir:
                    combined = None
                    for az in angulos:
                        hs = self._ejecutar_dem_processing(
                            z, "hillshade", azimuth=az, zFactor=z_factor, altitude=45.0, combined=False
                        )
                        combined = hs if combined is None else np.maximum(combined, hs)
                    return combined.astype(np.uint8)
                else:
                    return self._ejecutar_dem_processing(
                        z, "hillshade", azimuth=315, zFactor=z_factor, altitude=45.0, combined=False
                    ).astype(np.uint8)
            except Exception as e:
                logger.warning(f"GDAL hillshade falló, usando PyTorch: {e}")
        return self._hillshade_pytorch(z, z_factor, angulos, multidir)

    def _hillshade_pytorch(self, z: np.ndarray, z_factor: float, angulos: List[float], multidir: bool) -> np.ndarray:
        """Implementación PyTorch del hillshade."""
        z_t = self._to_tensor(z)
        dx, dy = self._calcular_gradientes(z_t)
        with self._get_autocast():
            slope_rad = torch.atan(z_factor * torch.sqrt(dx**2 + dy**2))
            aspect_rad = torch.atan2(-dy, dx)
            alt_rad = torch.tensor(np.pi / 4.0, device=self.device)
            if multidir:
                hs_max = torch.zeros_like(z_t)
                for az in angulos:
                    az_rad = torch.tensor(np.deg2rad((360.0 - az + 90.0) % 360.0), device=self.device)
                    hs = 255.0 * (
                        torch.cos(alt_rad) * torch.cos(slope_rad)
                        + torch.sin(alt_rad) * torch.sin(slope_rad) * torch.cos(az_rad - aspect_rad)
                    )
                    hs_max = torch.maximum(hs_max, hs)
                result = torch.clamp(hs_max, 0, 255).byte()
            else:
                az_rad = torch.tensor(np.deg2rad((360.0 - 315.0 + 90.0) % 360.0), device=self.device)
                hs = 255.0 * (
                    torch.cos(alt_rad) * torch.cos(slope_rad)
                    + torch.sin(alt_rad) * torch.sin(slope_rad) * torch.cos(az_rad - aspect_rad)
                )
                result = torch.clamp(hs, 0, 255).byte()
        return self._to_numpy(result)

    # ------------------------------------------------------------------
    # Slope
    # ------------------------------------------------------------------

    def slope(self, z: np.ndarray) -> np.ndarray:
        """Calcula pendiente en grados."""
        if self.use_gdal:
            try:
                return self._ejecutar_dem_processing(z, "slope").astype(np.float32)
            except Exception as e:
                logger.warning(f"GDAL slope falló, usando PyTorch: {e}")
        z_t = self._to_tensor(z)
        dx, dy = self._calcular_gradientes(z_t)
        with self._get_autocast():
            slope_rad = torch.atan(torch.sqrt(dx**2 + dy**2))
            res = torch.rad2deg(slope_rad)
        return self._to_numpy(res)

    # ------------------------------------------------------------------
    # Aspecto (para IA)
    # ------------------------------------------------------------------

    def aspect_sin(self, z: np.ndarray) -> np.ndarray:
        """Seno de la orientación (componente N-S)."""
        z_t = self._to_tensor(z)
        dx, dy = self._calcular_gradientes(z_t)
        with self._get_autocast():
            aspect_rad = torch.atan2(dy, -dx)
            sin_val = torch.sin(aspect_rad)
        return self._to_numpy(sin_val)

    def aspect_cos(self, z: np.ndarray) -> np.ndarray:
        """Coseno de la orientación (componente E-W)."""
        z_t = self._to_tensor(z)
        dx, dy = self._calcular_gradientes(z_t)
        with self._get_autocast():
            aspect_rad = torch.atan2(dy, -dx)
            cos_val = torch.cos(aspect_rad)
        return self._to_numpy(cos_val)

    # ------------------------------------------------------------------
    # Curvaturas
    # ------------------------------------------------------------------

    def _compute_hessian(self, z_t: torch.Tensor, sigma: float):
        """Calcula derivadas segundas sobre MDT suavizado."""
        z_smooth = self._apply_gaussian_blur(z_t, sigma)
        dx, dy = torch.gradient(z_smooth, spacing=self.res, dim=(0, 1))
        dxx, dxy = torch.gradient(dx, spacing=self.res, dim=(0, 1))
        _, dyy = torch.gradient(dy, spacing=self.res, dim=(0, 1))
        return dx, dy, dxx, dyy, dxy

    def curvature(self, z: np.ndarray) -> np.ndarray:
        """Curvatura general (Laplaciana)."""
        z_t = self._to_tensor(z)
        _, _, dxx, dyy, _ = self._compute_hessian(z_t, self.sigma_curvature)
        return self._to_numpy(dxx + dyy)

    def curvature_vert(self, z: np.ndarray) -> np.ndarray:
        """Curvatura vertical (perfil)."""
        z_t = self._to_tensor(z)
        dx, dy, dxx, dyy, dxy = self._compute_hessian(z_t, self.sigma_curvature)
        p = dx**2 + dy**2 + 1e-8
        cv = (dx**2 * dxx + 2 * dx * dy * dxy + dy**2 * dyy) / (p * torch.sqrt(1 + p))
        return self._to_numpy(cv)

    def curvature_horiz(self, z: np.ndarray) -> np.ndarray:
        """Curvatura horizontal (planta)."""
        z_t = self._to_tensor(z)
        dx, dy, dxx, dyy, dxy = self._compute_hessian(z_t, self.sigma_curvature)
        p = dx**2 + dy**2 + 1e-8
        ch = (dy**2 * dxx - 2 * dx * dy * dxy + dx**2 * dyy) / p
        return self._to_numpy(ch)

    # ------------------------------------------------------------------
    # TPI, LRM, ridge/valley
    # ------------------------------------------------------------------

    def tpi_multiescala(self, z: np.ndarray, radios: List[float]) -> np.ndarray:
        """TPI promediado sobre varios radios (metros)."""
        logger.info(f"Calculando TPI multiescala (radios={radios})...")
        inicio = time.time()
        z_t = self._to_tensor(z)
        with self._get_autocast():
            tpi_sum = torch.zeros_like(z_t)
            z_4d = z_t.unsqueeze(0).unsqueeze(0)
            for r in radios:
                size = max(3, int(r / self.proc.res))
                if size % 2 == 0:
                    size += 1
                pad = size // 2
                kernel = torch.ones((1, 1, size, size), device=self.device) / (size * size)
                z_pad = F.pad(z_4d, (pad, pad, pad, pad), mode="replicate")
                mean_z = F.conv2d(z_pad, kernel).squeeze()
                tpi_sum += (z_t - mean_z)
            res = tpi_sum / len(radios)
        duracion = time.time() - inicio
        logger.info(f"TPI multiescala completado en {duracion:.1f}s")
        return self._to_numpy(res)

    def local_relief_model(self, z: np.ndarray, radio: float) -> np.ndarray:
        """Modelo de Relieve Local (LRM): resta de la media en ventana."""
        z_t = self._to_tensor(z)
        size = max(3, int(radio / self.proc.res))
        if size % 2 == 0:
            size += 1
        pad = size // 2
        with self._get_autocast():
            z_4d = z_t.unsqueeze(0).unsqueeze(0)
            z_pad = F.pad(z_4d, (pad, pad, pad, pad), mode="replicate")
            kernel = torch.ones((1, 1, size, size), device=self.device) / (size * size)
            mean_z = F.conv2d(z_pad, kernel).squeeze()
            lrm = z_t - mean_z
        return self._to_numpy(lrm)

    def ridge_valley(self, z: np.ndarray, sigmas: Optional[List[float]] = None) -> np.ndarray:
        """Detección multiescala de crestas/valles mediante Hessiano."""
        if sigmas is None:
            sigmas = self.ridge_valley_sigmas
        logger.info(f"Calculando Ridge/Valley (sigmas={sigmas})...")
        inicio = time.time()
        z_t = self._to_tensor(z)
        with self._get_autocast():
            ridge_response = torch.zeros_like(z_t)
            for sigma in sigmas:
                sigma_pix = sigma / self.proc.res
                size = max(3, int(sigma_pix * 4))
                if size % 2 == 0:
                    size += 1
                ax = torch.arange(size, device=self.device, dtype=torch.float32) - size // 2
                xx, yy = torch.meshgrid(ax, ax, indexing="ij")
                kernel = torch.exp(-(xx**2 + yy**2) / (2 * sigma_pix**2))
                kernel /= kernel.sum()
                kernel = kernel.view(1, 1, size, size)
                z_4d = z_t.unsqueeze(0).unsqueeze(0)
                pad = size // 2
                z_pad = F.pad(z_4d, (pad, pad, pad, pad), mode="replicate")
                z_smooth = F.conv2d(z_pad, kernel).squeeze()
                dx, dy = torch.gradient(z_smooth, spacing=self.proc.res, dim=(0, 1))
                dxx, dxy = torch.gradient(dx, spacing=self.proc.res, dim=(0, 1))
                _, dyy = torch.gradient(dy, spacing=self.proc.res, dim=(0, 1))
                trace = dxx + dyy
                det = dxx * dyy - dxy * dxy
                sqrt_term = torch.sqrt(torch.clamp(trace**2 - 4 * det, min=0))
                lambda2 = (trace - sqrt_term) / 2
                ridge = -lambda2
                ridge_response = torch.maximum(ridge_response, ridge)
        duracion = time.time() - inicio
        logger.info(f"Ridge/Valley completado en {duracion:.1f}s")
        return self._to_numpy(ridge_response).astype(np.float32)

    # ------------------------------------------------------------------
    # Openness
    # ------------------------------------------------------------------

    def openness(self, z: np.ndarray, radio: float, positive: bool = True) -> np.ndarray:
        """Calcula openness positivo o negativo."""
        etiqueta = "positivo" if positive else "negativo"
        logger.info(f"Calculando openness {etiqueta} (radio={radio}m)...")
        inicio = time.time()
        z_t = self._to_tensor(z)
        L = max(1, int(radio / self.proc.res))
        h, w = z_t.shape
        device = self.device

        initial_angle = np.pi / 2
        min_angle_rad = torch.full((h, w), initial_angle, device=device, dtype=torch.float32)

        dirs = [
            (0, 1), (1, 1), (1, 0), (1, -1),
            (0, -1), (-1, -1), (-1, 0), (-1, 1),
        ]

        for dy_dir, dx_dir in dirs:
            dir_min = torch.full((h, w), initial_angle, device=device, dtype=torch.float32)
            for step in range(1, L + 1):
                ny = (torch.arange(h, device=device).view(-1, 1) + dy_dir * step).clamp(0, h - 1)
                nx = (torch.arange(w, device=device).view(1, -1) + dx_dir * step).clamp(0, w - 1)
                z_neigh = z_t[ny.long(), nx.long()]
                dz = z_neigh - z_t
                dist = step * self.proc.res
                angle = torch.atan(dz / dist)
                if positive:
                    current_angle = initial_angle - angle
                else:
                    current_angle = initial_angle + angle
                dir_min = torch.minimum(dir_min, current_angle)
            min_angle_rad = torch.minimum(min_angle_rad, dir_min)

        res = torch.rad2deg(min_angle_rad)
        del z_t
        if self.use_gpu:
            torch.cuda.empty_cache()
        duracion = time.time() - inicio
        logger.info(f"Openness {etiqueta} completado en {duracion:.1f}s")
        return self._to_numpy(res)

    def openness_anisotropic(self, z: np.ndarray, radio: float, direcciones=None) -> np.ndarray:
        """Alias de openness positivo (compatibilidad)."""
        logger.info(f"Calculando openness anisotrópico (radio={radio}m)...")
        inicio = time.time()
        res = self.openness(z, radio, positive=True)
        duracion = time.time() - inicio
        logger.info(f"Openness anisotrópico completado en {duracion:.1f}s")
        return res

    # ------------------------------------------------------------------
    # Sky View Factor
    # ------------------------------------------------------------------

    def sky_view_factor(self, z: np.ndarray) -> np.ndarray:
        """Sky View Factor basado en pendiente (0 obstruido, 1 abierto)."""
        slope_deg = self.slope(z)
        svf = 1.0 - (slope_deg / 90.0)
        return np.clip(svf, 0, 1).astype(np.float32)

    # ------------------------------------------------------------------
    # MRVBF
    # ------------------------------------------------------------------

    def mrvbf(self, z: np.ndarray, scales: Optional[List[float]] = None, slope_threshold: Optional[float] = None) -> np.ndarray:
        """
        Índice multiescala de planitud de fondos de valle (MRVBF).
        """
        if scales is None:
            scales = self.mrvbf_scales
        if slope_threshold is None:
            slope_threshold = self.mrvbf_slope_threshold

        logger.info(f"Calculando MRVBF (escalas={scales}, umbral pendiente={slope_threshold}°)...")
        inicio = time.time()

        slope_deg = self.slope(z)
        flat_mask = slope_deg < slope_threshold

        z_t = self._to_tensor(z)
        with self._get_autocast():
            z_4d = z_t.unsqueeze(0).unsqueeze(0)
            mrvbf_sum = torch.zeros_like(z_t)

            for scale in scales:
                size = max(3, int(scale / self.res))
                if size % 2 == 0:
                    size += 1
                pad_pool = size // 2

                mean_local = F.avg_pool2d(z_4d, kernel_size=size, stride=1, padding=pad_pool).squeeze()
                deviation = torch.abs(z_t - mean_local)

                diff_sq = (z_4d - mean_local.unsqueeze(0).unsqueeze(0)) ** 2
                var_local = F.avg_pool2d(diff_sq, kernel_size=size, stride=1, padding=pad_pool).squeeze()
                std_local = torch.sqrt(var_local + 1e-6)

                flatness = 1.0 - torch.clamp(deviation / std_local, 0.0, 1.0)
                mrvbf_sum += flatness

            mrvbf = mrvbf_sum / len(scales)

        result = self._to_numpy(mrvbf)
        result[~flat_mask] = 0.0

        duracion = time.time() - inicio
        logger.info(f"MRVBF completado en {duracion:.1f}s")
        return np.clip(result, 0.0, 1.0).astype(np.float32)