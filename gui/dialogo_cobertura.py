from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
)

# Importamos la misma paleta unificada
from ..config import (
    COLOR_FONDO,
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_HOVER,
    COLOR_SECUNDARIO,
    COLOR_SECUNDARIO_HOVER,
    COLOR_TEXTO,
)


class DialogoCobertura(QDialog):
    """
    Diálogo modal para seleccionar la cobertura LiDAR del PNOA.
    Adaptable a pantallas de alta resolución (High-DPI) y tematizado con colores UCO.
    """

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selección de Cobertura PNOA LiDAR")
        self.resize(350, 250)
        self._cobertura_seleccionada: str = "todas"
        self._init_ui()
        self._aplicar_estilo_global()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Cabecera
        label_cabecera = QLabel("Selecciona la cobertura que deseas cargar:")
        label_cabecera.setProperty("heading", "true")
        label_cabecera.setAlignment(Qt.AlignCenter)
        label_cabecera.setWordWrap(True)
        label_cabecera.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(label_cabecera)

        # Opciones
        opciones = {
            "todas": "Todas las coberturas (Recomendado)",
            "1": "1ª Cobertura PNOA LiDAR",
            "2": "2ª Cobertura PNOA LiDAR",
            "3": "3ª Cobertura PNOA LiDAR"
        }

        self.grupo = QButtonGroup(self)
        self._radios = {}

        for key, etiqueta in opciones.items():
            radio = QRadioButton(etiqueta)
            radio.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if key == "todas":
                radio.setChecked(True)

            self.grupo.addButton(radio, int(key) if key.isdigit() else -1)
            layout.addWidget(radio)
            self._radios[key] = radio

        # Botones de Acción
        btn_layout = QHBoxLayout()
        btn_aceptar = QPushButton("Aceptar")
        btn_cancelar = QPushButton("Cancelar")
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
        return self._cobertura_seleccionada

    def _aplicar_estilo_global(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_FONDO}; }}
            QLabel[heading="true"] {{
                font-size: 14pt; font-weight: bold; color: {COLOR_PRIMARIO};
            }}
            QRadioButton {{
                spacing: 6px;
                font-size: 10pt;
                color: {COLOR_TEXTO};
            }}
            QPushButton {{
                background-color: {COLOR_PRIMARIO};

                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: {COLOR_PRIMARIO_HOVER}; }}
            QPushButton#btn_cancelar {{
                background-color: {COLOR_SECUNDARIO};
            }}
            QPushButton#btn_cancelar:hover {{ background-color: {COLOR_SECUNDARIO_HOVER}; }}
        """)
