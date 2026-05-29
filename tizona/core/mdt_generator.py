# -*- coding: utf-8 -*-
"""
Generación del MDT optimizada para IA (Arqueo-CID)
===================================================

Filtrado estricto de suelo, rasterización de alta calidad con interpolación
orgánica (Thin Plate Spline o IDW gaussiano) y suavizado adaptativo.

Compatible con laspy >= 2.0 y con GDAL para interpolación.
"""

import os
import json
import subprocess
import tempfile
import csv
from typing import Optional, Tuple, Dict, Any, List

import numpy as np
import laspy
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS

# Importar constantes desde la configuración central
from ...config import (
    PDAL_TIMEOUT,
    CACHE_SUELO_DIR,
    INTERPOLATION_METHOD,
    SMRF_DEFAULT_WINDOW,
    SMRF_DEFAULT_SLOPE,
    SMRF_DEFAULT_THRESHOLD,
    SMRF_DEFAULT_SCALAR,
    GDAL_GRID_METHOD,
    GDAL_GRID_RADIUS1_FACTOR,
    GDAL_GRID_RADIUS2_FACTOR,
    GDAL_GRID_SMOOTHING,
    GDAL_GRID_COMPRESSION_OPTS,
    PDAL_RASTER_OUTPUT_TYPE,
    PDAL_GDAL_DRIVER,
    PDAL_GDAL_DATA_TYPE,
    PDAL_GDAL_OPTS,
    RBF_MAX_POINTS,
    RBF_KERNEL,
    RBF_BLOCK_SIZE,
    IDW_K_NEIGHBORS,
    IDW_DISTANCE_UPPER_BOUND,
    IDW_SIGMA_FACTOR,
    MIN_PUNTOS_SUELO,
    BILATERAL_SIGMA_COLOR,
    BILATERAL_SIGMA_SPATIAL,
)
from ...utils.logging import get_logger
from .salidas import perfil_derivado

logger = get_logger('Tizona.mdt_generator')


