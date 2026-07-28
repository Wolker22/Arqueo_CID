# -*- coding: utf-8 -*-
"""
Tarea de predicción (inferencia) de COLADA
===========================================

Ejecuta la predicción de anomalías sobre múltiples stacks GeoTIFF
en segundo plano, soportando VAE e Isolation Forest.

Características:
- Procesamiento paralelo de teselas (hilos CPU/GPU).
- Cancelación segura.
- Progreso global ponderado por tesela.
- Carga automática de resultados en QGIS al finalizar.
"""

import os
import time
import threading
import gc
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from typing import List, Dict, Any, Optional, Tuple, Callable

import numpy as np
import torch

from qgis.core import (
    QgsTask,
    Qgis,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsRasterBandStats,
    QgsContrastEnhancement,
    QgsSingleSymbolRenderer,
    QgsFillSymbol,
)
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ...utils.logging import get_logger
from ...core.core_postprocesado.predictor import (
    cargar_modelo_vae,
    leer_stack_multibanda,
    extraer_parches_generator,
    inferir_y_reconstruir,
    suavizar_y_umbralizar,
    guardar_raster,
    vectorizar_anomalias,
    predecir_anomalia_isolation_forest,
)
from ...config import (
    TAMANO_PARCHE,
    SOLAPAMIENTO,
    SIGMA_GAUSSIANO,
    UMBRAL_PERCENTIL,
    TAMANIO_LOTE,
    MAX_GPU_WORKERS,
    CPU_WORKERS,
    VENTANA_ADAPTATIVA,
    ASPECT_RATIO_MAX,
    CIRCULARITY_MIN,
    MIN_AREA_ANOMALIA_M2,
    PREDICCION_TAREA_NOMBRE,
    PREDICCION_MENSAJE_CANCELADA,
    PREDICCION_MENSAJE_COMPLETADA,
    PREDICCION_MENSAJE_FINALIZADA,
    PREDICCION_MENSAJE_SIN_RESULTADOS,
    PREDICCION_NOMBRE_CAPA_ANOMALIA,
    PREDICCION_NOMBRE_CAPA_CANDIDATOS,
    PREDICCION_ANOMALIA_OPACIDAD,
    PREDICCION_COLORES_RAMPA,
    PREDICCION_ETIQUETAS_RAMPA,
    PREDICCION_CANDIDATO_COLOR,
    PREDICCION_CANDIDATO_OUTLINE_COLOR,
    PREDICCION_CANDIDATO_OUTLINE_WIDTH,
    PREDICCION_MIN_AREA_M2_DEFAULT,
    PREDICCION_IF_N_ESTIMATORS_DEFAULT,
    PREDICCION_IF_CONTAMINATION_DEFAULT,
    PREDICCION_IF_MAX_SAMPLES_DEFAULT,
)

logger = get_logger('Colada.tasks.prediccion')


# ============================================================================
# Funciones auxiliares de estilo
# ============================================================================

def _aplicar_estilo_mapa_anomalia(capa: QgsRasterLayer) -> None:
    """
    Aplica una rampa de color azul‑rojo al ráster de anomalías.

    Args:
        capa: Capa raster de anomalías.
    """
    provider = capa.dataProvider()
    if not provider:
        return

    stats = provider.bandStatistics(1, QgsRasterBandStats.All, capa.extent(), 250000)
    min_val = stats.minimumValue
    max_val = stats.maximumValue
    if min_val == max_val:
        min_val = 0.0
        max_val = 1.0

    shader = QgsColorRampShader()
    shader.setColorRampType(QgsColorRampShader.Interpolated)

    rng = max_val - min_val
    items = []
    for i, (rgb, label) in enumerate(zip(PREDICCION_COLORES_RAMPA, PREDICCION_ETIQUETAS_RAMPA)):
        value = min_val + rng * i / (len(PREDICCION_COLORES_RAMPA) - 1.0)
        color = QColor(*rgb)
        items.append(QgsColorRampShader.ColorRampItem(value, color, label))

    shader.setColorRampItemList(items)
    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(shader)
    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
    renderer.setOpacity(PREDICCION_ANOMALIA_OPACIDAD)
    capa.setRenderer(renderer)

    enhancement = QgsContrastEnhancement()
    enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
    enhancement.setMinimumValue(min_val)
    enhancement.setMaximumValue(max_val)
    capa.setContrastEnhancement(enhancement)
    capa.triggerRepaint()


