# -*- coding: utf-8 -*-
"""
Orquestador de procesamiento por tesela LiDAR (Arqueo-CID)
===========================================================

Controla el flujo completo para un único archivo LAZ:
1. Filtrado de suelo (SMRF, CSF, o sin filtro).
2. Generación del MDT (con MDTGenerator).
3. Cálculo de los derivados morfométricos mediante PytorchBackend.
4. Exportación a GeoTIFF, PNG, stack multibanda y metadatos.

Soporta procesamiento por bloques para teselas grandes y cancelación.
"""

import os
import time
import numpy as np
from typing import Dict, List, Optional, Callable, Any

# Importar la dataclass de configuración desde el módulo específico
from ...utils.processing_config import ConfiguracionProcesamiento

# Importar constantes desde la configuración central
from ...config import (
    CARPETA_MDT,
    CARPETA_DERIVADOS,
    CARPETA_IMAGENES,
    CARPETA_STACKS,
    SMRF_SCALAR_DEFAULT,
    SIGMA_CURVATURE_DEFAULT,
    RIDGE_VALLEY_RADIOS_DEFAULT,
    MRVBF_SCALES_DEFAULT,
    ETAPA_SUELO,
    ETAPA_MDT,
    ETAPA_DERIVADOS,
    ETAPA_EXPORTACION,
)

from .pytorch_backend import PytorchBackend
from .mdt_generator import MDTGenerator
from .salidas import (
    guardar_derivado_geotiff,
    exportar_imagenes,
    exportar_stack_multibanda,
    GeneradorMetadatos,
)
from ...utils.logging import get_logger

logger = get_logger('Tizona.procesador')


