# -*- coding: utf-8 -*-
"""
COLADA – Detección Arqueológica mediante LiDAR e Inteligencia Artificial
Submódulo de postprocesado del proyecto Arqueo Cid.

Expone el método público run_colada() para que el plugin paraguas
(ArqueoCidPlugin) lo invoque cuando el usuario elija Colada.

Acepta una ruta inicial para precargar la carpeta de resultados de Tizona
(útil cuando se abre desde el diálogo de progreso de Tizona).
MODIFICACIÓN: Acepta también una lista opcional de nombres de tesela
para cargar solo esas en lugar de todas las encontradas.
"""

import os
import json
from qgis.core import QgsApplication, Qgis, QgsProject, QgsSettings
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ..utils.logging import get_logger
from ..gui.gui_postprocesado.dialogoPrincipal import DialogoPrincipal
from ..gui.gui_postprocesado.dialogoProgreso import ProgresoCOLADA
from .tasks.pipeline_prediccion import TareaPrediccion
from .tasks.pipeline_entrenamiento import lanzar_entrenamiento
from ..core.core_postprocesado.tizona_integration import recolectar_stacks_por_tesela

# Usar el logger 'Colada' (el mapeo lo dirigirá al logger principal 'Colada')
logger = get_logger('Colada')


class ColadaPlugin:
    """
    Motor de postprocesado con IA – Colada.

    El plugin paraguas (Arqueo Cid) instancia esta clase y llama a
    run_colada() cuando el usuario solicita el postprocesado.
    """

    def __init__(self, iface):
        self.iface = iface
        self.dialogo_progreso = None
        self.carpeta_resultados_actual = None
        # ¡CRÍTICO! Retener el diálogo principal en memoria para que Python no lo destruya
        self.dialogo_principal = None

    # ------------------------------------------------------------------
    # Punto de entrada principal (nueva interfaz unificada)
    # ------------------------------------------------------------------
    def run_colada(self, ruta_inicial=None, nombres_teselas=None):
        """
        Abre el nuevo diálogo principal de Colada.

        Args:
            ruta_inicial: Ruta opcional a la carpeta de resultados de Tizona
                          para precargar en el selector de datos.
            nombres_teselas: Lista opcional de nombres de tesela a cargar.
                             Si se proporciona, solo esos se mostrarán en el combo.
        """
        # Usamos self para evitar que el Garbage Collector borre la lógica de los botones
        self.dialogo_principal = DialogoPrincipal(self.iface.mainWindow())
        if ruta_inicial:
            self.dialogo_principal.establecer_carpeta_tizona(ruta_inicial, nombres_teselas)
        self.dialogo_principal.show()  # no modal, permite interactuar con QGIS

    # ------------------------------------------------------------------
    # Métodos legacy (entrenamiento y predicción antiguos).
    # Se conservan por si se necesitan desde el diálogo de progreso.
    # ------------------------------------------------------------------
    def _lanzar_entrenamiento(self, dialogo):
        params_entrenamiento, _, params_tecnico = dialogo.obtener_parametros()
        archivos = params_entrenamiento.get('archivos_entrenamiento', [])
        archivos_validos = [f for f in archivos if os.path.exists(f)]
        if not archivos_validos:
            QMessageBox.warning(self.iface.mainWindow(), "Archivos no encontrados",
                                "Ninguno de los archivos de entrenamiento existe.")
            return

        ruta_salida = params_entrenamiento.get('ruta_salida', '')
        if not ruta_salida:
            QMessageBox.warning(self.iface.mainWindow(), "Configuración incompleta",
                                "Debe especificar la ruta de salida del modelo.")
            return

        self.dialogo_progreso = ProgresoCOLADA(modo='training', parent=self.iface.mainWindow())
        self.dialogo_progreso.show()

        config_entrenamiento = params_entrenamiento.copy()
        config_entrenamiento['dispositivo'] = config_entrenamiento.get('dispositivo', 'cpu')
        self._guardar_ultima_config_entrenamiento(params_entrenamiento, params_tecnico)

        tarea = lanzar_entrenamiento(
            archivos=archivos_validos, ruta_modelo=ruta_salida,
            config=config_entrenamiento, dialog=self.dialogo_progreso
        )
        tarea.taskCompleted.connect(self._on_entrenamiento_completado)
        tarea.taskTerminated.connect(self._on_entrenamiento_terminado)
        QgsApplication.taskManager().addTask(tarea)
        self.iface.messageBar().pushMessage("COLADA", "Entrenamiento iniciado en segundo plano.", level=Qgis.Info)

    def _lanzar_prediccion(self, dialogo):
        _, params_prediccion, params_tecnico = dialogo.obtener_parametros()
        modelo_seleccionado = params_prediccion.get('modelo', 'vae')

        if not params_prediccion.get('carpeta_stacks') or not params_prediccion.get('carpeta_resultados'):
            QMessageBox.warning(self.iface.mainWindow(), "Configuración incompleta",
                                "Debe especificar:\n- Carpeta de stacks procesados\n- Carpeta de resultados\n")
            return

        if modelo_seleccionado != 'isolation_forest' and not params_prediccion.get('ruta_modelo'):
            QMessageBox.warning(self.iface.mainWindow(), "Configuración incompleta",
                                "Debe especificar el archivo del modelo entrenado (.pth).")
            return

        self.dialogo_progreso = ProgresoCOLADA(modo='prediction', parent=self.iface.mainWindow())
        self.dialogo_progreso.show()

        carpeta = params_prediccion['carpeta_stacks']
        if os.path.basename(carpeta) == '04_IA_STACKS':
            carpeta_stacks_directa = carpeta
            nombres_teselas, rutas_stacks = None, None
        else:
            stacks_por_tesela = recolectar_stacks_por_tesela(carpeta)
            if stacks_por_tesela:
                self.dialogo_progreso.log_info(f"Modo Tizona: se procesarán {len(stacks_por_tesela)} teselas.")
                nombres_teselas = list(stacks_por_tesela.keys())
                rutas_stacks = list(stacks_por_tesela.values())
                carpeta_stacks_directa = None
            else:
                carpeta_stacks_directa = carpeta
                nombres_teselas, rutas_stacks = None, None

        if nombres_teselas is None:
            try:
                archivos = os.listdir(carpeta)
                nombres_teselas = sorted({os.path.splitext(f)[0] for f in archivos if f.lower().endswith('.tif')})
                if not nombres_teselas:
                    raise FileNotFoundError("No se encontraron archivos .tif")
                rutas_stacks = [os.path.join(carpeta, f"{n}.tif") for n in nombres_teselas]
            except Exception as e:
                logger.error(f"Error al leer carpeta de stacks: {e}")
                self.dialogo_progreso.log_error(f"No se pudieron listar las teselas: {e}")
                return

        config_pred = params_prediccion.copy()
        config_pred.update({
            'max_gpu_workers': params_tecnico.get('max_gpu_workers', 2),
            'cpu_workers_pred': params_tecnico.get('cpu_workers_pred', 1),
        })
        self._guardar_ultima_config(params_prediccion, params_tecnico)

        archivos_entrenamiento = None
        if modelo_seleccionado == 'isolation_forest':
            config_entrenamiento = dialogo.obtener_parametros_completos().get('entrenamiento', {})
            archivos_entrenamiento = config_entrenamiento.get('archivos_entrenamiento', [])

        self.carpeta_resultados_actual = params_prediccion['carpeta_resultados']

        tarea = TareaPrediccion(
            nombres_teselas=nombres_teselas, rutas_stacks=rutas_stacks,
            carpeta_stacks=carpeta_stacks_directa,
            carpeta_resultados=params_prediccion['carpeta_resultados'],
            ruta_modelo=params_prediccion.get('ruta_modelo', ''),
            config_pred=config_pred, progress_dialog=self.dialogo_progreso,
            archivos_entrenamiento=archivos_entrenamiento
        )
        tarea.taskCompleted.connect(self._on_prediccion_completada)
        tarea.taskTerminated.connect(self._on_prediccion_terminada)
        QgsApplication.taskManager().addTask(tarea)
        self.iface.messageBar().pushMessage("COLADA", "Predicción iniciada en segundo plano.", level=Qgis.Info)

    # ------------------------------------------------------------------
    # Persistencia de configuración
    # ------------------------------------------------------------------
    def _guardar_ultima_config(self, prediccion, tecnico):
        config = {'prediccion': prediccion, 'tecnico': tecnico}
        QgsSettings().setValue("COLADA/last_config", json.dumps(config))

    def _guardar_ultima_config_entrenamiento(self, entrenamiento, tecnico):
        config = {'entrenamiento': entrenamiento, 'tecnico': tecnico}
        QgsSettings().setValue("COLADA/last_config", json.dumps(config))

    # ------------------------------------------------------------------
    # Carga de resultados en el mapa (legacy)
    # ------------------------------------------------------------------
    def _cargar_resultados_prediccion(self, carpeta_resultados):
        if not os.path.isdir(carpeta_resultados):
            logger.warning(f"Carpeta de resultados no encontrada: {carpeta_resultados}")
            return
        cargadas = 0
        for archivo in sorted(os.listdir(carpeta_resultados)):
            if not archivo.lower().endswith('.tif'):
                continue
            ruta = os.path.join(carpeta_resultados, archivo)
            nombre_capa = f"Colada_{archivo.replace('.tif', '')}"
            if QgsProject.instance().mapLayersByName(nombre_capa):
                continue
            capa = self.iface.addRasterLayer(ruta, nombre_capa)
            if capa:
                capa.renderer().setOpacity(0.7)
                cargadas += 1
        if cargadas > 0:
            logger.info(f"Se cargaron {cargadas} capas de resultados en el mapa.")
            self.iface.messageBar().pushMessage("Colada", f"Se han cargado {cargadas} capas de resultados en el mapa.", level=Qgis.Success)
        else:
            logger.info("No se encontraron archivos de resultado para cargar.")

    # ------------------------------------------------------------------
    # Callbacks de finalización
    # ------------------------------------------------------------------
    def _on_prediccion_completada(self):
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(True, "✅ Predicción completada con éxito.")
        logger.info("Predicción de COLADA completada. Cargando resultados en el mapa...")
        if self.carpeta_resultados_actual:
            self._cargar_resultados_prediccion(self.carpeta_resultados_actual)

    def _on_prediccion_terminada(self):
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(False, "❌ Predicción cancelada o con errores.")
        logger.warning("Predicción de COLADA terminada de forma inesperada.")

    def _on_entrenamiento_completado(self):
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(True, "✅ Entrenamiento completado.")
        logger.info("Entrenamiento finalizado con éxito.")

    def _on_entrenamiento_terminado(self):
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(False, "❌ Entrenamiento cancelado o con errores.")
        logger.warning("Entrenamiento finalizado de manera inesperada.")