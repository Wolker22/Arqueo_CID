# -*- coding: utf-8 -*-
"""
Diálogo de Progreso de COLADA – Basado en Tizona
=================================================

Muestra el avance de operaciones largas (entrenamiento, predicción) con:
- Barra de progreso global.
- Tabla de desglose por unidad de trabajo (épocas, teselas).
- Tiempo transcurrido.
- Terminal de registro (log).
- Botones: Cancelar (aborta la operación) y Cerrar (solo habilita al finalizar).

Las señales internas garantizan actualización segura desde hilos secundarios.
"""

import time
import numpy as np
from typing import Optional

from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QTimer
from qgis.PyQt.QtGui import QFont

from ...config import (
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_FONDO,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    COLADA_PROGRESO_TITULO,
    COLADA_PROGRESO_ANCHO,
    COLADA_PROGRESO_ALTO,
    COLADA_PROGRESO_ANCHO_MIN,
    COLADA_PROGRESO_ALTO_MIN,
    COLADA_PROGRESO_CABECERA,
    COLADA_PROGRESO_LABEL_INICIAL,
    COLADA_PROGRESO_BARRA_FORMATO,
    COLADA_PROGRESO_GRUPO_TABLA,
    COLADA_PROGRESO_GRUPO_LOG,
    COLADA_PROGRESO_TABLA_HEADERS,
    COLADA_PROGRESO_BOTON_CANCELAR,
    COLADA_PROGRESO_BOTON_CERRAR,
    COLADA_PROGRESO_CANCELANDO_TEXTO,
    COLADA_LOG_COLOR_ERROR,
    COLADA_LOG_COLOR_WARNING,
    COLADA_LOG_COLOR_SUCCESS,
    COLADA_LOG_COLOR_INFO,
    COLADA_PROGRESO_MINI_BARRA_STYLE,
    COLADA_PROGRESO_TIMESTAMP_FORMAT,
)
from ...utils.logging import get_logger

logger = get_logger('Colada.gui')


