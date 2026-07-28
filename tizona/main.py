# -*- coding: utf-8 -*-
"""
Motor de preprocesado LiDAR – Tizona (parte del proyecto Arqueo Cid)
====================================================================

Este módulo ya no gestiona la interfaz de usuario (barra de herramientas,
botones, mapa base). Ahora es una clase "pura" que expone el método run()
para que el plugin paraguas (ArqueoCidPlugin) lo invoque.

Flujo de trabajo:
1. El plugin paraguas llama a tizona.run() o tizona.run_with_names(nombres).
2. Si se pasan nombres, se usan directamente sin preguntar al usuario.
3. Se verifica el entorno en segundo plano.
4. Se abre el diálogo de configuración.
5. Si el usuario acepta, se lanza la tarea de procesamiento (descarga, MDT, derivados).
6. Al finalizar, los derivados se cargan sobre el mapa (a través de iface).
7. Opcionalmente, se puede conectar un callback para abrir Colada desde el diálogo de progreso.
   MODIFICACIÓN: El callback ahora recibe dos argumentos: ruta y lista de nombres.
"""

import os
from typing import List, Optional, Dict, Any, Callable

from qgis.core import QgsApplication, Qgis, QgsProject
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QProgressDialog
from qgis.PyQt.QtCore import QThread, pyqtSignal, QObject

# Importar constantes desde la configuración central
from ..config import (
    NOMBRE_CAMPO_TESELA as NOMBRE_CAMPO,
    CARPETA_DERIVADOS,
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLOR_FONDO,
    COLOR_BORDE,
)
from ..gui.gui_preprocesado.dialogoConfiguracion import DialogoConfiguracion
from ..gui.gui_preprocesado.dialogoProgreso import DialogoProgreso
from .tasks.pipeline import TareaPipeline
from ..utils.logging import get_logger
from ..utils.entorno import verificar_todas_dependencias, es_entorno_valido, formatear_mensaje_dependencias

logger = get_logger('Tizona')  # Usar logger 'Tizona' (se mapea al logger principal 'Tizona')


