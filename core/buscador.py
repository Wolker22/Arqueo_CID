# -*- coding: utf-8 -*-
"""
Buscador de lugares para Arqueo Cid.
====================================

Permite al usuario introducir un topónimo y centrar el mapa en ese lugar
utilizando el servicio Nominatim de OpenStreetMap.
"""

import json
import urllib.parse
import urllib.request
from typing import Optional

from qgis.core import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
)

from ..config import (
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLOR_FONDO,
    BUSCADOR_TITULO,
    BUSCADOR_MIN_WIDTH,
    BUSCADOR_MIN_HEIGHT,
    BUSCADOR_PLACEHOLDER,
    BUSCADOR_ZOOM_SCALE,
    NOMINATIM_USER_AGENT,
    NOMINATIM_TIMEOUT,
    NOMINATIM_BASE_URL,
    MENSAJE_CAMPO_VACIO,
    MENSAJE_ERROR_RED,
    MENSAJE_SIN_RESULTADOS,
    MENSAJE_BUSCANDO,
    MENSAJE_LLEGADA,
)
from ..utils.logging import get_logger

logger = get_logger('ArqueoCid.buscador')


class DialogoBuscador(QDialog):
    """
    Diálogo simple para introducir el nombre de un lugar.
    """

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(BUSCADOR_TITULO)
        self.setMinimumSize(BUSCADOR_MIN_WIDTH, BUSCADOR_MIN_HEIGHT)
        self._lugar: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        titulo = QLabel(BUSCADOR_TITULO)
        titulo.setProperty("heading", "true")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        lbl_instruccion = QLabel("Introduce el pueblo o lugar que deseas explorar:")
        lbl_instruccion.setWordWrap(True)
        layout.addWidget(lbl_instruccion)

        self.edit_lugar = QLineEdit()
        self.edit_lugar.setPlaceholderText(BUSCADOR_PLACEHOLDER)
        self.edit_lugar.returnPressed.connect(self._aceptar)
        layout.addWidget(self.edit_lugar)

        btn_layout = QHBoxLayout()
        btn_aceptar = QPushButton("Buscar")
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setObjectName("btn_cancelar")
        btn_aceptar.clicked.connect(self._aceptar)
        btn_cancelar.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_aceptar)
        btn_layout.addWidget(btn_cancelar)
        layout.addLayout(btn_layout)

        self.setLayout(layout)
        self._aplicar_estilos()
        self.edit_lugar.setFocus()

    def _aceptar(self) -> None:
        self._lugar = self.edit_lugar.text().strip()
        if not self._lugar:
            QMessageBox.warning(self, "Campo vacío", MENSAJE_CAMPO_VACIO)
            return
        self.accept()

    def lugar(self) -> str:
        return self._lugar

    def _aplicar_estilos(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_FONDO}; }}
            QLabel[heading="true"] {{
                font-size: 18px; font-weight: bold; color: {COLOR_PRIMARIO};
            }}
            QLabel {{ font-size: 12px; color: #333; }}
            QLineEdit {{
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                background: white;
                selection-background-color: {COLOR_PRIMARIO};
            }}
            QPushButton {{
                background-color: {COLOR_PRIMARIO};
                color: white;
                border: 1px solid {COLOR_PRIMARIO_OSC};
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {COLOR_PRIMARIO_OSC}; }}
            QPushButton#btn_cancelar {{
                background-color: {COLADA_COLOR_PRIMARIO};
                border: 1px solid {COLADA_COLOR_PRIMARIO_OSC};
                color: white;
            }}
            QPushButton#btn_cancelar:hover {{ background-color: {COLADA_COLOR_PRIMARIO_OSC}; }}
        """)


def buscar_lugar_y_centrar(iface: "QgisInterface") -> None:
    """
    Función principal que muestra el diálogo, consulta Nominatim y centra el mapa.

    Args:
        iface: Interfaz de QGIS.
    """
    dialogo = DialogoBuscador(iface.mainWindow())
    if dialogo.exec_() != QDialog.Accepted:
        return

    lugar = dialogo.lugar()
    try:
        iface.messageBar().pushMessage("Arqueo Cid", MENSAJE_BUSCANDO.format(lugar), level=0)
        params = {"q": f"{lugar}, Spain", "format": "json", "limit": 1}
        url = f"{NOMINATIM_BASE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': NOMINATIM_USER_AGENT})
        with urllib.request.urlopen(req, timeout=NOMINATIM_TIMEOUT) as respuesta:
            datos = json.loads(respuesta.read().decode('utf-8'))
        if not datos:
            QMessageBox.warning(iface.mainWindow(), "Sin resultados", MENSAJE_SIN_RESULTADOS.format(lugar))
            return
        lat = float(datos[0]['lat'])
        lon = float(datos[0]['lon'])
    except Exception as e:
        logger.error(f"Error en búsqueda de '{lugar}': {e}")
        QMessageBox.critical(iface.mainWindow(), "Error de red", MENSAJE_ERROR_RED)
        return

    # Transformar coordenadas al CRS del proyecto
    crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    crs_proyecto = QgsProject.instance().crs()
    transform = QgsCoordinateTransform(crs_wgs84, crs_proyecto, QgsProject.instance())
    punto_destino = transform.transform(QgsPointXY(lon, lat))

    lienzo = iface.mapCanvas()
    lienzo.setCenter(punto_destino)
    lienzo.zoomScale(BUSCADOR_ZOOM_SCALE)
    lienzo.refresh()
    iface.messageBar().pushMessage("Arqueo Cid", MENSAJE_LLEGADA.format(lugar), level=0, duration=5)