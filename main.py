# -*- coding: utf-8 -*-
"""
Plugin paraguas Arqueo Cid para QGIS.
======================================

Unifica los módulos Tizona (preprocesado LiDAR) y Colada (postprocesado IA)
bajo una misma interfaz. Al cargarse, añade una barra de herramientas con:

- Botón Arqueo Cid: selecciona cobertura, carga el mapa base y la malla de teselas.
- Botón Buscador: geolocaliza un lugar y centra el mapa en él.
- Botón Tizona: acceso directo al preprocesado LiDAR.
- Botón Colada: acceso directo al postprocesado IA.

La ortofoto del PNOA y la malla de teselas solo se cargan al pulsar el botón
Arqueo Cid y elegir cobertura. La vista se centra automáticamente en España.
"""

import os
from typing import List, Optional

from qgis.core import (
    QgsProject,
    QgsSettings,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRasterLayer,
    QgsApplication,
)
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QTimer

# Submódulos
from .tizona.main import TizonaPlugin
from .colada.main import ColadaPlugin

# Componentes propios del paraguas
from .gui.dialogoCobertura import DialogoCobertura
from .core.visor_teselas import actualizar_capa_teselas
from .core.buscador import buscar_lugar_y_centrar

# Logger común
from .utils.logging import get_logger

# Constantes desde la configuración central
from .config import URL_ORTOFOTO_PNOA, NOMBRE_MAPA_BASE

logger = get_logger('ArqueoCid')


