# -*- coding: utf-8 -*-
"""
Diálogo de selección de cobertura PNOA LiDAR para Arqueo Cid.
=============================================================

Permite al usuario elegir entre la 1ª, 2ª, 3ª cobertura o todas.
"""

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QButtonGroup,
    QRadioButton,
    QPushButton,
    QHBoxLayout,
)
from qgis.PyQt.QtCore import Qt

from ..config import (
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLOR_FONDO,
    TITULO_DIALOGO_COBERTURA,
    TAMANO_MIN_COBERTURA_ANCHO,
    TAMANO_MIN_COBERTURA_ALTO,
    OPCIONES_COBERTURA,
    TEXTO_CABECERA_COBERTURA,
    TEXTO_BOTON_ACEPTAR,
    TEXTO_BOTON_CANCELAR,
)
from ..utils.logging import get_logger

logger = get_logger('ArqueoCid.dialogoCobertura')


class DialogoCobertura(QDialog):
    """
    Diálogo modal para seleccionar la cobertura LiDAR del PNOA.
    """

    def __init__(self, parent: QDialog) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITULO_DIALOGO_COBERTURA)
        self.setMinimumSize(TAMANO_MIN_COBERTURA_ANCHO, TAMANO_MIN_COBERTURA_ALTO)
        self._cobertura_seleccionada: str = "todas"
        self._init_ui()
        self._aplicar_estilo_global()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        label_cabecera = QLabel(TEXTO_CABECERA_COBERTURA)
        label_cabecera.setProperty("heading", "true")
        label_cabecera.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_cabecera)

        self.grupo = QButtonGroup(self)
        self._radios = {}
        for key, etiqueta in OPCIONES_COBERTURA.items():
            radio = QRadioButton(etiqueta)
            if key == "todas":
                radio.setChecked(True)
            self.grupo.addButton(radio, int(key) if key.isdigit() else -1)
            layout.addWidget(radio)
            self._radios[key] = radio

        btn_layout = QHBoxLayout()
        btn_aceptar = QPushButton(TEXTO_BOTON_ACEPTAR)
        btn_cancelar = QPushButton(TEXTO_BOTON_CANCELAR)
        btn_cancelar.setObjectName("btn_cancelar")
        btn_aceptar.clicked.connect(self._aceptar)
        btn_cancelar.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_aceptar)
        btn_layout.addWidget(btn_cancelar)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _aceptar(self) -> None:
        btn_id = self.grupo.checkedId()
        if btn_id == -1:
            self._cobertura_seleccionada = "todas"
        else:
            self._cobertura_seleccionada = str(btn_id)
        self.accept()

    def cobertura_seleccionada(self) -> str:
        """Devuelve la clave de la cobertura elegida ('1', '2', '3' o 'todas')."""
        return self._cobertura_seleccionada

    def _aplicar_estilo_global(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_FONDO}; }}
            QLabel[heading="true"] {{
                font-size: 18px; font-weight: bold; color: {COLOR_PRIMARIO};
            }}
            QRadioButton {{ spacing: 6px; font-size: 12px; color: #333; }}
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