class MDTGenerator:
    """
    Genera un MDT de alta calidad a partir de nubes LiDAR, filtrando suelo
    y aplicando interpolación avanzada para evitar artefactos de TIN y ghosting.

    Attributes:
        proc: Instancia de ProcesadorLiDAR (proporciona configuración y callbacks).
        temp_files: Lista de archivos temporales para limpieza.
    """

    def __init__(self, procesador: 'ProcesadorLiDAR') -> None:
        """
        Args:
            procesador: Instancia de ProcesadorLiDAR con parámetros de procesamiento.
        """
        self.proc = procesador
        self.temp_files: List[str] = []

    # ------------------------------------------------------------------
    # Utilidades PDAL
    # ------------------------------------------------------------------

    def _ejecutar_pipeline(self, pipeline: List[Any], timeout: int = PDAL_TIMEOUT) -> bool:
        """
        Ejecuta un pipeline PDAL y devuelve True si tiene éxito.

        Args:
            pipeline: Lista de etapas del pipeline PDAL (formato JSON).
            timeout: Tiempo máximo de espera en segundos.

        Returns:
            True si la ejecución fue exitosa, False en caso contrario.
        """
        try:
            subprocess.run(
                ["pdal", "pipeline", "--stdin"],
                input=json.dumps(pipeline),
                text=True,
                capture_output=True,
                check=True,
                timeout=timeout,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"PDAL falló: {e.stderr.strip()}")
            return False
        except Exception as e:
            logger.warning(f"Error PDAL: {e}")
            return False

    # ------------------------------------------------------------------
    # Filtros de suelo con PDAL
    # ------------------------------------------------------------------

    @staticmethod
    def _aplicar_filtro_sobre_clase2(
        ruta_laz: str,
        algoritmo: str,
        smrf_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extrae Clase 2 y opcionalmente aplica SMRF/CSF. Retorna ruta temporal .laz.

        Args:
            ruta_laz: Ruta al archivo LAZ original.
            algoritmo: 'smrf', 'csf' o 'none'.
            smrf_params: Diccionario con parámetros del filtro.

        Returns:
            Ruta al archivo LAZ filtrado, o None si falló.
        """
        tmpfile = tempfile.mkstemp(suffix=".laz", prefix="suelo_")
        os.close(tmpfile[0])
        path = tmpfile[1]
        pipeline = [ruta_laz, {"type": "filters.range", "limits": "Classification[2:2]"}]
        if algoritmo in ("smrf", "csf"):
            pipeline.append(
                {
                    "type": f"filters.{algoritmo}",
                    "window": smrf_params.get("window", SMRF_DEFAULT_WINDOW),
                    "slope": smrf_params.get("slope", SMRF_DEFAULT_SLOPE),
                    "threshold": smrf_params.get("threshold", SMRF_DEFAULT_THRESHOLD),
                }
            )
        pipeline.append({"type": "writers.las", "filename": path})
        try:
            subprocess.run(
                ["pdal", "pipeline", "--stdin"],
                input=json.dumps(pipeline),
                text=True,
                capture_output=True,
                check=True,
                timeout=PDAL_TIMEOUT,
            )
            logger.info("Filtro Clase2+algoritmo aplicado.")
            return path
        except Exception as e:
            logger.warning(f"Fallo filtro Clase2 PDAL: {e}")
            if os.path.exists(path):
                os.remove(path)
            return None

    @staticmethod
    def _aplicar_filtro_directo(
        ruta_laz: str,
        algoritmo: str,
        smrf_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Aplica SMRF/CSF sobre la nube completa y extrae Clase 2. Retorna ruta temporal .laz.

        Args:
            ruta_laz: Ruta al archivo LAZ original.
            algoritmo: 'smrf', 'csf' o 'none'.
            smrf_params: Diccionario con parámetros del filtro.

        Returns:
            Ruta al archivo LAZ filtrado, o la original si algoritmo='none', o None si falló.
        """
        if algoritmo == "none":
            return ruta_laz
        tmpfile = tempfile.mkstemp(suffix=".laz", prefix="suelo_directo_")
        os.close(tmpfile[0])
        path = tmpfile[1]
        pipeline = [
            ruta_laz,
            {
                "type": f"filters.{algoritmo}",
                "window": smrf_params.get("window", SMRF_DEFAULT_WINDOW),
                "slope": smrf_params.get("slope", SMRF_DEFAULT_SLOPE),
                "threshold": smrf_params.get("threshold", SMRF_DEFAULT_THRESHOLD),
                "scalar": smrf_params.get("scalar", SMRF_DEFAULT_SCALAR),
            },
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "writers.las", "filename": path},
        ]
        try:
            subprocess.run(
                ["pdal", "pipeline", "--stdin"],
                input=json.dumps(pipeline),
                text=True,
                capture_output=True,
                check=True,
                timeout=PDAL_TIMEOUT,
            )
            logger.info("Filtro directo + extracción suelo aplicado.")
            return path
        except Exception as e:
            logger.warning(f"Fallo filtro directo PDAL: {e}")
            if os.path.exists(path):
                os.remove(path)
            return None

    # ------------------------------------------------------------------
    # Acceso compatible a arrays de laspy (laspy >= 2.0)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_xyz_classification(las_reader: laspy.LasReader) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Devuelve x, y, z, classification del lector LAS/LAZ abierto.
        Compatible con laspy >= 2.0 y versiones anteriores.

        Args:
            las_reader: Lector LAS/LAZ abierto.

        Returns:
            Tupla (x, y, z, classification) como arrays numpy.
        """
        try:
            # Forma moderna (laspy >= 2.0)
            x = np.array(las_reader.x)
            y = np.array(las_reader.y)
            z = np.array(las_reader.z)
            classification = np.array(las_reader.classification)
        except AttributeError:
            # Fallback para versiones antiguas
            pts = las_reader.points
            x = np.array(pts.x)
            y = np.array(pts.y)
            z = np.array(pts.z)
            classification = np.array(pts.classification)
        return x, y, z, classification

    # ------------------------------------------------------------------
    # Extracción de puntos de suelo con laspy
    # ------------------------------------------------------------------

    def _extraer_suelo_laspy(self, ruta_laz: str) -> Optional[str]:
        """
        Extrae puntos de Clase 2 del LAZ usando laspy y los guarda en CSV.

        Args:
            ruta_laz: Ruta al archivo LAZ.

        Returns:
            Ruta al archivo CSV con puntos de suelo, o None si no se pudo.
        """
        try:
            with laspy.open(ruta_laz) as f:
                x, y, z, cls = self._get_xyz_classification(f)
            mask = cls == 2
            if mask.sum() < MIN_PUNTOS_SUELO:
                logger.warning(
                    f"Pocos puntos de suelo (<{MIN_PUNTOS_SUELO}). Se usará nube completa."
                )
                return None
            xv, yv, zv = x[mask], y[mask], z[mask]

            fd, path = tempfile.mkstemp(suffix=".csv", prefix="suelo_laspy_")
            with os.fdopen(fd, "w", newline="") as out:
                writer = csv.writer(out)
                writer.writerow(["X", "Y", "Z"])
                for xi, yi, zi in zip(xv, yv, zv):
                    writer.writerow([xi, yi, zi])
            self.temp_files.append(path)
            logger.info(f"Extraídos {len(xv)} puntos de suelo (Clase 2) vía laspy.")
            return path
        except Exception as e:
            logger.error(f"Error extrayendo suelo con laspy: {e}")
            return None

    # ------------------------------------------------------------------
    # Rasterización con GDAL Grid
    # ------------------------------------------------------------------

    def _rasterizar_con_gdal_grid(
        self,
        puntos_csv: str,
        xmin: float,
        ymax: float,
        cols: int,
        rows: int,
        res: float,
        crs: CRS,
        ruta_mdt: str,
        method: str = GDAL_GRID_METHOD,
    ) -> bool:
        """
        Interpola con GDAL Grid usando el método configurado.

        Args:
            puntos_csv: Ruta al archivo CSV con puntos (X, Y, Z).
            xmin, ymax: Coordenadas mínima X y máxima Y del área.
            cols, rows: Dimensiones del ráster en píxeles.
            res: Resolución espacial.
            crs: Sistema de coordenadas.
            ruta_mdt: Ruta de salida del GeoTIFF.
            method: 'linear' (más suave) o 'invdist' (ponderación inversa).

        Returns:
            True si la interpolación fue exitosa, False en caso contrario.
        """
        try:
            from osgeo import gdal

            if method == "linear":
                options = gdal.GridOptions(
                    format="GTiff",
                    outputType=gdal.GDT_Float32,
                    algorithm="linear",
                    width=cols,
                    height=rows,
                    outputBounds=(
                        xmin,
                        ymax - rows * res,
                        xmin + cols * res,
                        ymax,
                    ),
                    outputSRS=crs,
                    zfield="Z",
                    lco=GDAL_GRID_COMPRESSION_OPTS,
                )
            else:  # invdist (fallback o configurado)
                radius1 = res * GDAL_GRID_RADIUS1_FACTOR
                radius2 = res * GDAL_GRID_RADIUS2_FACTOR
                options = gdal.GridOptions(
                    format="GTiff",
                    outputType=gdal.GDT_Float32,
                    algorithm="invdist",
                    width=cols,
                    height=rows,
                    outputBounds=(
                        xmin,
                        ymax - rows * res,
                        xmin + cols * res,
                        ymax,
                    ),
                    outputSRS=crs,
                    zfield="Z",
                    radius1=radius1,
                    radius2=radius2,
                    smoothing=GDAL_GRID_SMOOTHING,
                    lco=GDAL_GRID_COMPRESSION_OPTS,
                )
            gdal.Grid(ruta_mdt, puntos_csv, options=options)
            logger.info(f"MDT generado con GDAL Grid ({method}).")
            return True
        except Exception as e:
            logger.warning(f"GDAL Grid ({method}) falló: {e}")
            return False

    # ------------------------------------------------------------------
    # PDAL -> GeoTIFF
    # ------------------------------------------------------------------

    def _generar_mdt_pdal(self, laz_suelo: str, ruta_mdt: str) -> bool:
        """
        Usa PDAL writers.gdal para generar el MDT.

        Args:
            laz_suelo: Ruta al archivo LAZ con puntos de suelo.
            ruta_mdt: Ruta de salida del GeoTIFF.

        Returns:
            True si la generación fue exitosa, False en caso contrario.
        """
        pipeline = [laz_suelo]
        if self.proc.pdal_decimation_step > 1:
            pipeline.append(
                {"type": "filters.decimation", "step": self.proc.pdal_decimation_step}
            )
        pipeline.append(
            {
                "type": "writers.gdal",
                "resolution": self.proc.res,
                "output_type": PDAL_RASTER_OUTPUT_TYPE,
                "gdaldriver": PDAL_GDAL_DRIVER,
                "filename": ruta_mdt,
                "data_type": PDAL_GDAL_DATA_TYPE,
                "gdalopts": PDAL_GDAL_OPTS,
            }
        )
        return self._ejecutar_pipeline(pipeline)

    # ------------------------------------------------------------------
    # Fallback Python: interpolación orgánica (RBF o IDW)
    # ------------------------------------------------------------------

    def _generar_mdt_fallback(
        self,
        fuente: str,
        ruta_mdt: str,
        xmin: float,
        ymax: float,
        cols: int,
        rows: int,
        transform: rasterio.Affine,
        crs: CRS,
    ) -> None:
        """
        Interpolación Python del MDT con métodos elásticos:
        1. Thin Plate Spline (RBF) si scipy >= 1.7.
        2. IDW con pesos gaussianos (k vecinos) como alternativa.

        Args:
            fuente: Ruta al archivo LAZ de entrada.
            ruta_mdt: Ruta de salida del GeoTIFF.
            xmin, ymax, cols, rows, transform, crs: Parámetros geoespaciales.
        """
        logger.info("Interpolación Python del MDT (método orgánico).")
        with laspy.open(fuente) as f:
            x, y, z, _ = self._get_xyz_classification(f)

        # Crear malla destino
        mdt = np.full((rows, cols), np.nan, dtype=np.float32)
        grid_x = transform.c + (np.arange(cols) + 0.5) * transform.a
        grid_y = transform.f + (np.arange(rows) + 0.5) * transform.e
        xx, yy = np.meshgrid(grid_x, grid_y)
        puntos_destino = np.column_stack((xx.ravel(), yy.ravel()))

        try:
            from scipy.spatial import cKDTree
        except ImportError:
            raise ImportError("Se requiere SciPy para la interpolación Python.")

        # Intentar Thin Plate Spline (RBF)
        try:
            from scipy.interpolate import RBFInterpolator

            n_pts = min(len(z), RBF_MAX_POINTS)
            idx_sample = np.random.choice(len(z), size=n_pts, replace=False)
            pts_src = np.column_stack((x[idx_sample], y[idx_sample]))
            z_src = z[idx_sample]

            rbf = RBFInterpolator(pts_src, z_src, kernel=RBF_KERNEL)
            # Procesar por bloques para evitar picos de memoria
            for i in range(0, len(puntos_destino), RBF_BLOCK_SIZE):
                chunk = puntos_destino[i : i + RBF_BLOCK_SIZE]
                mdt.flat[i : i + RBF_BLOCK_SIZE] = rbf(chunk)
            del rbf
            logger.info("MDT interpolado con Thin Plate Spline (RBF).")
        except Exception as e:
            logger.warning(f"RBF no disponible o falló ({e}). Usando IDW gaussiano.")
            # IDW con pesos gaussianos
            tree = cKDTree(np.column_stack((x, y)))
            dist, idx = tree.query(
                puntos_destino,
                k=IDW_K_NEIGHBORS,
                distance_upper_bound=IDW_DISTANCE_UPPER_BOUND,
            )
            sigma = self.proc.res * IDW_SIGMA_FACTOR
            for i in range(len(puntos_destino)):
                if np.any(dist[i] < IDW_DISTANCE_UPPER_BOUND):
                    valid = dist[i] < IDW_DISTANCE_UPPER_BOUND
                    w = np.exp(-0.5 * (dist[i][valid] / sigma) ** 2)
                    w /= np.sum(w)
                    mdt.flat[i] = np.sum(z[idx[i][valid]] * w)

        # Rellenar huecos residuales
        if np.any(np.isnan(mdt)):
            self._rellenar_nan(mdt)

        # Guardar con perfil unificado
        perfil = perfil_derivado(crs, transform, rows, cols, np.float32)
        with rasterio.open(ruta_mdt, "w", **perfil) as dst:
            dst.write(mdt.astype(np.float32), 1)
        logger.info("MDT generado por interpolación Python.")

    # ------------------------------------------------------------------
    # Obtención de CRS
    # ------------------------------------------------------------------

    def _obtener_crs(self, ruta_laz: str) -> CRS:
        """
        Determina el CRS del archivo LAZ. Si no se puede, asume UTM según la ubicación.

        Args:
            ruta_laz: Ruta al archivo LAZ.

        Returns:
            CRS (sistema de coordenadas).
        """
        crs = None
        try:
            with laspy.open(ruta_laz) as f:
                try:
                    crs = f.header.crs
                except AttributeError:
                    try:
                        crs = f.header.parse_crs()
                    except Exception:
                        pass
        except Exception:
            pass

        if crs is None:
            # Fallback: estimar UTM según longitud (xmin)
            with laspy.open(ruta_laz) as f:
                xmin = f.header.x_min
            # Husos UTM: 28 para Canarias, 29 para Galicia/Portugal, 30 para España peninsular
            if -19 < xmin < -13:
                crs = CRS.from_epsg(32628)  # UTM 28N
            elif -13 < xmin < -7:
                crs = CRS.from_epsg(32629)  # UTM 29N
            elif -7 < xmin < -1:
                crs = CRS.from_epsg(32630)  # UTM 30N
            else:
                crs = CRS.from_epsg(25830)  # ETRS89 / UTM 30N (península)
            logger.warning(f"CRS no encontrado, usando fallback: {crs}")
        return crs

    # ------------------------------------------------------------------
    # Obtención fiable de puntos de suelo
    # ------------------------------------------------------------------

    def _obtener_fuente_suelo(self) -> Tuple[str, bool, CRS, float, float, float, float]:
        """
        Busca obtener puntos de suelo (Clase 2) usando PDAL, laspy, o la nube completa.

        Returns:
            (ruta_fuente, es_csv, crs, xmin, ymin, xmax, ymax)
        """
        ruta_laz = self.proc.ruta_laz

        # 1. Intentar con PDAL
        if self.proc.usar_pdal:
            if self.proc.usar_clasificacion_existente:
                tmp = self._aplicar_filtro_sobre_clase2(
                    ruta_laz, self.proc.algoritmo_suelo, self.proc.smrf_params
                )
                if tmp:
                    self.temp_files.append(tmp)
                    with laspy.open(tmp) as f:
                        xmin, xmax = f.header.x_min, f.header.x_max
                        ymin, ymax = f.header.y_min, f.header.y_max
                    crs = self._obtener_crs(tmp)
                    return tmp, False, crs, xmin, ymin, xmax, ymax
                tmp = self._aplicar_filtro_directo(
                    ruta_laz, self.proc.algoritmo_suelo, self.proc.smrf_params
                )
                if tmp:
                    self.temp_files.append(tmp)
                    with laspy.open(tmp) as f:
                        xmin, xmax = f.header.x_min, f.header.x_max
                        ymin, ymax = f.header.y_min, f.header.y_max
                    crs = self._obtener_crs(tmp)
                    return tmp, False, crs, xmin, ymin, xmax, ymax
            else:
                tmp = self._aplicar_filtro_directo(
                    ruta_laz, self.proc.algoritmo_suelo, self.proc.smrf_params
                )
                if tmp:
                    self.temp_files.append(tmp)
                    with laspy.open(tmp) as f:
                        xmin, xmax = f.header.x_min, f.header.x_max
                        ymin, ymax = f.header.y_min, f.header.y_max
                    crs = self._obtener_crs(tmp)
                    return tmp, False, crs, xmin, ymin, xmax, ymax

        # 2. Fallback con laspy (CSV de suelo)
        if self.proc.usar_clasificacion_existente:
            csv_path = self._extraer_suelo_laspy(ruta_laz)
            if csv_path:
                with open(csv_path, "r") as f:
                    reader = csv.DictReader(f)
                    xs, ys = [], []
                    for row in reader:
                        xs.append(float(row["X"]))
                        ys.append(float(row["Y"]))
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                crs = self._obtener_crs(ruta_laz)
                return csv_path, True, crs, xmin, ymin, xmax, ymax

        # 3. Último recurso: nube completa
        logger.warning("Usando nube completa (calidad reducida).")
        with laspy.open(ruta_laz) as f:
            xmin, xmax = f.header.x_min, f.header.x_max
            ymin, ymax = f.header.y_min, f.header.y_max
        return ruta_laz, False, self._obtener_crs(ruta_laz), xmin, ymin, xmax, ymax

    # ------------------------------------------------------------------
    # Generación principal del MDT
    # ------------------------------------------------------------------

    def generar_mdt(self) -> Tuple[str, np.ndarray, rasterio.Affine, CRS]:
        """
        Genera el MDT final:
        1. Filtra suelo.
        2. Rasteriza con GDAL Grid, PDAL o fallback Python.
        3. Rellena huecos, suaviza (gaussiano + bilateral opcional).
        4. Guarda con perfil unificado.

        Returns:
            (ruta_mdt, mdt_array, transform, crs)

        Raises:
            RuntimeError: Si no se puede generar el MDT por ningún método.
            ValueError: Si el archivo de entrada no es .laz/.las.
        """
        ruta_mdt = os.path.join(
            self.proc.carpeta_mdt, f"{self.proc.nombre_base}_MDT.tif"
        )
        if os.path.exists(ruta_mdt):
            logger.info(f"Cargando MDT existente: {ruta_mdt}")
            with rasterio.open(ruta_mdt) as src:
                mdt = src.read(1, masked=True)
                mdt = np.where(mdt.mask, np.nan, mdt.data.astype(np.float32))
                transform, crs = src.transform, src.crs
            self.proc.crs, self.proc.transform = crs, transform
            mdt = self._rellenar_nan(mdt)
            return ruta_mdt, mdt, transform, crs

        # Validar formato de entrada
        if not self.proc.ruta_laz.lower().endswith((".laz", ".las")):
            raise ValueError(
                f"El archivo de entrada debe ser .laz/.las, no '{self.proc.ruta_laz}'"
            )

        fuente, es_csv, crs, xmin, ymin, xmax, ymax = self._obtener_fuente_suelo()
        self.proc.crs = crs

        res = self.proc.res
        cols = int(np.ceil((xmax - xmin) / res))
        rows = int(np.ceil((ymax - ymin) / res))
        transform = from_origin(xmin, ymax, res, res)

        # Rasterizar según el tipo de fuente
        exito = False
        metodo_interp = getattr(self.proc, "interpolation_method", INTERPOLATION_METHOD)
        if es_csv:
            exito = self._rasterizar_con_gdal_grid(
                fuente,
                xmin,
                ymax,
                cols,
                rows,
                res,
                crs,
                ruta_mdt,
                method=metodo_interp,
            )
            if not exito:
                raise RuntimeError("Fallo GDAL Grid con CSV de suelo.")
        else:
            if self.proc.usar_pdal:
                exito = self._generar_mdt_pdal(fuente, ruta_mdt)
            if not exito:
                self._generar_mdt_fallback(
                    fuente, ruta_mdt, xmin, ymax, cols, rows, transform, crs
                )
                exito = True

        if not exito:
            raise RuntimeError("No se pudo generar el MDT por ningún método.")

        # Leer el MDT recién creado
        with rasterio.open(ruta_mdt) as src:
            mdt = src.read(1, masked=True)
            mdt = np.where(mdt.mask, np.nan, mdt.data.astype(np.float32))
            transform = src.transform
        self.proc.transform = transform

        # Rellenar NaN residuales
        mdt = self._rellenar_nan(mdt)

        # Suavizado gaussiano (configurable)
        if self.proc.gaussian_blur_sigma > 0:
            try:
                from scipy.ndimage import gaussian_filter

                sigma_px = self.proc.gaussian_blur_sigma / self.proc.res
                mdt = gaussian_filter(mdt, sigma=sigma_px, mode="nearest")
                logger.info(f"Suavizado gaussiano aplicado (sigma={sigma_px:.2f} px)")
            except ImportError:
                logger.warning("SciPy no disponible, suavizado gaussiano omitido.")

        # Filtro bilateral opcional (preserva bordes)
        if getattr(self.proc, "aplicar_filtro_bilateral", False):
            try:
                from skimage.restoration import denoise_bilateral

                mdt = denoise_bilateral(
                    mdt,
                    sigma_color=BILATERAL_SIGMA_COLOR,
                    sigma_spatial=BILATERAL_SIGMA_SPATIAL,
                    channel_axis=None,
                )
                logger.info("Filtro bilateral aplicado.")
            except ImportError:
                logger.warning("scikit-image no disponible, omitiendo filtro bilateral.")

        # Guardar MDT final con perfil unificado
        perfil = perfil_derivado(
            crs,
            transform,
            mdt.shape[0],
            mdt.shape[1],
            np.float32,
            nodata=-9999.0,
        )
        with rasterio.open(ruta_mdt, "w", **perfil) as dst:
            dst.write(np.where(np.isnan(mdt), -9999.0, mdt).astype(np.float32), 1)

        logger.info(f"MDT guardado en {ruta_mdt}")
        return ruta_mdt, mdt, transform, crs

    # ------------------------------------------------------------------
    # Relleno de huecos (NaN)
    # ------------------------------------------------------------------

    def _rellenar_nan(self, mdt: np.ndarray) -> np.ndarray:
        """
        Rellena los píxeles NaN con interpolación de vecinos más cercanos.

        Args:
            mdt: Array del MDT (puede contener NaN).

        Returns:
            MDT sin NaN.
        """
        if not np.any(np.isnan(mdt)):
            return mdt
        try:
            from scipy.interpolate import NearestNDInterpolator

            nan_mask = np.isnan(mdt)
            coords = np.argwhere(~nan_mask)
            values = mdt[~nan_mask]
            interp = NearestNDInterpolator(coords, values)
            mdt[nan_mask] = interp(
                np.argwhere(nan_mask)[:, 0], np.argwhere(nan_mask)[:, 1]
            )
        except ImportError:
            # Fallback: usar la media si no hay SciPy
            mdt[np.isnan(mdt)] = np.nanmean(mdt)
        return mdt

    # ------------------------------------------------------------------
    # Limpieza de archivos temporales
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Elimina todos los archivos temporales creados."""
        for f in self.temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass
        self.temp_files.clear()