class ArqueoCidPlugin:
    """
    Plugin principal Arqueo Cid v1.0.

    Attributes:
        iface: Interfaz de QGIS.
        actions: Lista de acciones creadas (para limpieza).
        menu: Nombre del menú donde se añaden las acciones.
        toolbar: Barra de herramientas personalizada.
        _cobertura_actual: Cobertura LiDAR actual ('todas', '1', '2', '3').
        tizona: Instancia del submódulo Tizona (si se pudo cargar).
        colada: Instancia del submódulo Colada (si se pudo cargar).
    """

    def __init__(self, iface: "QgisInterface") -> None:
        """
        Inicializa el plugin, cargando los submódulos internos.

        Args:
            iface: Interfaz de QGIS.
        """
        self.iface = iface
        self.actions: List[QAction] = []
        self.menu = 'Arqueo Cid'
        self._cobertura_actual = 'todas'

        # Instanciar submódulos de forma segura
        try:
            self.tizona = TizonaPlugin(iface)
        except Exception as e:
            logger.error(f"Error al iniciar Tizona: {e}")
            self.tizona = None

        try:
            self.colada = ColadaPlugin(iface)
        except Exception as e:
            logger.error(f"Error al iniciar Colada: {e}")
            self.colada = None

        # Callback para abrir Colada desde el diálogo de progreso de Tizona
        def _abrir_colada_desde_tizona(ruta_resultados: str, nombres_teselas: Optional[List[str]] = None) -> None:
            if self.colada:
                QTimer.singleShot(150, lambda: self.colada.run_colada(
                    ruta_inicial=ruta_resultados,
                    nombres_teselas=nombres_teselas
                ))

        if self.tizona:
            self.tizona._colada_callback = _abrir_colada_desde_tizona

    # ------------------------------------------------------------------
    # Interfaz de QGIS
    # ------------------------------------------------------------------

    def initGui(self) -> None:
        """Crea la barra de herramientas 'Arqueo Cid' con cuatro botones."""
        self.toolbar = self.iface.addToolBar("Arqueo Cid")
        self.toolbar.setObjectName("ArqueoCidToolbar")

        base_dir = os.path.dirname(__file__)
        ruta_icono_cid = os.path.join(base_dir, 'resources', 'icons', 'cid.png')
        ruta_icono_tizona = os.path.join(base_dir, 'resources', 'icons', 'tizona.png')
        ruta_icono_colada = os.path.join(base_dir, 'resources', 'icons', 'colada.png')
        ruta_icono_buscar = os.path.join(base_dir, 'resources', 'icons', 'buscar.png')

        icono_cid = QIcon(ruta_icono_cid) if os.path.exists(ruta_icono_cid) else QIcon()
        icono_tizona = QIcon(ruta_icono_tizona) if os.path.exists(ruta_icono_tizona) else QIcon()
        icono_colada = QIcon(ruta_icono_colada) if os.path.exists(ruta_icono_colada) else QIcon()
        icono_buscar = QIcon(ruta_icono_buscar) if os.path.exists(ruta_icono_buscar) else QIcon(":/images/themes/default/mActionFilter.svg")

        # ── Acciones ─────────────────────────────────────────────
        self.accion_cid = QAction(icono_cid, "Arqueo Cid – Seleccionar cobertura", self.iface.mainWindow())
        self.accion_cid.setToolTip("Elige cobertura, carga el mapa base y la malla de teselas")
        self.accion_cid.triggered.connect(self._seleccionar_cobertura)
        self.toolbar.addAction(self.accion_cid)

        self.accion_buscar = QAction(icono_buscar, "Buscador de lugares", self.iface.mainWindow())
        self.accion_buscar.setToolTip("Busca un pueblo o yacimiento y centra el mapa en él")
        self.accion_buscar.triggered.connect(lambda: buscar_lugar_y_centrar(self.iface))
        self.toolbar.addAction(self.accion_buscar)

        self.toolbar.addSeparator()

        self.accion_tizona = QAction(icono_tizona, "Tizona – Preprocesado LiDAR", self.iface.mainWindow())
        self.accion_tizona.setToolTip("Abre directamente la configuración de preprocesado LiDAR")
        self.accion_tizona.triggered.connect(self._ejecutar_tizona)
        self.toolbar.addAction(self.accion_tizona)

        self.accion_colada = QAction(icono_colada, "Colada – Postprocesado IA", self.iface.mainWindow())
        self.accion_colada.setToolTip("Abre directamente el módulo de postprocesado IA")
        self.accion_colada.triggered.connect(self._ejecutar_colada)
        self.toolbar.addAction(self.accion_colada)

        for accion in [self.accion_cid, self.accion_buscar, self.accion_tizona, self.accion_colada]:
            self.iface.addPluginToMenu(self.menu, accion)

        self.actions = [self.accion_cid, self.accion_buscar, self.accion_tizona, self.accion_colada]

    def unload(self) -> None:
        """Limpia la interfaz al descargar el plugin."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
        if hasattr(self, 'toolbar'):
            self.toolbar.setParent(None)
            del self.toolbar

    # ------------------------------------------------------------------
    # Mapa base (ortofoto PNOA)
    # ------------------------------------------------------------------

    def _cargar_mapa_base(self) -> bool:
        """
        Añade la ortofoto del PNOA como capa WMS.

        Returns:
            True si se cargó correctamente, False en caso contrario.
        """
        proyecto = QgsProject.instance()
        nombre_capa = NOMBRE_MAPA_BASE

        # Eliminar capas previas del PNOA
        for capa_id, capa in list(proyecto.mapLayers().items()):
            if capa.name() == nombre_capa or ('pnoa-ma' in getattr(capa, 'source', '')):
                proyecto.removeMapLayer(capa_id)

        # URI del servicio WMS (formato simple y fiable)
        uri = (
            f"crs=EPSG:25830&format=image/jpeg"
            f"&layers=OI.OrthoimageCoverage&styles=default"
            f"&url={URL_ORTOFOTO_PNOA}"
        )
        capa = QgsRasterLayer(uri, nombre_capa, "wms")

        if capa.isValid():
            proyecto.addMapLayer(capa, False)
            root = proyecto.layerTreeRoot()
            root.insertLayer(-1, capa)
            self._configurar_cache_mapa()
            logger.info("Mapa base PNOA cargado correctamente")
            return True
        else:
            logger.warning("No se pudo cargar la ortofoto PNOA. Intentando OpenStreetMap como fallback.")
            return self._cargar_mapa_base_osm()

    def _configurar_cache_mapa(self) -> None:
        """Habilita la caché de red para que las teselas WMS se almacenen en disco."""
        s = QgsSettings()
        s.setValue("/qgis/networkAndProxy/cache/enabled", True)
        s.setValue("/qgis/networkAndProxy/cache/directory",
                   os.path.join(QgsApplication.qgisSettingsDirPath(), 'cache'))
        s.setValue("/qgis/networkAndProxy/cache/size", 512 * 1024 * 1024)  # 512 MB

    def _cargar_mapa_base_osm(self) -> bool:
        """
        Carga OpenStreetMap como mapa de respaldo.

        Returns:
            True si se cargó correctamente.
        """
        url_osm = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        capa = QgsRasterLayer(url_osm, "OpenStreetMap", "xyz")
        if capa.isValid():
            QgsProject.instance().addMapLayer(capa)
            logger.info("Mapa base OpenStreetMap cargado correctamente")
            return True
        else:
            logger.error("No se pudo cargar ningún mapa base.")
            return False

    # ------------------------------------------------------------------
    # Centrar vista en España
    # ------------------------------------------------------------------

    def _centrar_vista_en_espana(self) -> None:
        """Ajusta el lienzo de QGIS para mostrar la Península Ibérica y Baleares."""
        proyecto = QgsProject.instance()
        canvas = self.iface.mapCanvas()

        crs_utm30 = QgsCoordinateReferenceSystem("EPSG:25830")
        proyecto.setCrs(crs_utm30)

        xmin, ymin = -9.5, 35.5
        xmax, ymax = 4.5, 44.0
        rect_wgs84 = QgsRectangle(xmin, ymin, xmax, ymax)

        crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(crs_wgs84, crs_utm30, proyecto)
        rect_proyecto = transform.transformBoundingBox(rect_wgs84)
        canvas.setExtent(rect_proyecto)
        canvas.refresh()
        logger.info("Vista centrada en la Península Ibérica")

    # ------------------------------------------------------------------
    # Selección de cobertura → carga mapa y malla
    # ------------------------------------------------------------------

    def _seleccionar_cobertura(self) -> None:
        """Abre el diálogo de cobertura y carga mapa + malla si el usuario acepta."""
        dialogo = DialogoCobertura(self.iface.mainWindow())
        if dialogo.exec_():
            cobertura = dialogo.cobertura_seleccionada()
            self._cobertura_actual = cobertura

            if not self._cargar_mapa_base():
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Mapa base no disponible",
                    "No se pudo cargar la ortofoto PNOA ni OpenStreetMap.\n"
                    "Verifique su conexión a Internet o la disponibilidad del servicio WMS."
                )
            else:
                self._centrar_vista_en_espana()

            capa = actualizar_capa_teselas(cobertura)
            if capa is None:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Malla no disponible",
                    f"No se encontró la malla para la cobertura {cobertura}.\n"
                    "Asegúrese de que los shapefiles están en:\n"
                    f"{os.path.join(os.path.dirname(__file__), 'resources', 'mallas', f'cobertura_{cobertura}')}"
                )
                return

            self.iface.messageBar().pushMessage(
                "Arqueo Cid",
                f"Malla de teselas cargada para cobertura {cobertura}.",
                level=0,
                duration=3
            )
            logger.info(f"Cobertura seleccionada: {cobertura}")

    # ------------------------------------------------------------------
    # Accesos directos a los submódulos
    # ------------------------------------------------------------------

    def _ejecutar_tizona(self) -> None:
        """Ejecuta Tizona (preprocesado LiDAR)."""
        if self.tizona:
            self.tizona.run()
        else:
            QMessageBox.critical(self.iface.mainWindow(), "Error",
                                 "El módulo Tizona no está disponible.")

    def _ejecutar_colada(self) -> None:
        """Ejecuta Colada (postprocesado IA)."""
        if self.colada:
            self.colada.run_colada()
        else:
            QMessageBox.critical(self.iface.mainWindow(), "Error",
                                 "El módulo Colada no está disponible.")