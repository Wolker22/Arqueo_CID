"""
Plugin paraguas Arqueo Cid para QGIS.
======================================

Unifica los módulos Tizona (preprocesado LiDAR) y Colada (postprocesado IA)
bajo una misma interfaz.
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.utils import QgisInterface

# Submódulos
from .colada.main import ColadaPlugin

# Constantes desde la configuración central
from .config import (
    NOMBRE_PLUGIN,
    NOMBRE_POSTPROCESAR,
    NOMBRE_PREPROCESAR,
)

# Importaciones de los módulos del core
from .core.buscador import buscar_lugar_y_centrar
from .core.mapa_cobertura import seleccionar_cobertura
from .tizona.main import TizonaPlugin

# Logger común
from .utils.logging import get_logger

logger = get_logger("ArqueoCid")


class ArqueoCidPlugin:
    """
    Plugin principal Arqueo Cid v1.0.
    """

    def __init__(self, iface: QgisInterface) -> None:
        """Inicializa el plugin, cargando los submódulos internos."""
        self.iface = iface
        self.actions: list[QAction] = []
        self.menu = NOMBRE_PLUGIN
        self._cobertura_actual = "todas"

        # Instanciar submódulos de forma segura
        try:
            self.tizona = TizonaPlugin(iface)
        except Exception:
            logger.exception("Error al iniciar Tizona")
            self.tizona = None

        try:
            self.colada = ColadaPlugin(iface)
        except Exception:
            logger.exception("Error al iniciar Colada")
            self.colada = None

    # ------------------------------------------------------------------
    # Interfaz de QGIS
    # ------------------------------------------------------------------

    def initgui(self) -> None:
        """Crea la barra de herramientas 'Arqueo UCO' con cuatro botones."""
        self.toolbar = self.iface.addToolBar(NOMBRE_PLUGIN)
        self.toolbar.setObjectName("ArqueoCidToolbar")

        base_dir = os.path.dirname(__file__)
        ruta_icono_principal = os.path.join(base_dir, "resources", "icons", "principal.png")
        ruta_icono_preprocesar = os.path.join(base_dir, "resources", "icons", "preprocesar.png")
        ruta_icono_postprocesar = os.path.join(base_dir, "resources", "icons", "postprocesar.png")
        ruta_icono_buscar = os.path.join(base_dir, "resources", "icons", "buscar.png")

        icono_principal = QIcon(ruta_icono_principal) if os.path.exists(ruta_icono_principal) else QIcon()
        icono_preprocesar = QIcon(ruta_icono_preprocesar) if os.path.exists(ruta_icono_preprocesar) else QIcon()
        icono_postprocesar = QIcon(ruta_icono_postprocesar) if os.path.exists(ruta_icono_postprocesar) else QIcon()
        icono_buscar = QIcon(ruta_icono_buscar) if os.path.exists(ruta_icono_buscar) else QIcon()

        # ── Acciones ─────────────────────────────────────────────
        self.accion_principal = QAction(
            icono_principal, f"{NOMBRE_PLUGIN} – Seleccionar cobertura", self.iface.mainWindow()
        )
        self.accion_principal.setToolTip("Elige cobertura, carga el mapa base y la malla de teselas")
        # Le pasamos self.iface a la función aislada
        self.accion_principal.triggered.connect(lambda: seleccionar_cobertura(self.iface))
        self.toolbar.addAction(self.accion_principal)

        self.accion_buscar = QAction(icono_buscar, "Buscador de lugares", self.iface.mainWindow())
        self.accion_buscar.setToolTip("Busca un pueblo o yacimiento y centra el mapa en él")
        self.accion_buscar.triggered.connect(lambda: buscar_lugar_y_centrar(self.iface))
        self.toolbar.addAction(self.accion_buscar)

        self.accion_preprocesar = QAction(
            icono_preprocesar, f"{NOMBRE_PREPROCESAR} - Preprocesado LiDAR", self.iface.mainWindow()
        )
        self.accion_preprocesar.setToolTip("Abre directamente la configuración de preprocesado LiDAR")
        self.accion_preprocesar.triggered.connect(self._ejecutar_tizona)
        self.toolbar.addAction(self.accion_preprocesar)

        self.accion_postprocesar = QAction(
            icono_postprocesar, f"{NOMBRE_POSTPROCESAR} - Postprocesado IA", self.iface.mainWindow()
        )
        self.accion_postprocesar.setToolTip("Abre directamente el módulo de postprocesado IA")
        self.accion_postprocesar.triggered.connect(self._ejecutar_colada)
        self.toolbar.addAction(self.accion_postprocesar)

        self.actions = [
            self.accion_principal,
            self.accion_buscar,
            self.accion_preprocesar,
            self.accion_postprocesar,
        ]

        for accion in self.actions:
            self.iface.addPluginToMenu(self.menu, accion)

    def unload(self) -> None:
        """Limpia la interfaz al descargar el plugin."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
        if hasattr(self, "toolbar"):
            self.toolbar.setParent(None)
            del self.toolbar

    # ------------------------------------------------------------------
    # Accesos directos a los submódulos
    # ------------------------------------------------------------------

    def _ejecutar_tizona(self) -> None:
        """Ejecuta Tizona (preprocesado LiDAR)."""
        if self.tizona:
            self.tizona.run()
        else:
            QMessageBox.critical(self.iface.mainWindow(), "Error", "El módulo Tizona no está disponible.")

    def _ejecutar_colada(self) -> None:
        """Ejecuta Colada (postprocesado IA)."""
        if self.colada:
            self.colada.run_colada()
        else:
            QMessageBox.critical(self.iface.mainWindow(), "Error", "El módulo Colada no está disponible.")