def _aplicar_estilo_candidatos(capa: QgsVectorLayer) -> None:
    """
    Aplica estilo a la capa de polígonos candidatos.

    Args:
        capa: Capa vectorial de polígonos.
    """
    symbol = QgsFillSymbol.createSimple({
        "color": PREDICCION_CANDIDATO_COLOR,
        "outline_color": PREDICCION_CANDIDATO_OUTLINE_COLOR,
        "outline_width": PREDICCION_CANDIDATO_OUTLINE_WIDTH,
    })
    capa.setRenderer(QgsSingleSymbolRenderer(symbol))
    if capa.isValid():
        capa.triggerRepaint()


# ============================================================================
# Worker para una sola tesela
# ============================================================================

def _predecir_tesela_worker(
    ruta_stack: str,
    nombre: str,
    carpeta_salida: str,
    modelo: Optional[torch.nn.Module],
    modelo_lock: Optional[threading.Lock],
    config_pred: Dict[str, Any],
    cancel_event: threading.Event,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    archivos_entrenamiento: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[Dict[str, str]], float]:
    """
    Procesa una única tesela (stack) para predicción de anomalías.

    Args:
        ruta_stack: Ruta al stack GeoTIFF.
        nombre: Nombre de la tesela.
        carpeta_salida: Carpeta donde guardar resultados.
        modelo: Modelo VAE (si aplica, None para Isolation Forest).
        modelo_lock: Lock para acceso al modelo (thread-safe).
        config_pred: Configuración de predicción.
        cancel_event: Evento de cancelación.
        progress_callback: Callback para reportar progreso (porcentaje, mensaje).
        archivos_entrenamiento: Lista de stacks de entrenamiento (para Isolation Forest).

    Returns:
        (éxito, mensaje, paths, duración_segundos) donde paths es dict con 'tif' y/o 'geojson'.
    """
    if cancel_event.is_set():
        return False, f"{nombre}: Cancelado", None, 0.0

    t_inicio = time.time()
    try:
        if progress_callback:
            progress_callback(0, "Iniciando lectura...")

        array, geotrans, (cols, filas), proj = leer_stack_multibanda(ruta_stack)
        modelo_tipo = config_pred.get("modelo", "vae")

        sigma = config_pred.get("sigma_gaussiano", SIGMA_GAUSSIANO)
        umbral = config_pred.get("umbral_percentil", UMBRAL_PERCENTIL)
        exportar_tif = config_pred.get("exportar_tif", True)
        exportar_geojson = config_pred.get("exportar_geojson", True)
        min_area_m2 = config_pred.get("min_area_m2", PREDICCION_MIN_AREA_M2_DEFAULT)
        ventana_adapt = config_pred.get("ventana_adaptativa", VENTANA_ADAPTATIVA)

        # Isolation Forest
        if modelo_tipo == "isolation_forest":
            if archivos_entrenamiento is None:
                raise ValueError("Faltan archivos de entrenamiento para Isolation Forest.")

            def if_progress_callback(pct: int, msg: str) -> None:
                if progress_callback:
                    progress_callback(pct, msg)

            mapa_suave = predecir_anomalia_isolation_forest(
                ruta_stack,
                archivos_entrenamiento,
                sigma=sigma,
                umbral_pct=umbral,
                min_area_m2=min_area_m2,
                n_estimators=config_pred.get("if_n_estimators", PREDICCION_IF_N_ESTIMATORS_DEFAULT),
                contamination=config_pred.get("if_contamination", PREDICCION_IF_CONTAMINATION_DEFAULT),
                max_samples=config_pred.get("if_max_samples", PREDICCION_IF_MAX_SAMPLES_DEFAULT),
                progress_callback=if_progress_callback,
                cancel_event=cancel_event,
            )
            mapa_binario = (mapa_suave >= np.percentile(mapa_suave, umbral)).astype(np.uint8)

        # VAE
        else:
            dispositivo = config_pred.get("dispositivo", "cpu")
            tamanio_parche = config_pred.get("tamanio_parche", TAMANO_PARCHE)
            solapamiento = config_pred.get("solapamiento", SOLAPAMIENTO)
            tamanio_lote = config_pred.get("tamanio_lote", TAMANIO_LOTE)
            norm_params = config_pred.get("norm_params", None)

            with modelo_lock if modelo_lock else threading.Lock():
                if cancel_event.is_set():
                    raise InterruptedError()

                parches_gen = extraer_parches_generator(
                    array,
                    tamanio=tamanio_parche,
                    solape=solapamiento,
                    norm_params=norm_params,
                )

                def inferencia_callback(pct: int) -> None:
                    if progress_callback:
                        mapped = int(10 + pct * 0.7)
                        progress_callback(mapped, f"Parches VAE: {pct}%")

                mapa_anomalia = inferir_y_reconstruir(
                    modelo,
                    parches_gen,
                    (filas, cols),
                    dispositivo,
                    tamanio_lote=tamanio_lote,
                    callback=inferencia_callback,
                    cancel_event=cancel_event,
                )

            if progress_callback:
                progress_callback(85, "Suavizando matriz topológica...")
            mapa_suave, mapa_binario = suavizar_y_umbralizar(
                mapa_anomalia,
                sigma=sigma,
                umbral_pct=umbral,
                ventana_adaptativa=ventana_adapt,
            )

        if cancel_event.is_set():
            raise InterruptedError()

        if progress_callback:
            progress_callback(90, "Escribiendo formatos GIS...")

        os.makedirs(carpeta_salida, exist_ok=True)
        paths: Dict[str, str] = {}

        if exportar_tif:
            ruta_tif = os.path.join(carpeta_salida, f"{nombre}_anomalia.tif")
            guardar_raster(mapa_suave, ruta_tif, geotrans, proj, cols, filas)
            paths["tif"] = ruta_tif

        if exportar_geojson:
            ruta_geojson = os.path.join(carpeta_salida, f"{nombre}_candidatos.geojson")
            vectorizar_anomalias(
                mapa_binario,
                ruta_geojson,
                geotrans,
                proj,
                min_area_m2=min_area_m2,
                aspect_ratio_max=config_pred.get("aspect_ratio_max", ASPECT_RATIO_MAX),
                circularity_min=config_pred.get("circularity_min", CIRCULARITY_MIN),
            )
            paths["geojson"] = ruta_geojson

        if progress_callback:
            progress_callback(100, "Completado")

        duracion = time.time() - t_inicio
        gc.collect()
        return True, nombre, paths, duracion

    except Exception as e:
        logger.error(f"Error en predicción de {nombre}: {e}", exc_info=True)
        if progress_callback:
            progress_callback(0, f"Error: {str(e)}")
        return False, f"{nombre}: {str(e)}", None, 0.0