class ProcesadorLiDAR:
    """
    Ejecuta el flujo de procesamiento sobre una única tesela LAZ.

    Encapsula la lógica de generación de MDT, cálculo de derivados y
    exportación de resultados, respetando la configuración proporcionada
    y permitiendo cancelación y reporte de progreso.

    Attributes:
        ruta_laz (str): Ruta completa al archivo LAZ de entrada.
        carpeta_salida (str): Directorio donde se generarán las subcarpetas.
        config (ConfiguracionProcesamiento): Configuración validada.
        progress_callback (Optional[Callable]): Función para reportar progreso.
        cancel_callback (Optional[Callable]): Función que retorna True si cancelar.
        nombre_base (str): Nombre de la tesela (sin extensión).
        mdt_array (Optional[np.ndarray]): Array del MDT.
        crs: Sistema de coordenadas.
        transform: Transformación affine.
        derivados_arrays (Dict[str, np.ndarray]): Arrays de derivados.
        rutas_derivados (Dict[str, str]): Rutas de salida de derivados.
        res (float): Resolución del MDT.
        z_factor (float): Factor Z.
        radio_openness (float): Radio para Openness.
        radio_lrm (float): Radio para LRM.
        radio_tpi (List[float]): Radios para TPI.
        hillshade_multidir (bool): Hillshade multidireccional.
        angulos_multidir (List[float]): Ángulos de iluminación.
        algoritmo_suelo (str): Algoritmo de filtrado de suelo.
        usar_gpu (bool): Usar GPU.
        usar_pdal (bool): Usar PDAL.
        pdal_decimation_step (int): Diezmado PDAL.
        memoria_max_mb (int): Memoria máxima para caché.
        aplicar_filtro_mediana (bool): Aplicar filtro mediana.
        usar_clasificacion_existente (bool): Usar clase 2 del LAZ.
        gaussian_blur_sigma (float): Sigma del suavizado gaussiano.
        interpolation_method (str): Método de interpolación.
        sigma_curvature (float): Sigma para curvaturas.
        ridge_valley_radios (List[float]): Radios para ridge_valley.
        mrvbf_scales (List[float]): Escalas para MRVBF.
        smrf_params (Dict): Parámetros SMRF/CSF.
        backend (PytorchBackend): Motor de derivados.
        generador (MDTGenerator): Generador de MDT.
        carpeta_mdt (str): Subcarpeta MDT.
        carpeta_derivados (str): Subcarpeta derivados.
        carpeta_imagenes (str): Subcarpeta PNG.
        carpeta_stacks (str): Subcarpeta stacks.
    """

    def __init__(
        self,
        ruta_laz: str,
        carpeta_salida: str,
        config: ConfiguracionProcesamiento,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Args:
            ruta_laz: Ruta completa al archivo LAZ de entrada.
            carpeta_salida: Directorio donde se generarán las subcarpetas.
            config: Instancia validada de ConfiguracionProcesamiento.
            progress_callback: Función opcional (etapa, pct, msg).
            cancel_callback: Función opcional que retorna True si cancelar.
        """
        self.ruta_laz = ruta_laz
        self.carpeta_salida = carpeta_salida
        self.config = config
        self.progress_callback = progress_callback
        self.cancel_callback = cancel_callback
        self.nombre_base = os.path.splitext(os.path.basename(ruta_laz))[0]

        # Resultados intermedios
        self.mdt_array: Optional[np.ndarray] = None
        self.crs = None
        self.transform = None
        self.derivados_arrays: Dict[str, np.ndarray] = {}
        self.rutas_derivados: Dict[str, str] = {}

        # Parámetros de configuración
        self.res = config.resolucion
        self.z_factor = config.z_factor
        self.radio_openness = config.radio_openness
        self.radio_lrm = config.radio_lrm
        self.radio_tpi = config.radio_tpi_multiescala
        self.hillshade_multidir = config.multidirectional
        self.angulos_multidir = config.angulos_multidir
        self.algoritmo_suelo = config.algoritmo_suelo
        self.usar_gpu = config.usar_gpu
        self.usar_pdal = config.usar_pdal
        self.pdal_decimation_step = config.pdal_decimation_step
        self.memoria_max_mb = config.memoria_max_mb
        self.aplicar_filtro_mediana = config.aplicar_filtro_mediana
        self.usar_clasificacion_existente = config.usar_clasificacion_existente
        self.gaussian_blur_sigma = config.gaussian_blur_sigma
        self.interpolation_method = config.interpolation_method

        # Parámetros específicos de derivados
        self.sigma_curvature = getattr(config, "sigma_curvature", SIGMA_CURVATURE_DEFAULT)
        self.ridge_valley_radios = getattr(config, "ridge_valley_radios", RIDGE_VALLEY_RADIOS_DEFAULT)
        self.mrvbf_scales = getattr(config, "mrvbf_scales", MRVBF_SCALES_DEFAULT)

        # Parámetros SMRF/CSF
        self.smrf_params = {
            "window": config.smrf_window,
            "slope": config.smrf_slope,
            "threshold": config.smrf_threshold,
            "scalar": SMRF_SCALAR_DEFAULT,
        }

        # Backend y generador
        self.backend = PytorchBackend(self)
        self.generador = MDTGenerator(self)

        # Crear estructura de carpetas
        self._crear_directorios()

    # ------------------------------------------------------------------
    # Inicialización de directorios
    # ------------------------------------------------------------------

    def _crear_directorios(self) -> None:
        """Crea las subcarpetas de salida usando las constantes de config.py."""
        self.carpeta_mdt = os.path.join(self.carpeta_salida, CARPETA_MDT)
        self.carpeta_derivados = os.path.join(self.carpeta_salida, CARPETA_DERIVADOS)
        self.carpeta_imagenes = os.path.join(self.carpeta_salida, CARPETA_IMAGENES)
        self.carpeta_stacks = os.path.join(self.carpeta_salida, CARPETA_STACKS)
        for d in [self.carpeta_mdt, self.carpeta_derivados, self.carpeta_imagenes, self.carpeta_stacks]:
            os.makedirs(d, exist_ok=True)
            logger.debug(f"Directorio creado/verificado: {d}")

    # ------------------------------------------------------------------
    # Control de cancelación y progreso
    # ------------------------------------------------------------------

    def _is_canceled(self) -> bool:
        """Verifica si se ha solicitado cancelación."""
        if self.cancel_callback:
            return self.cancel_callback()
        return False

    def _report_progress(self, etapa: str, pct: int, msg: str = "") -> None:
        """Reporta progreso a través del callback."""
        if self.progress_callback:
            self.progress_callback(etapa, pct, msg)

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------

    def bbox(self) -> Optional[List[float]]:
        """
        Devuelve el bounding box del MDT generado.

        Returns:
            [xmin, ymin, xmax, ymax] en CRS del MDT, o None si no hay MDT.
        """
        if self.mdt_array is not None and self.transform is not None:
            h, w = self.mdt_array.shape
            xmin, ymax = self.transform * (0, 0)
            xmax, ymin = self.transform * (w, h)
            return [xmin, ymin, xmax, ymax]
        return None

    def ejecutar_pipeline_completo(self) -> None:
        """
        Ejecuta secuencialmente las etapas del pipeline.

        Raises:
            InterruptedError: Si el proceso es cancelado.
        """
        inicio = time.time()
        logger.info(f"Iniciando procesamiento de {self.nombre_base}")

        # 1. Generar MDT
        self._report_progress(ETAPA_SUELO, 10, "Filtrando suelo...")
        self._generar_mdt()
        self._report_progress(ETAPA_MDT, 60, "MDT generado")

        # 2. Calcular derivados
        self._calcular_derivados()
        self._report_progress(ETAPA_DERIVADOS, 80, "Derivados calculados")

        # 3. Exportar resultados
        duracion_total = time.time() - inicio
        self._exportar_resultados(duracion_total)
        self._report_progress(ETAPA_EXPORTACION, 100, "Procesamiento completado")

        # Limpiar temporales
        self.generador.cleanup()
        logger.info(f"Tesela {self.nombre_base} procesada en {duracion_total:.1f}s")

    # ------------------------------------------------------------------
    # Generación del MDT
    # ------------------------------------------------------------------

    def _generar_mdt(self) -> None:
        """
        Genera el MDT y almacena array, CRS y transformación.
        """
        if self._is_canceled():
            raise InterruptedError("Cancelado por el usuario")
        ruta_mdt, mdt, transform, crs = self.generador.generar_mdt()
        self.mdt_array = mdt
        self.crs = crs
        self.transform = transform
        logger.info(f"MDT listo para {self.nombre_base}: {mdt.shape}, res {self.res}m")

    # ------------------------------------------------------------------
    # Cálculo de derivados
    # ------------------------------------------------------------------

    def _calcular_derivados(self) -> None:
        """Calcula todos los derivados activos en la configuración."""
        metodos: Dict[str, Callable[[np.ndarray], Optional[np.ndarray]]] = {
            "hillshade": lambda z: self.backend.hillshade(
                z, self.z_factor, self.angulos_multidir, self.hillshade_multidir
            ),
            "slope": self.backend.slope,
            "aspect_sin": self.backend.aspect_sin,
            "aspect_cos": self.backend.aspect_cos,
            "curvature": self.backend.curvature,
            "curvature_vert": self.backend.curvature_vert,
            "curvature_horiz": self.backend.curvature_horiz,
            "tpi": lambda z: self.backend.tpi_multiescala(z, self.radio_tpi),
            "lrm": lambda z: self.backend.local_relief_model(z, self.radio_lrm),
            "ridge_valley": lambda z: self.backend.ridge_valley(z, self.ridge_valley_radios),
            "openness_pos": lambda z: self.backend.openness(z, self.radio_openness, positive=True),
            "openness_neg": lambda z: self.backend.openness(z, self.radio_openness, positive=False),
            "openness_aniso": lambda z: self.backend.openness_anisotropic(z, self.radio_openness),
            "sky_view_factor": self.backend.sky_view_factor,
            "mrvbf": lambda z: self.backend.mrvbf(z, scales=self.mrvbf_scales),
        }

        total = len(self.config.derivados)
        for i, nombre in enumerate(self.config.derivados):
            if self._is_canceled():
                raise InterruptedError("Cancelado por el usuario")
            if nombre in metodos:
                self._report_progress(ETAPA_DERIVADOS, int((i / total) * 100), f"Calculando {nombre}")
                try:
                    arr = metodos[nombre](self.mdt_array)
                    if arr is not None:
                        self.derivados_arrays[nombre] = arr
                    else:
                        logger.warning(f"Derivado '{nombre}' devolvió None")
                except Exception as e:
                    logger.error(f"Error calculando '{nombre}': {e}", exc_info=True)
            else:
                logger.warning(f"Derivado '{nombre}' no reconocido, se omite.")

    # ------------------------------------------------------------------
    # Exportación de resultados
    # ------------------------------------------------------------------

    def _exportar_resultados(self, tiempo_procesamiento: float) -> None:
        """
        Exporta MDT, derivados GeoTIFF, PNG, stack y metadatos.

        Args:
            tiempo_procesamiento: Duración total del pipeline en segundos.
        """
        if self._is_canceled():
            raise InterruptedError("Cancelado por el usuario")

        # Guardar derivados GeoTIFF
        self.rutas_derivados = {}
        for nombre, arr in self.derivados_arrays.items():
            ruta = os.path.join(self.carpeta_derivados, f"{self.nombre_base}_{nombre}.tif")
            guardar_derivado_geotiff(
                arr,
                ruta,
                self.crs,
                self.transform,
                aplicar_filtro_mediana=self.aplicar_filtro_mediana,
                tipo_derivado=nombre,
            )
            self.rutas_derivados[nombre] = ruta
            logger.debug(f"Derivado guardado: {ruta}")

        # Exportar PNG
        if self.config.generar_imagenes_png:
            exportar_imagenes(
                self,
                self.rutas_derivados,
                self.carpeta_imagenes,
                self.nombre_base,
                normalizar=self.config.normalizar_imagenes,
                perc_low=self.config.png_perc_low,
                perc_high=self.config.png_perc_high,
                progress_callback=self.progress_callback,
            )

        # Exportar stack multibanda
        ruta_stack = None
        percentiles_ia = None
        if self.config.exportar_stack:
            bandas_stack = list(self.rutas_derivados.keys())
            ruta_stack, percentiles_ia = exportar_stack_multibanda(
                self.rutas_derivados,
                self.carpeta_stacks,
                self.nombre_base,
                bandas=bandas_stack,
                normalizar=self.config.normalizar_stack,
                perc_low=self.config.stack_perc_low,
                perc_high=self.config.stack_perc_high,
                incluir_mascara=self.config.incluir_mascara_stack,
                progress_callback=self.progress_callback,
            )

        # Generar metadatos JSON
        if self.config.generar_metadatos_json:
            GeneradorMetadatos.generar(
                self,
                self.rutas_derivados,
                tiempo_procesamiento,
                stack_ia_ruta=ruta_stack,
                percentiles_ia=percentiles_ia,
                actualizar_manifiesto=self.config.generar_manifiesto_ia,
            )

        logger.info(f"Exportación completada para {self.nombre_base}")