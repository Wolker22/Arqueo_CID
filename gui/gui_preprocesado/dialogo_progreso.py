# -*- coding: utf-8 -*-
"""
Diálogo de progreso de Tizona – Minimalista teal (Arqueo-CID)
==============================================================

Muestra el progreso de descarga y procesamiento de LiDAR.
Incluye barras de progreso, tabla de estado por tesela, registro de eventos
y un botón para abrir los resultados en Colada (habilitado al finalizar).
Adaptado estructuralmente a los estándares de Colada, pero con paleta teal.

MODIFICACIÓN: Se añade soporte para pasar la lista de teselas procesadas a Colada.
"""

import time
from typing import List, Optional

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QProgressBar,
    QLabel,
    QPushButton,
    QTextEdit,
    QHBoxLayout,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont

from ...config import (
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLOR_BORDE,
    COLOR_SUPERFICIE,
    COLOR_FONDO,
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    PROGRESO_DIALOG_WIDTH,
    PROGRESO_DIALOG_HEIGHT,
    PROGRESO_TITULO_DEFAULT,
    PROGRESO_TEXTO_CABECERA,
    PROGRESO_LABEL_DESCARGA,
    PROGRESO_LABEL_PROCESAMIENTO,
    PROGRESO_GRUPO_TESELAS,
    PROGRESO_GRUPO_LOG,
    PROGRESO_COLUMNAS_TESELAS,
    PROGRESO_BOTON_COLADA_TEXTO,
    PROGRESO_BOTON_COLADA_TOOLTIP,
    PROGRESO_BOTON_CANCELAR_TEXTO,
    PROGRESO_BOTON_CERRAR_TEXTO,
    PROGRESO_CANCELANDO_TEXTO,
    PROGRESO_FORMATO_TIEMPO,
    PROGRESO_LOG_COLORES,
    PROGRESO_CHUNK_STYLE,
    PROGRESO_BAR_STYLE,
)
from ...utils.logging import get_logger

logger = get_logger('Tizona.gui.progreso')