# ============================================================================
# Tarea principal de predicción
# ============================================================================

class TareaPrediccion(QgsTask):
    """
    Tarea QGIS para ejecutar predicción de anomalías sobre múltiples teselas.

    Attributes:
        nombres: Lista de nombres de tesela.
        rutas_stacks: Lista de rutas a stacks (opcional, si se proporciona).
        carpeta_stacks: Directorio con stacks (si no se dan rutas individuales).
        carpeta_resultados: Carpeta base para guardar resultados.
        ruta_modelo: Ruta al modelo VAE (si aplica).
        config: Diccionario de configuración.
        dialog: Diálogo de progreso.
        archivos_entrenamiento: Lista de stacks de entrenamiento (para IF).
        dispositivo: 'cpu' o 'cuda'.
        max_hilos: Número máximo de hilos paralelos.
        cancel_event: Evento de cancelación.
        procesados: Contador de teselas procesadas con éxito.
        _total_validos: Número total de teselas válidas.
        _output_paths: Diccionario con rutas de resultados por tesela.
        modelo: Modelo VAE (si aplica).
        modelo_lock: Lock para acceso al modelo.
        _executor: Executor de hilos.
        lock_progreso: Lock para actualizar progreso global.
        progreso_teselas: Diccionario con progreso por tesela.
    """

    def __init__(
        self,
        nombres_teselas: List[str],
        carpeta_resultados: str,
        ruta_modelo: str,
        config_pred: Dict[str, Any],
        progress_dialog: Optional[Any] = None,
        carpeta_stacks: Optional[str] = None,
        rutas_stacks: Optional[List[str]] = None,
        archivos_entrenamiento: Optional[List[str]] = None,
    ) -> None:
        """
        Args:
            nombres_teselas: Lista de nombres de tesela.
            carpeta_resultados: Carpeta base para guardar resultados.
            ruta_modelo: Ruta al modelo VAE (.pth).
            config_pred: Configuración de predicción.
            progress_dialog: Diálogo de progreso.
            carpeta_stacks: Directorio con stacks (si no se dan rutas individuales).
            rutas_stacks: Lista de rutas a stacks (opcional, si se proporciona directamente).
            archivos_entrenamiento: Lista de stacks para entrenamiento de IF.
        """
        super().__init__(PREDICCION_TAREA_NOMBRE, QgsTask.CanCancel)
        self.nombres: List[str] = nombres_teselas
        self.rutas_stacks: Optional[List[str]] = rutas_stacks
        self.carpeta_stacks: Optional[str] = carpeta_stacks
        self.carpeta_resultados: str = carpeta_resultados
        self.ruta_modelo: str = ruta_modelo
        self.config: Dict[str, Any] = config_pred
        self.dialog: Optional[Any] = progress_dialog
        self.archivos_entrenamiento: Optional[List[str]] = archivos_entrenamiento

        self.dispositivo: str = config_pred.get("dispositivo", "cpu")
        if self.dispositivo == "cuda":
            max_hilos = config_pred.get("max_gpu_workers", MAX_GPU_WORKERS)
        else:
            max_hilos = config_pred.get("cpu_workers_pred", CPU_WORKERS)
        self.max_hilos: int = max_hilos if max_hilos > 0 else 1

        self.cancel_event: threading.Event = threading.Event()
        self.procesados: int = 0
        self.errores: List[str] = []
        self._total_validos: int = 0
        self._output_paths: Dict[str, Dict[str, str]] = {}
        self.modelo: Optional[torch.nn.Module] = None
        self.modelo_lock: Optional[threading.Lock] = None
        self._executor: Optional[ThreadPoolExecutor] = None

        # Progreso ponderado por tesela
        self.lock_progreso: threading.Lock = threading.Lock()
        self.progreso_teselas: Dict[str, int] = {nombre: 0 for nombre in self.nombres}

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """Ejecuta la predicción sobre todas las teselas."""
        self.log_info(f"Predicción sobre {len(self.nombres)} tesela(s), max workers={self.max_hilos}")

        modelo_tipo = self.config.get("modelo", "vae")

        # Cargar modelo VAE si es necesario
        if modelo_tipo != "isolation_forest":
            try:
                self.modelo, meta, norm_params = cargar_modelo_vae(self.ruta_modelo, self.dispositivo)
                self.modelo_lock = threading.Lock()
                self.config["norm_params"] = norm_params
                _, _, _, patch_modelo = meta
                tamanio_parche_conf = self.config.get("tamanio_parche", TAMANO_PARCHE)
                if patch_modelo != tamanio_parche_conf:
                    self.log_info(f"Ajustando parche al modelo: {patch_modelo} px")
                    self.config["tamanio_parche"] = patch_modelo
            except Exception as e:
                self.log_error(f"No se pudo cargar el modelo VAE: {e}")
                return False
        else:
            self.modelo = None
            self.modelo_lock = None
            self.log_info("Usando Isolation Forest de scikit-learn")

        # Preparar lista de tareas (nombre, ruta)
        tareas: List[Tuple[str, str]] = []
        if self.rutas_stacks is not None and len(self.rutas_stacks) == len(self.nombres):
            for nombre, ruta in zip(self.nombres, self.rutas_stacks):
                if os.path.exists(ruta):
                    tareas.append((nombre, ruta))
                else:
                    self.errores.append(f"{nombre}: archivo no encontrado")
                    if self.dialog:
                        self.dialog.actualizar_fila(nombre, "Archivo no encontrado", 0)
        else:
            if not self.carpeta_stacks:
                self.log_error("Falta ruta o directorio origen de teselas.")
                return False
            for nombre in self.nombres:
                ruta = os.path.join(self.carpeta_stacks, f"{nombre}.tif")
                if os.path.exists(ruta):
                    tareas.append((nombre, ruta))
                else:
                    self.errores.append(f"{nombre}: no encontrado")
                    if self.dialog:
                        self.dialog.actualizar_fila(nombre, "No encontrado", 0)

        self._total_validos = len(tareas)
        if self._total_validos == 0:
            self.log_error("Ninguna tesela ráster es válida para inferencia.")
            return False

        # Inicializar diálogo de progreso
        if self.dialog:
            for nombre, _ in tareas:
                self.dialog.actualizar_fila(nombre, "En cola (Pendiente)", 0)
            self.dialog.actualizar_global(0, "Repartiendo carga en hilos CPU/GPU...")

        # Ejecutar predicción (secuencial o paralela)
        if self.max_hilos == 1:
            for nombre, ruta in tareas:
                if self.cancel_event.is_set():
                    break
                carpeta_salida = os.path.join(self.carpeta_resultados, nombre)

                def progress_cb(pct: int, msg: Optional[str] = None, n: str = nombre) -> None:
                    self._actualizar_progreso_dinamico(n, pct, msg)

                exito, msg, paths, dur = _predecir_tesela_worker(
                    ruta, nombre, carpeta_salida, self.modelo, self.modelo_lock,
                    self.config, self.cancel_event, progress_cb,
                    archivos_entrenamiento=self.archivos_entrenamiento,
                )
                self._procesar_resultado(exito, nombre, msg, paths, dur)
        else:
            self._executor = ThreadPoolExecutor(max_workers=self.max_hilos)
            futures = {}
            for nombre, ruta in tareas:
                if self.cancel_event.is_set():
                    break
                carpeta_salida = os.path.join(self.carpeta_resultados, nombre)

                def progress_cb(pct: int, msg: Optional[str] = None, n: str = nombre) -> None:
                    self._actualizar_progreso_dinamico(n, pct, msg)

                fut = self._executor.submit(
                    _predecir_tesela_worker,
                    ruta, nombre, carpeta_salida, self.modelo, self.modelo_lock,
                    self.config, self.cancel_event, progress_cb,
                    archivos_entrenamiento=self.archivos_entrenamiento,
                )
                futures[fut] = nombre

            # Esperar a que terminen todos los futuros
            for fut in futures_wait(futures, return_when='ALL_COMPLETED')[0]:
                nombre = futures[fut]
                try:
                    exito, msg, paths, dur = fut.result(timeout=0.1)
                except Exception as e:
                    exito, msg, paths, dur = False, str(e), None, 0.0
                self._procesar_resultado(exito, nombre, msg, paths, dur)
                if self.cancel_event.is_set():
                    break

            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None

        self.log_info(f"Predicción finalizada. Procesadas con éxito: {self.procesados}/{self._total_validos}")
        return self.procesados > 0

    # ------------------------------------------------------------------
    # Gestión de progreso
    # ------------------------------------------------------------------

    def _actualizar_progreso_dinamico(self, nombre: str, pct: int, msg: Optional[str]) -> None:
        """
        Actualiza el progreso de una tesela y recalcula el progreso global.

        Args:
            nombre: Nombre de la tesela.
            pct: Porcentaje de progreso local (0-100).
            msg: Mensaje de estado opcional.
        """
        with self.lock_progreso:
            self.progreso_teselas[nombre] = pct
            suma_total = sum(self.progreso_teselas.values())
            pct_global = int(suma_total / self._total_validos) if self._total_validos else 0

        if self.dialog:
            self.dialog.actualizar_fila(nombre, msg or f"Procesando... {pct}%", pct)
            self.dialog.actualizar_global(
                pct_global,
                f"Procesando: {pct_global}% ({self.procesados}/{self._total_validos} terminadas)"
            )

    def _procesar_resultado(self, exito: bool, nombre: str, msg: str, paths: Optional[Dict[str, str]], dur: float) -> None:
        """
        Procesa el resultado de una tesela (éxito o error).

        Args:
            exito: True si la tesela se procesó correctamente.
            nombre: Nombre de la tesela.
            msg: Mensaje (nombre en caso de éxito, error en caso contrario).
            paths: Diccionario con rutas de resultados (si éxito).
            dur: Duración del procesamiento (segundos).
        """
        if exito:
            self.procesados += 1
            self._output_paths[nombre] = paths or {}
            if self.dialog:
                self.dialog.actualizar_fila(nombre, "Completado con éxito", 100)
        else:
            self.errores.append(msg)
            if self.dialog:
                self.dialog.actualizar_fila(nombre, f"Error: {msg}", 0)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_info(self, msg: str) -> None:
        """Registra un mensaje de nivel INFO."""
        if self.dialog:
            self.dialog.log_info(msg)
        logger.info(msg)

    def log_error(self, msg: str) -> None:
        """Registra un mensaje de nivel ERROR."""
        if self.dialog:
            self.dialog.log_error(msg)
        logger.error(msg)

    # ------------------------------------------------------------------
    # Cancelación
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Solicita la cancelación de la tarea."""
        self.cancel_event.set()
        if self._executor:
            self._executor.shutdown(wait=False)
        super().cancel()

    # ------------------------------------------------------------------
    # Finalización
    # ------------------------------------------------------------------

    def finished(self, result: bool) -> None:
        """Maneja la finalización de la tarea y carga los resultados en QGIS."""
        if self.dialog:
            if self.isCanceled():
                self.dialog.finalizar(False, PREDICCION_MENSAJE_CANCELADA)
            elif result:
                self.dialog.finalizar(True, PREDICCION_MENSAJE_FINALIZADA)
            else:
                self.dialog.finalizar(False, PREDICCION_MENSAJE_SIN_RESULTADOS)

        if not result and not self.isCanceled():
            iface.messageBar().pushMessage("COLADA", PREDICCION_MENSAJE_SIN_RESULTADOS, level=Qgis.Critical)
        elif result and not self.isCanceled():
            iface.messageBar().pushMessage(
                "COLADA",
                PREDICCION_MENSAJE_COMPLETADA.format(self.procesados),
                level=Qgis.Success,
            )

            # Cargar resultados en el mapa
            for nombre, paths in self._output_paths.items():
                if "tif" in paths and os.path.exists(paths["tif"]):
                    capa_rast = iface.addRasterLayer(paths["tif"], PREDICCION_NOMBRE_CAPA_ANOMALIA.format(nombre))
                    if capa_rast and capa_rast.isValid():
                        _aplicar_estilo_mapa_anomalia(capa_rast)
                        capa_rast.triggerRepaint()
                if "geojson" in paths and os.path.exists(paths["geojson"]):
                    capa_vect = iface.addVectorLayer(
                        paths["geojson"],
                        PREDICCION_NOMBRE_CAPA_CANDIDATOS.format(nombre),
                        "ogr"
                    )
                    if capa_vect and capa_vect.isValid():
                        _aplicar_estilo_candidatos(capa_vect)
                        capa_vect.triggerRepaint()