class DependencyWorker(QObject):
    """
    Trabajador que ejecuta la verificación de dependencias en un hilo
    secundario para no bloquear la interfaz de QGIS.
    """

    finished = pyqtSignal(object)  # Emite el diccionario de dependencias
    error = pyqtSignal(str)        # Emite mensaje de error

    def run(self) -> None:
        """Ejecuta la verificación y emite la señal correspondiente."""
        try:
            info = verificar_todas_dependencias()
            self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class TizonaPlugin:
    """
    Motor de preprocesado LiDAR Tizona.

    El plugin paraguas (Arqueo Cid) instancia esta clase y llama a run()
    o run_with_names() cuando el usuario solicita el preprocesado.

    Attributes:
        iface: Interfaz de QGIS (QgisInterface).
        dialogo_progreso: Diálogo de progreso actual (si existe).
        ruta_descarga: Carpeta donde se guardan los LAZ descargados.
        ruta_procesados: Carpeta donde se guardan los resultados.
        _nombres_predefinidos: Lista de nombres de tesela pasada externamente.
        _colada_callback: Función para abrir Colada al finalizar.
    """

    def __init__(self, iface: "QgisInterface") -> None:
        """
        Inicializa el plugin Tizona.

        Args:
            iface: Interfaz de QGIS proporcionada por el plugin paraguas.
        """
        self.iface = iface
        self.dialogo_progreso: Optional[DialogoProgreso] = None

        # Rutas de trabajo (se actualizan al aceptar la configuración)
        self.ruta_descarga: Optional[str] = None
        self.ruta_procesados: Optional[str] = None

        # Nombres de tesela predefinidos (si se pasan desde fuera)
        self._nombres_predefinidos: Optional[List[str]] = None

        # Callback para abrir Colada (se conecta en el diálogo de progreso)
        # MODIFICACIÓN: espera una función que reciba (ruta, lista_nombres)
        self._colada_callback: Optional[Callable[[str, List[str]], None]] = None

        # Almacenar hilo y worker de dependencias para evitar que se destruyan
        self._dep_thread: Optional[QThread] = None
        self._dep_worker: Optional[DependencyWorker] = None
        self._progress_deps: Optional[QProgressDialog] = None

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Inicia el flujo de Tizona:
        1. Muestra un diálogo de espera mientras se verifican las dependencias.
        2. Al terminar, abre el diálogo de configuración.
        3. Si el usuario acepta, lanza el pipeline de procesamiento.
        """
        # Mostrar diálogo de progreso mientras se verifican dependencias
        self._progress_deps = QProgressDialog(
            "Verificando dependencias...",
            None,
            0,
            0,
            self.iface.mainWindow(),
        )
        self._progress_deps.setWindowTitle("Tizona")
        self._progress_deps.setCancelButton(None)
        self._progress_deps.setMinimumDuration(0)
        self._progress_deps.setValue(0)
        self._progress_deps.show()

        self._dep_thread = QThread()
        self._dep_worker = DependencyWorker()
        self._dep_worker.moveToThread(self._dep_thread)
        self._dep_thread.started.connect(self._dep_worker.run)
        self._dep_worker.finished.connect(self._on_deps_checked)
        self._dep_worker.error.connect(self._on_deps_error)
        self._dep_thread.start()

    def run_with_names(self, nombres: List[str]) -> None:
        """
        Igual que run(), pero utiliza directamente la lista de nombres proporcionada
        sin preguntar al usuario. Útil cuando el plugin paraguas ya ha validado
        la selección de teselas en la malla.

        Args:
            nombres: Lista de identificadores de tesela (sin extensión).
        """
        self._nombres_predefinidos = nombres
        self.run()

    # ------------------------------------------------------------------
    # Manejadores de la verificación de dependencias
    # ------------------------------------------------------------------

    def _on_deps_error(self, msg: str) -> None:
        """Se ejecuta si falla la verificación de dependencias."""
        if self._progress_deps:
            self._progress_deps.close()
        self._dep_thread.quit()
        self._dep_thread.wait()
        QMessageBox.critical(
            self.iface.mainWindow(),
            "Error",
            f"Fallo al verificar dependencias:\n{msg}"
        )

    def _on_deps_checked(self, info_deps: Dict[str, Any]) -> None:
        """
        Se ejecuta cuando la verificación de dependencias ha terminado.
        Muestra el diálogo de configuración y, si es aceptado, lanza el pipeline.
        """
        if self._progress_deps:
            self._progress_deps.close()
        self._dep_thread.quit()
        self._dep_thread.wait()

        # Mostrar diálogo de configuración
        dialogo_conf = DialogoConfiguracion(self.iface.mainWindow())
        if dialogo_conf.exec_() != QDialog.Accepted:
            return

        params_proc, config_descarga = dialogo_conf.obtener_parametros()
        modo = config_descarga.get("modo_ejecucion", "Descargar y procesar")

        # Verificar dependencias obligatorias según el modo
        faltantes = self._obtener_faltantes_obligatorios(info_deps, modo)
        if faltantes:
            msg = (
                "Faltan las siguientes dependencias obligatorias:\n\n"
                + "\n".join(faltantes)
                + "\n\nEl plugin no funcionará correctamente."
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Tizona - Dependencias incompletas",
                msg
            )
            return

        # Si el modo incluye descarga, advertir si CNIG no está accesible
        if modo != "Solo procesamiento":
            cnig_info = info_deps["dependencias"].get("cnig", {})
            if not cnig_info.get("disponible", False):
                respuesta = QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Aviso de Red",
                    "El test previo de conexión con el servidor del CNIG ha fallado.\n"
                    "¿Desea forzar el intento de descarga de todos modos?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if respuesta == QMessageBox.No:
                    return

        # Guardar rutas de trabajo
        self.ruta_descarga = config_descarga.get("ruta_descarga")
        self.ruta_procesados = config_descarga.get("ruta_procesados")

        # Obtener lista de nombres de tesela
        nombres = []
        if self._nombres_predefinidos is not None:
            nombres = self._nombres_predefinidos
            self._nombres_predefinidos = None
        else:
            nombres = self._obtener_nombres_teselas(config_descarga, modo)
            if nombres is None:
                return

        if not nombres:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Tizona",
                "No se pudo determinar ningún archivo a procesar.",
            )
            return

        # Lanzar pipeline
        self.dialogo_progreso = DialogoProgreso(
            "Tizona - Procesamiento",
            self.iface.mainWindow()
        )

        # Guardar ruta de resultados para el botón Colada
        self.dialogo_progreso.set_ruta_resultados(self.ruta_procesados)
        # Guardar la lista de teselas que se van a procesar
        self.dialogo_progreso.set_teselas_procesadas(nombres)

        # Conectar señal de apertura de Colada si hay callback
        if self._colada_callback:
            self.dialogo_progreso._sig_abrir_colada_con_teselas.connect(
                self._colada_callback
            )

        self.dialogo_progreso.show()
        self.dialogo_progreso.log_info(
            f"Iniciando proceso con {len(nombres)} archivo(s)..."
        )
        self.dialogo_progreso.log_info(f"Modo: {modo}")
        self.dialogo_progreso.log_info(
            f"Resolución MDT: {params_proc.get('resolucion', 0.5)} m"
        )
        self.dialogo_progreso.log_info(
            f"Derivados: {len(params_proc.get('derivados', []))}"
        )

        tarea = TareaPipeline(
            nombres,
            params_proc,
            config_descarga,
            self.dialogo_progreso
        )
        tarea.taskCompleted.connect(self._on_tarea_completada)
        tarea.taskTerminated.connect(self._on_tarea_terminada)
        QgsApplication.taskManager().addTask(tarea)

        self.iface.messageBar().pushMessage(
            "Tizona",
            "Tarea iniciada en segundo plano.",
            level=Qgis.Info
        )

    # ------------------------------------------------------------------
    # Verificación de dependencias
    # ------------------------------------------------------------------

    def _obtener_faltantes_obligatorios(
        self,
        info_deps: Dict[str, Any],
        modo: str
    ) -> List[str]:
        """
        Extrae de la información de dependencias las que son obligatorias
        y no están disponibles, formateando un mensaje de error.

        Args:
            info_deps: Diccionario devuelto por `verificar_todas_dependencias`.
            modo: Modo de ejecución ('Descargar y procesar', 'Solo descarga', 'Solo procesamiento').

        Returns:
            Lista de cadenas con los mensajes de error.
        """
        faltantes = []
        for clave, dep in info_deps["dependencias"].items():
            if dep.get("disponible", True):
                continue
            # Si es solo procesamiento, no exigimos CNIG
            if clave == "cnig" and modo == "Solo procesamiento":
                continue
            if not dep.get("obligatoria", False):
                continue
            faltantes.append(f"• {dep.get('nombre', clave)}: {dep['mensaje']}")
            if dep.get("ayuda"):
                faltantes.append(f"   → {dep['ayuda']}")
        return faltantes

    # ------------------------------------------------------------------
    # Obtención de nombres de tesela
    # ------------------------------------------------------------------

    def _obtener_nombres_teselas(
        self,
        config_descarga: Dict[str, Any],
        modo: str
    ) -> Optional[List[str]]:
        """
        Determina la lista de nombres de tesela a procesar según:
        - Si existe la capa "Teselas PNOA LiDAR" con selección, se usan sus campos.
        - En modo descarga, se usa la capa activa seleccionada.
        - En modo solo procesamiento, se escanea la carpeta de descarga en busca de .laz.

        Args:
            config_descarga: Diccionario con la configuración de descarga.
            modo: Modo de ejecución.

        Returns:
            Lista de nombres (sin extensión) o None si hay error.
        """
        nombres = []

        # 1. Intentar obtener de la capa "Teselas PNOA LiDAR" (visión)
        for capa in QgsProject.instance().mapLayers().values():
            if capa.name() == "Teselas PNOA LiDAR" and capa.selectedFeatureCount() > 0:
                nombres = [f[NOMBRE_CAMPO] for f in capa.selectedFeatures()]
                break

        if not nombres:
            descarga_activada = modo in ("Descargar y procesar", "Solo descarga")
            if descarga_activada:
                capa = self.iface.activeLayer()
                if not capa:
                    QMessageBox.critical(
                        self.iface.mainWindow(),
                        "Tizona",
                        "Para modos de descarga es necesario tener una capa activa con una selección.",
                    )
                    return None
                if capa.selectedFeatureCount() == 0:
                    QMessageBox.critical(
                        self.iface.mainWindow(),
                        "Tizona",
                        "Selecciona al menos un elemento en la capa activa.",
                    )
                    return None
                if NOMBRE_CAMPO not in [f.name() for f in capa.fields()]:
                    QMessageBox.critical(
                        self.iface.mainWindow(),
                        "Tizona",
                        f"La capa no contiene el campo '{NOMBRE_CAMPO}'.",
                    )
                    return None
                nombres = list(
                    set(
                        str(f[NOMBRE_CAMPO]).strip()
                        for f in capa.selectedFeatures()
                        if str(f[NOMBRE_CAMPO]).strip()
                    )
                )
                if not nombres:
                    QMessageBox.critical(
                        self.iface.mainWindow(),
                        "Tizona",
                        "Los elementos seleccionados no contienen nombres de tesela válidos.",
                    )
                    return None
            else:
                # Modo "Solo procesamiento": se toman los archivos locales de la carpeta de descarga
                capa = self.iface.activeLayer()
                if (
                    capa
                    and capa.selectedFeatureCount() > 0
                    and NOMBRE_CAMPO in [f.name() for f in capa.fields()]
                ):
                    nombres = list(
                        set(
                            str(f[NOMBRE_CAMPO]).strip()
                            for f in capa.selectedFeatures()
                            if str(f[NOMBRE_CAMPO]).strip()
                        )
                    )
                if not nombres:
                    carpeta = config_descarga.get("ruta_descarga")
                    if not carpeta or not os.path.isdir(carpeta):
                        QMessageBox.critical(
                            self.iface.mainWindow(),
                            "Tizona",
                            "No se ha especificado una carpeta de descargas válida en la configuración.",
                        )
                        return None
                    # Buscar archivos .laz/.las en la carpeta
                    nombres = [
                        os.path.splitext(f)[0]
                        for f in os.listdir(carpeta)
                        if f.lower().endswith((".laz", ".las"))
                    ]
                    if not nombres:
                        QMessageBox.critical(
                            self.iface.mainWindow(),
                            "Tizona",
                            f"No se encontraron archivos .laz/.las en:\n{carpeta}",
                        )
                        return None
                    QMessageBox.information(
                        self.iface.mainWindow(),
                        "Tizona",
                        f"Se procesarán todos los archivos encontrados:\n{carpeta}\n({len(nombres)} archivos)",
                    )

        return nombres if nombres else None

    # ------------------------------------------------------------------
    # Carga de derivados en el mapa
    # ------------------------------------------------------------------

    def _cargar_derivados_en_mapa(self) -> None:
        """
        Recorre la carpeta de resultados y carga todos los GeoTIFF de derivados
        como capas raster en el proyecto de QGIS.
        """
        if not self.ruta_procesados or not os.path.isdir(self.ruta_procesados):
            logger.warning("No se encontró la carpeta de procesados para cargar resultados.")
            return

        cargadas = 0
        for nombre_tesela in os.listdir(self.ruta_procesados):
            carpeta_tesela = os.path.join(self.ruta_procesados, nombre_tesela)
            if not os.path.isdir(carpeta_tesela):
                continue
            carpeta_derivados = os.path.join(carpeta_tesela, CARPETA_DERIVADOS)
            if not os.path.isdir(carpeta_derivados):
                continue
            for archivo in sorted(os.listdir(carpeta_derivados)):
                if not archivo.endswith(".tif"):
                    continue
                ruta_completa = os.path.join(carpeta_derivados, archivo)
                nombre_capa = f"{nombre_tesela}_{archivo.replace('.tif', '')}"
                if QgsProject.instance().mapLayersByName(nombre_capa):
                    continue
                capa = self.iface.addRasterLayer(ruta_completa, nombre_capa)
                if capa:
                    if "hillshade" in archivo.lower():
                        capa.renderer().setOpacity(0.5)
                    cargadas += 1

        if cargadas > 0:
            logger.info(f"Se cargaron {cargadas} capas de derivados en el mapa.")
            self.iface.messageBar().pushMessage(
                "Tizona",
                f"Se han cargado {cargadas} capas de resultados en el mapa.",
                level=Qgis.Success,
            )

    # ------------------------------------------------------------------
    # Finalización de la tarea
    # ------------------------------------------------------------------

    def _on_tarea_completada(self) -> None:
        """Se ejecuta cuando el pipeline termina con éxito."""
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(True, "✅ Proceso completado con éxito.")
        self._cargar_derivados_en_mapa()
        logger.info("Pipeline completado con éxito.")

    def _on_tarea_terminada(self) -> None:
        """Se ejecuta cuando el pipeline termina con error o cancelación."""
        if self.dialogo_progreso:
            self.dialogo_progreso.finalizar(False, "❌ Proceso cancelado o con errores.")
        logger.warning("Pipeline terminado de forma inesperada.")