class DialogoProgreso(QDialog):
    """
    Diálogo no modal que muestra el progreso de las operaciones de Tizona.
    Emite señales para actualizar la interfaz desde hilos secundarios.
    """

    # Señales originales
    _sig_barra_descarga = pyqtSignal(int, str)
    _sig_barra_proc = pyqtSignal(int, str)
    _sig_mensaje = pyqtSignal(str, str)
    _sig_finalizar = pyqtSignal(bool, str)
    _sig_tesela = pyqtSignal(str, str, int)
    # NUEVA SEÑAL: envía ruta de resultados + lista de teselas procesadas
    _sig_abrir_colada_con_teselas = pyqtSignal(str, list)

    def __init__(self, titulo: str = PROGRESO_TITULO_DEFAULT, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(False)
        self.setMinimumSize(PROGRESO_DIALOG_WIDTH, PROGRESO_DIALOG_HEIGHT)
        self._cancelado: bool = False
        self._finalizado: bool = False
        self._tiempo_inicio: float = time.time()
        self._ruta_resultados: Optional[str] = None
        self._nombres_teselas: List[str] = []
        self._setup_ui()
        self._apply_styles()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Crea los widgets y los organiza en el layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Cabecera del diálogo
        titulo_lbl = QLabel(PROGRESO_TEXTO_CABECERA)
        titulo_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {COLOR_PRIMARIO_OSC};"
        )
        layout.addWidget(titulo_lbl)

        # Barra de descarga
        self.label_descarga = QLabel(PROGRESO_LABEL_DESCARGA)
        self.label_descarga.setStyleSheet("font-size: 12px; color: #333;")
        self.barra_descarga = QProgressBar()
        self.barra_descarga.setRange(0, 100)
        self.barra_descarga.setTextVisible(True)
        layout.addWidget(self.label_descarga)
        layout.addWidget(self.barra_descarga)

        # Barra de procesamiento
        self.label_proc = QLabel(PROGRESO_LABEL_PROCESAMIENTO)
        self.label_proc.setStyleSheet("font-size: 12px; color: #333;")
        self.barra_proc = QProgressBar()
        self.barra_proc.setRange(0, 100)
        self.barra_proc.setTextVisible(True)
        layout.addWidget(self.label_proc)
        layout.addWidget(self.barra_proc)

        # Tabla de estado por tesela
        grupo_teselas = QGroupBox(PROGRESO_GRUPO_TESELAS)
        lay_tes = QVBoxLayout(grupo_teselas)
        self.tabla_teselas = QTableWidget()
        self.tabla_teselas.setColumnCount(len(PROGRESO_COLUMNAS_TESELAS))
        self.tabla_teselas.setHorizontalHeaderLabels(PROGRESO_COLUMNAS_TESELAS)
        self.tabla_teselas.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_teselas.setMaximumHeight(200)
        self.tabla_teselas.setEditTriggers(QTableWidget.NoEditTriggers)
        lay_tes.addWidget(self.tabla_teselas)
        layout.addWidget(grupo_teselas)

        # Registro de eventos (log)
        grupo_log = QGroupBox(PROGRESO_GRUPO_LOG)
        lay_log = QVBoxLayout(grupo_log)
        self.texto_log = QTextEdit()
        self.texto_log.setReadOnly(True)
        self.texto_log.setFont(QFont("Consolas", 9))
        self.texto_log.setMinimumHeight(150)
        lay_log.addWidget(self.texto_log)
        layout.addWidget(grupo_log)

        # Botones de acción
        btn_layout = QHBoxLayout()

        self.btn_colada = QPushButton(PROGRESO_BOTON_COLADA_TEXTO)
        self.btn_colada.setToolTip(PROGRESO_BOTON_COLADA_TOOLTIP)
        self.btn_colada.setEnabled(False)
        self.btn_colada.clicked.connect(self._emitir_abrir_colada)

        self.btn_cancelar = QPushButton(PROGRESO_BOTON_CANCELAR_TEXTO)
        self.btn_cerrar = QPushButton(PROGRESO_BOTON_CERRAR_TEXTO)
        self.btn_cerrar.setEnabled(False)

        btn_layout.addWidget(self.btn_colada)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_cerrar)
        layout.addLayout(btn_layout)

        # Conectar señales de botones
        self.btn_cancelar.clicked.connect(self.cancelar)
        self.btn_cerrar.clicked.connect(self.accept)

    def _apply_styles(self) -> None:
        """Aplica la hoja de estilos unificada (teal) y el estilo coral para el botón Colada."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_FONDO};
            }}
            QProgressBar {{
                border: 1px solid {COLOR_BORDE};
                border-radius: 4px;
                text-align: center;
                background-color: white;
                color: {COLOR_PRIMARIO_OSC};
                font-weight: bold;
                font-size: 12px;
                min-height: 24px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_PRIMARIO};
                border-radius: 3px;
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLOR_BORDE};
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 14px;
                background-color: {COLOR_SUPERFICIE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: {COLOR_PRIMARIO_OSC};
            }}
            QTableWidget {{
                border: 1px solid {COLOR_BORDE};
                gridline-color: {COLOR_BORDE};
                background-color: white;
                selection-background-color: {COLOR_PRIMARIO};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {COLOR_SUPERFICIE};
                padding: 6px;
                border: 1px solid {COLOR_BORDE};
                font-weight: bold;
                color: {COLOR_PRIMARIO_OSC};
                font-size: 12px;
            }}
            QTextEdit {{
                border: 1px solid {COLOR_BORDE};
                border-radius: 4px;
                background: white;
                font-family: Consolas;
                font-size: 12px;
            }}
            QPushButton {{
                background-color: {COLOR_PRIMARIO_OSC};
                color: white;
                border: 1px solid {COLOR_PRIMARIO_OSC};
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_PRIMARIO};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_PRIMARIO};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #888;
            }}
        """)

        # Estilo específico para el botón Colada (coral)
        self.btn_colada.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLADA_COLOR_PRIMARIO};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {COLADA_COLOR_PRIMARIO_OSC}; }}
            QPushButton:disabled {{ background-color: #CCCCCC; color: #888888; }}
        """)

    def _connect_signals(self) -> None:
        """Conecta las señales internas a los slots correspondientes."""
        self._sig_barra_descarga.connect(self._set_barra_descarga)
        self._sig_barra_proc.connect(self._set_barra_proc)
        self._sig_mensaje.connect(self._append_log)
        self._sig_finalizar.connect(self._finish)
        self._sig_tesela.connect(self._update_tile)

    # ------------------------------------------------------------------
    # Configuración de visibilidad de barras según modo
    # ------------------------------------------------------------------

    def configurar_barras(self, modo: str) -> None:
        """
        Muestra u oculta las barras de progreso según el modo de ejecución.
        modos: 'Solo procesamiento', 'Solo descarga', 'Descargar y procesar'
        """
        if modo == "Solo procesamiento":
            self.label_descarga.hide()
            self.barra_descarga.hide()
            self.label_proc.show()
            self.barra_proc.show()
        elif modo == "Solo descarga":
            self.label_descarga.show()
            self.barra_descarga.show()
            self.label_proc.hide()
            self.barra_proc.hide()
        else:  # 'Descargar y procesar' o cualquier otro
            self.label_descarga.show()
            self.barra_descarga.show()
            self.label_proc.show()
            self.barra_proc.show()

    # ------------------------------------------------------------------
    # Slots para actualizar la interfaz desde hilos secundarios
    # ------------------------------------------------------------------

    def _set_barra_descarga(self, valor: int, texto: str) -> None:
        self.barra_descarga.setValue(valor)
        self.label_descarga.setText(texto)

    def _set_barra_proc(self, valor: int, texto: str) -> None:
        self.barra_proc.setValue(valor)
        self.label_proc.setText(texto)

    def _append_log(self, tipo: str, mensaje: str) -> None:
        color = PROGRESO_LOG_COLORES.get(tipo, "#333")
        self.texto_log.append(f"<span style='color:{color};'>{mensaje}</span>")
        self.texto_log.verticalScrollBar().setValue(
            self.texto_log.verticalScrollBar().maximum()
        )

    def _finish(self, exito: bool, mensaje: str) -> None:
        """Maneja la finalización del proceso."""
        self._finalizado = True
        self.btn_cancelar.setEnabled(False)
        self.btn_cerrar.setEnabled(True)
        elapsed = time.time() - self._tiempo_inicio
        self.label_proc.setText(mensaje)
        self.label_proc.setStyleSheet(
            f"color: {'#006666' if exito else '#CC0000'}; font-weight: bold;"
        )
        self.texto_log.append(PROGRESO_FORMATO_TIEMPO.format(elapsed / 60.0))
        if exito:
            self.btn_colada.setEnabled(True)

    def _update_tile(self, nombre: str, estado: str, progreso: int) -> None:
        """Actualiza o añade una fila en la tabla de teselas."""
        # Buscar si ya existe
        fila = -1
        for r in range(self.tabla_teselas.rowCount()):
            if self.tabla_teselas.item(r, 0).text() == nombre:
                fila = r
                break
        if fila == -1:
            fila = self.tabla_teselas.rowCount()
            self.tabla_teselas.insertRow(fila)
            self.tabla_teselas.setItem(fila, 0, QTableWidgetItem(nombre))
            self.tabla_teselas.setItem(fila, 1, QTableWidgetItem(""))
            barra = QProgressBar()
            barra.setRange(0, 100)
            barra.setTextVisible(True)
            barra.setStyleSheet(PROGRESO_CHUNK_STYLE + PROGRESO_BAR_STYLE)
            self.tabla_teselas.setCellWidget(fila, 2, barra)
        # Actualizar estado y progreso
        self.tabla_teselas.item(fila, 1).setText(estado)
        barra = self.tabla_teselas.cellWidget(fila, 2)
        if barra:
            barra.setValue(progreso)

    # ------------------------------------------------------------------
    # Métodos públicos para control desde el hilo principal
    # ------------------------------------------------------------------

    def set_ruta_resultados(self, ruta: str) -> None:
        """Establece la ruta de resultados para abrir en Colada."""
        self._ruta_resultados = ruta

    def set_teselas_procesadas(self, nombres: List[str]) -> None:
        """Guarda la lista de teselas que se procesaron (o seleccionaron)."""
        self._nombres_teselas = nombres

    def _emitir_abrir_colada(self) -> None:
        """Emite la señal con la ruta y la lista de teselas para abrir Colada."""
        if self._ruta_resultados and self._nombres_teselas:
            self._sig_abrir_colada_con_teselas.emit(self._ruta_resultados, self._nombres_teselas)
        self.accept()

    def cancelar(self) -> None:
        """Solicita la cancelación del proceso."""
        self._cancelado = True
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.setText(PROGRESO_CANCELANDO_TEXTO)

    def is_canceled(self) -> bool:
        """Devuelve True si el usuario ha solicitado cancelar."""
        return self._cancelado

    # Métodos de actualización (thread-safe mediante señales)
    def actualizar_barra_descarga(self, porcentaje: int, mensaje: str) -> None:
        self._sig_barra_descarga.emit(porcentaje, mensaje)

    def actualizar_barra_procesamiento(self, porcentaje: int, mensaje: str) -> None:
        self._sig_barra_proc.emit(porcentaje, mensaje)

    def log_info(self, mensaje: str) -> None:
        self._sig_mensaje.emit("info", mensaje)

    def log_error(self, mensaje: str) -> None:
        self._sig_mensaje.emit("error", mensaje)

    def log_warning(self, mensaje: str) -> None:
        self._sig_mensaje.emit("warning", mensaje)

    def finalizar(self, exito: bool, mensaje: str) -> None:
        self._sig_finalizar.emit(exito, mensaje)

    def actualizar_estado_tesela(self, nombre: str, estado: str, progreso: int = 0) -> None:
        self._sig_tesela.emit(nombre, estado, progreso)