class ProgresoCOLADA(QDialog):
    """
    Diálogo de progreso no modal para operaciones largas (entrenamiento/predicción).

    Señales internas (thread-safe):
        _actualizar_global: (porcentaje, texto_operacion)
        _agregar_log: (nivel, mensaje)
        _finalizar: (éxito, mensaje_final)
        _actualizar_fila: (clave, estado, progreso, metrica_extra)
    """

    _actualizar_global = pyqtSignal(int, str)
    _agregar_log = pyqtSignal(str, str)
    _finalizar = pyqtSignal(bool, str)
    _actualizar_fila = pyqtSignal(str, str, int, float)  # clave, estado, progreso, métrica

    def __init__(self, modo: str = 'prediction', parent: Optional['QWidget'] = None) -> None:
        """
        Args:
            modo: 'prediction' o 'training' (afecta título y algunos textos).
            parent: Widget padre.
        """
        super().__init__(parent)
        self.modo = modo
        self._cancelado: bool = False
        self._tiempo_inicio: float = time.time()
        self._timer_actualizacion: Optional[QTimer] = None
        self._finalizado_flag: bool = False

        self.setWindowTitle(COLADA_PROGRESO_TITULO)
        self.setModal(False)
        self.resize(COLADA_PROGRESO_ANCHO, COLADA_PROGRESO_ALTO)
        self.setMinimumSize(COLADA_PROGRESO_ANCHO_MIN, COLADA_PROGRESO_ALTO_MIN)

        self._setup_ui()
        self._conectar_senales()
        self._aplicar_hoja_estilos()

        self._timer_actualizacion = QTimer(self)
        self._timer_actualizacion.timeout.connect(self._actualizar_tiempo_ui)
        self._timer_actualizacion.start(1000)

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Cabecera
        titulo_lbl = QLabel(COLADA_PROGRESO_CABECERA)
        titulo_lbl.setProperty("heading", "true")
        layout.addWidget(titulo_lbl)

        # Barra de progreso global
        self.barra_global = QProgressBar()
        self.barra_global.setRange(0, 100)
        self.barra_global.setFormat(COLADA_PROGRESO_BARRA_FORMATO)
        self.barra_global.setMinimumHeight(28)
        layout.addWidget(self.barra_global)

        # Información de operación y tiempo
        info_layout = QHBoxLayout()
        self.label_operacion = QLabel(COLADA_PROGRESO_LABEL_INICIAL)
        self.label_operacion.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.label_tiempo = QLabel("Tiempo: 0:00")
        self.label_tiempo.setStyleSheet("font-size: 11px; color: #666;")
        info_layout.addWidget(self.label_operacion, 1)
        info_layout.addWidget(self.label_tiempo)
        layout.addLayout(info_layout)

        # Tabla de desglose
        grupo_tabla = QGroupBox(COLADA_PROGRESO_GRUPO_TABLA)
        lay_tabla = QVBoxLayout(grupo_tabla)
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(len(COLADA_PROGRESO_TABLA_HEADERS))
        self.tabla.setHorizontalHeaderLabels(COLADA_PROGRESO_TABLA_HEADERS)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.setMaximumHeight(220)
        self.tabla.setMinimumHeight(160)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        lay_tabla.addWidget(self.tabla)
        layout.addWidget(grupo_tabla)

        # Terminal de log
        grupo_log = QGroupBox(COLADA_PROGRESO_GRUPO_LOG)
        lay_log = QVBoxLayout(grupo_log)
        self.texto_log = QTextEdit()
        self.texto_log.setReadOnly(True)
        self.texto_log.setFont(QFont("Consolas", 10))
        self.texto_log.setMinimumHeight(180)
        lay_log.addWidget(self.texto_log)
        layout.addWidget(grupo_log)

        # Botones
        botones_layout = QHBoxLayout()
        botones_layout.addStretch()
        self.btn_cancelar = QPushButton(COLADA_PROGRESO_BOTON_CANCELAR)
        self.btn_cerrar = QPushButton(COLADA_PROGRESO_BOTON_CERRAR)
        self.btn_cerrar.setEnabled(False)  # Solo se habilita al finalizar
        botones_layout.addWidget(self.btn_cancelar)
        botones_layout.addWidget(self.btn_cerrar)
        layout.addLayout(botones_layout)

        self.btn_cancelar.clicked.connect(self.cancelar)
        self.btn_cerrar.clicked.connect(self.close)

    def _conectar_senales(self) -> None:
        """Conecta las señales internas a los slots."""
        self._actualizar_global.connect(self._set_global)
        self._agregar_log.connect(self._append_log)
        self._finalizar.connect(self._on_finalizado)
        self._actualizar_fila.connect(self._set_fila_tabla)

    # ------------------------------------------------------------------
    # Slots para actualizar UI desde señales (thread-safe)
    # ------------------------------------------------------------------

    def _set_global(self, porcentaje: int, texto_operacion: str) -> None:
        """Actualiza la barra de progreso global y la etiqueta de operación."""
        if self._finalizado_flag:
            return
        self.barra_global.setValue(porcentaje)
        self.label_operacion.setText(texto_operacion)

    def _append_log(self, nivel: str, mensaje: str) -> None:
        """Añade un mensaje al terminal de log con color según nivel."""
        timestamp = time.strftime(COLADA_PROGRESO_TIMESTAMP_FORMAT)
        color_map = {
            "error": COLADA_LOG_COLOR_ERROR,
            "warning": COLADA_LOG_COLOR_WARNING,
            "success": COLADA_LOG_COLOR_SUCCESS,
            "info": COLADA_LOG_COLOR_INFO,
        }
        color = color_map.get(nivel, "#333")
        self.texto_log.append(f"[{timestamp}] <span style='color:{color};'>{mensaje}</span>")
        # Auto-scroll al final
        self.texto_log.verticalScrollBar().setValue(self.texto_log.verticalScrollBar().maximum())

    def _on_finalizado(self, exito: bool, mensaje_final: str) -> None:
        """Maneja la finalización de la operación (éxito/error/cancelación)."""
        if self._finalizado_flag:
            return
        self._finalizado_flag = True

        if self._timer_actualizacion:
            self._timer_actualizacion.stop()
            self._timer_actualizacion = None

        self.btn_cancelar.setEnabled(False)
        self.btn_cerrar.setEnabled(True)
        self.label_operacion.setText(mensaje_final)

        if exito:
            self.barra_global.setValue(100)
            self.log_info("Operación completada con éxito.")
        else:
            self.barra_global.setValue(0)
            self.log_error(mensaje_final)

        elapsed = time.time() - self._tiempo_inicio
        minutos = int(elapsed // 60)
        segundos = int(elapsed % 60)
        self.label_tiempo.setText(f"Tiempo total: {minutos}:{segundos:02d}")

        self.repaint()

    def _actualizar_tiempo_ui(self) -> None:
        """Actualiza el contador de tiempo transcurrido (cada segundo)."""
        if self._finalizado_flag or self._timer_actualizacion is None:
            return
        elapsed = time.time() - self._tiempo_inicio
        minutos = int(elapsed // 60)
        segundos = int(elapsed % 60)
        self.label_tiempo.setText(f"Transcurrido: {minutos}:{segundos:02d}")

    def _set_fila_tabla(self, identificador: str, estado: str, progreso_local: int, metrica_extra: float) -> None:
        """
        Actualiza o crea una fila en la tabla de desglose.

        Args:
            identificador: Clave única para la fila.
            estado: Texto de estado.
            progreso_local: Porcentaje para la mini barra (0-100).
            metrica_extra: Valor numérico (pérdida, etc.) que se muestra en la última columna.
        """
        if self._finalizado_flag:
            return

        # Buscar fila existente
        fila_indice = -1
        for r in range(self.tabla.rowCount()):
            if self.tabla.item(r, 0) is not None and self.tabla.item(r, 0).text() == identificador:
                fila_indice = r
                break

        if fila_indice == -1:
            # Crear nueva fila
            fila_indice = self.tabla.rowCount()
            self.tabla.insertRow(fila_indice)
            self.tabla.setItem(fila_indice, 0, QTableWidgetItem(identificador))
            self.tabla.setItem(fila_indice, 1, QTableWidgetItem(""))
            mini_barra = QProgressBar()
            mini_barra.setRange(0, 100)
            mini_barra.setTextVisible(False)
            mini_barra.setFixedHeight(18)
            mini_barra.setStyleSheet(COLADA_PROGRESO_MINI_BARRA_STYLE)
            self.tabla.setCellWidget(fila_indice, 2, mini_barra)
            self.tabla.setItem(fila_indice, 3, QTableWidgetItem(""))

        # Actualizar estado
        self.tabla.item(fila_indice, 1).setText(estado)

        # Actualizar mini barra
        barra = self.tabla.cellWidget(fila_indice, 2)
        if barra:
            barra.setValue(progreso_local)

        # Actualizar métrica extra (si no es NaN)
        if not np.isnan(metrica_extra):
            self.tabla.item(fila_indice, 3).setText(f"{metrica_extra:.6f}")

    # ------------------------------------------------------------------
    # Métodos públicos para control desde hilos externos
    # ------------------------------------------------------------------

    def actualizar_global(self, porcentaje: int, texto_operacion: str) -> None:
        """Actualiza la barra de progreso global (thread-safe mediante señal)."""
        if self._finalizado_flag:
            return
        self._actualizar_global.emit(int(porcentaje), str(texto_operacion))

    def log_info(self, mensaje: str) -> None:
        """Añade mensaje de nivel info al log (thread-safe)."""
        if not self._finalizado_flag:
            self._agregar_log.emit("info", str(mensaje))

    def log_warning(self, mensaje: str) -> None:
        """Añade mensaje de nivel warning al log (thread-safe)."""
        if not self._finalizado_flag:
            self._agregar_log.emit("warning", str(mensaje))

    def log_error(self, mensaje: str) -> None:
        """Añade mensaje de nivel error al log (thread-safe)."""
        if not self._finalizado_flag:
            self._agregar_log.emit("error", str(mensaje))

    def finalizar(self, exito: bool, mensaje: str) -> None:
        """Marca la operación como finalizada (thread-safe)."""
        if self._finalizado_flag:
            return
        self._finalizar.emit(bool(exito), str(mensaje))

    def actualizar_fila(self, clave: str, estado: str, progreso: int, valor_extra: Optional[float] = None) -> None:
        """
        Actualiza o crea una fila en la tabla de desglose.

        Args:
            clave: Identificador único de la fila.
            estado: Texto de estado.
            progreso: Porcentaje (0-100) para la mini barra.
            valor_extra: Valor numérico opcional (ej. pérdida) para la última columna.
        """
        if self._finalizado_flag:
            return
        valor_float = float(valor_extra) if valor_extra is not None else float('nan')
        self._actualizar_fila.emit(str(clave), str(estado), int(progreso), valor_float)

    def cancelar(self) -> None:
        """Solicita cancelación de la operación en curso."""
        if self._finalizado_flag:
            return
        self._cancelado = True
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.setText(COLADA_PROGRESO_CANCELANDO_TEXTO)

    def is_cancelado(self) -> bool:
        """Devuelve True si el usuario ha solicitado cancelar."""
        return self._cancelado

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Al cerrar, si la operación no ha finalizado, se cancela."""
        if not self._finalizado_flag:
            self.cancelar()
        if self._timer_actualizacion:
            self._timer_actualizacion.stop()
        event.accept()

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_hoja_estilos(self) -> None:
        """Aplica la hoja de estilos definida en config."""
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLADA_COLOR_FONDO}; }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 14px;
                background-color: {COLADA_COLOR_SUPERFICIE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QPushButton {{
                background-color: {COLADA_COLOR_PRIMARIO_OSC};
                color: white;
                border: 1px solid {COLADA_COLOR_PRIMARIO_OSC};
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {COLADA_COLOR_PRIMARIO}; }}
            QPushButton:disabled {{ background-color: {COLADA_COLOR_BORDE}; color: #888; }}
            QLabel[heading="true"] {{
                font-size: 18px;
                font-weight: bold;
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QProgressBar {{
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 4px;
                text-align: center;
                font-weight: bold;
                font-size: 12px;
                background-color: white;
            }}
            QProgressBar::chunk {{ background-color: {COLADA_COLOR_PRIMARIO}; border-radius: 3px; }}
            QTableWidget, QTextEdit {{
                border: 1px solid {COLADA_COLOR_BORDE};
                background-color: white;
                selection-background-color: {COLADA_COLOR_PRIMARIO};
                font-size: 12px;
            }}
            QHeaderView::section {{
                background-color: {COLADA_COLOR_SUPERFICIE};
                border: 1px solid {COLADA_COLOR_BORDE};
                padding: 6px;
                font-weight: bold;
                color: #333;
                font-size: 12px;
            }}
        """)