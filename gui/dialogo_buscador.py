from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..config import (
    COLOR_BORDE,
    COLOR_FONDO,
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_HOVER,
    COLOR_SECUNDARIO,
    COLOR_SECUNDARIO_HOVER,
    COLOR_TEXTO,
)


class DialogoBuscador(QDialog):
    """
    Diálogo simple para introducir el nombre de un lugar.
    Adaptable a pantallas de alta resolución (High-DPI) y tematizado con colores UCO.
    """

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Buscador Arqueo Cid")
        self.resize(400, 150)
        self._lugar: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Título
        titulo = QLabel("Buscador Arqueo Cid")
        titulo.setProperty("heading", "true")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        # Instrucciones
        lbl_instruccion = QLabel("Introduce el pueblo o lugar que deseas explorar:")
        lbl_instruccion.setWordWrap(True)
        lbl_instruccion.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(lbl_instruccion)

        # Caja de texto
        self.edit_lugar = QLineEdit()
        self.edit_lugar.setPlaceholderText("Ej: Burgos, Covarrubias, San Pedro de Arlanza...")
        self.edit_lugar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.edit_lugar.returnPressed.connect(self._aceptar)
        layout.addWidget(self.edit_lugar)

        # Botones
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
            QMessageBox.warning(self, "Campo vacío", "Por favor, introduce el nombre de un lugar antes de buscar.")
            return
        self.accept()

    def lugar(self) -> str:
        return self._lugar

    def _aplicar_estilos(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_FONDO}; }}
            QLabel[heading="true"] {{
                font-size: 14pt; font-weight: bold; color: {COLOR_PRIMARIO};
            }}
            QLabel {{ font-size: 10pt; color: {COLOR_TEXTO}; }}
            QLineEdit {{
                border: 1px solid {COLOR_BORDE};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 10pt;
                background: white;
                selection-background-color: {COLOR_PRIMARIO};
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
