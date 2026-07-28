# -*- coding: utf-8 -*-
"""
Pestaña de Rendimiento: paralelismo, memoria y aceleración hardware.
(Adaptada a los estándares de Arqueo-CID, paleta teal de TIZONA, spinboxes nativos,
con scroll interno y desplegables con popup forzado)
"""

import multiprocessing
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QGroupBox,
    QGridLayout,
    QSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QScrollArea,
    QFrame,
)
from qgis.PyQt.QtCore import Qt

# Importar constantes desde la configuración central
from ....config import (
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLOR_FONDO,
    COLOR_SUPERFICIE,
    COLOR_BORDE,
    COMBO_POPUP_STYLE,
    DESCARGAS_SIMULTANEAS,
    MAX_PROCESOS_SIMULTANEOS,
    USAR_PROCESAMIENTO_BLOQUES,
    TAMANO_BLOQUE,
    MEMORIA_MAX_MB,
    CPU_CORES,
    USAR_PDAL,
    TIMEOUT_DESCARGA,
    PDAL_DECIMATION_STEP,
    PDAL_OUTPUT_TYPE,
    MIN_MEMORIA_LIBRE_MB,
    RENDIMIENTO_GRUPO_RED,
    RENDIMIENTO_GRUPO_HARDWARE,
    RENDIMIENTO_GRUPO_MEMORIA,
    RENDIMIENTO_LABEL_DESC_SIM,
    RENDIMIENTO_LABEL_TIMEOUT,
    RENDIMIENTO_LABEL_USAR_GPU,
    RENDIMIENTO_LABEL_GPU_NO_DISP,
    RENDIMIENTO_LABEL_USAR_GDAL,
    RENDIMIENTO_LABEL_GDAL_NO_DISP,
    RENDIMIENTO_LABEL_USAR_PDAL,
    RENDIMIENTO_LABEL_PDAL_DECIM,
    RENDIMIENTO_LABEL_PDAL_OUT,
    RENDIMIENTO_LABEL_PROC_PARALELO,
    RENDIMIENTO_LABEL_HILOS_TESELAS,
    RENDIMIENTO_LABEL_USAR_BLOQUES,
    RENDIMIENTO_LABEL_TAM_BLOQUE,
    RENDIMIENTO_LABEL_LIMITE_CACHE,
    RENDIMIENTO_LABEL_PAUSAR_RAM,
    RENDIMIENTO_LABEL_HILOS_INTERNOS,
    RENDIMIENTO_TOOLTIP_DESC_SIM,
    RENDIMIENTO_TOOLTIP_TIMEOUT,
    RENDIMIENTO_TOOLTIP_USAR_GPU,
    RENDIMIENTO_TOOLTIP_USAR_GDAL,
    RENDIMIENTO_TOOLTIP_USAR_PDAL,
    RENDIMIENTO_TOOLTIP_PDAL_DECIM,
    RENDIMIENTO_TOOLTIP_PDAL_OUT,
    RENDIMIENTO_TOOLTIP_PROC_PARALELO,
    RENDIMIENTO_TOOLTIP_HILOS_TESELAS,
    RENDIMIENTO_TOOLTIP_USAR_BLOQUES,
    RENDIMIENTO_TOOLTIP_TAM_BLOQUE,
    RENDIMIENTO_TOOLTIP_LIMITE_CACHE,
    RENDIMIENTO_TOOLTIP_PAUSAR_RAM,
    RENDIMIENTO_TOOLTIP_HILOS_INTERNOS,
    RENDIMIENTO_DESC_SIM_RANGE,
    RENDIMIENTO_DESC_SIM_STEP,
    RENDIMIENTO_TIMEOUT_RANGE,
    RENDIMIENTO_TIMEOUT_STEP,
    RENDIMIENTO_PDAL_STEP_RANGE,
    RENDIMIENTO_PDAL_STEP_STEP,
    RENDIMIENTO_PROC_PARALELO_RANGE_MIN,
    RENDIMIENTO_BLOQUE_RANGE,
    RENDIMIENTO_BLOQUE_STEP,
    RENDIMIENTO_MEM_RANGE,
    RENDIMIENTO_MEM_STEP,
    RENDIMIENTO_MIN_MEM_RANGE,
    RENDIMIENTO_MIN_MEM_STEP,
    RENDIMIENTO_HILOS_INTERNOS_RANGE_MIN,
    RENDIMIENTO_HILOS_INTERNOS_DEFAULT,
    RENDIMIENTO_PDAL_OUT_OPCIONES,
    RENDIMIENTO_PROC_PARALELO_DEFAULT,
    RENDIMIENTO_GPU_BLOQUE_MAX_SUGERIDO,
    RENDIMIENTO_HILOS_INTERNOS_MAX,
    # Nuevos parámetros añadidos
    TIFF_COMPRESSION,
    TIFF_BLOCK_SIZE,
    SOLAPE_PORCENTAJE,
    BLEND_WIDTH_DEFAULT,
)
from ....utils.logging import get_logger

from ....utils.entorno import GDAL_DISPONIBLE, PYTORCH_CUDA_DISPONIBLE


logger = get_logger("gui.tabs.rendimiento")


class TabRendimiento(QWidget):
    """
    Pestaña de configuración de rendimiento:
    descargas, aceleración hardware, gestión de memoria y CPU,
    formato GeoTIFF y parámetros avanzados de procesamiento por bloques.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._aplicar_hoja_estilos()
        self._conectar_signals()
        self._actualizar_visibilidad_opciones()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---------- Grupo: Operaciones de red (descarga) ----------
        g1 = QGroupBox(RENDIMIENTO_GRUPO_RED)
        g1_lay = QGridLayout()
        g1_lay.setVerticalSpacing(10)

        self.desc_simultaneas = QSpinBox()
        self.desc_simultaneas.setRange(*RENDIMIENTO_DESC_SIM_RANGE)
        self.desc_simultaneas.setSingleStep(RENDIMIENTO_DESC_SIM_STEP)
        self.desc_simultaneas.setValue(DESCARGAS_SIMULTANEAS)
        self.desc_simultaneas.setToolTip(RENDIMIENTO_TOOLTIP_DESC_SIM)
        g1_lay.addWidget(QLabel(RENDIMIENTO_LABEL_DESC_SIM), 0, 0)
        g1_lay.addWidget(self.desc_simultaneas, 0, 1)

        self.timeout_descarga = QSpinBox()
        self.timeout_descarga.setRange(*RENDIMIENTO_TIMEOUT_RANGE)
        self.timeout_descarga.setSingleStep(RENDIMIENTO_TIMEOUT_STEP)
        self.timeout_descarga.setValue(TIMEOUT_DESCARGA)
        self.timeout_descarga.setToolTip(RENDIMIENTO_TOOLTIP_TIMEOUT)
        g1_lay.addWidget(QLabel(RENDIMIENTO_LABEL_TIMEOUT), 1, 0)
        g1_lay.addWidget(self.timeout_descarga, 1, 1)

        g1.setLayout(g1_lay)
        layout.addWidget(g1)

        # ---------- Grupo: Motores de aceleración hardware ----------
        g3 = QGroupBox(RENDIMIENTO_GRUPO_HARDWARE)
        g3_lay = QGridLayout()
        g3_lay.setVerticalSpacing(10)

        self.check_gpu = QCheckBox(RENDIMIENTO_LABEL_USAR_GPU)
        self.check_gpu.setChecked(False)
        if not PYTORCH_CUDA_DISPONIBLE:
            self.check_gpu.setEnabled(False)
            self.check_gpu.setText(RENDIMIENTO_LABEL_GPU_NO_DISP)
        self.check_gpu.setToolTip(RENDIMIENTO_TOOLTIP_USAR_GPU)
        g3_lay.addWidget(self.check_gpu, 0, 0, 1, 2)

        self.check_gdal = QCheckBox(RENDIMIENTO_LABEL_USAR_GDAL)
        self.check_gdal.setChecked(False)
        if not GDAL_DISPONIBLE:
            self.check_gdal.setEnabled(False)
            self.check_gdal.setText(RENDIMIENTO_LABEL_GDAL_NO_DISP)
        self.check_gdal.setToolTip(RENDIMIENTO_TOOLTIP_USAR_GDAL)
        g3_lay.addWidget(self.check_gdal, 1, 0, 1, 2)

        self.check_pdal = QCheckBox(RENDIMIENTO_LABEL_USAR_PDAL)
        self.check_pdal.setChecked(USAR_PDAL)
        self.check_pdal.setToolTip(RENDIMIENTO_TOOLTIP_USAR_PDAL)
        g3_lay.addWidget(self.check_pdal, 2, 0, 1, 2)

        self.spin_pdal_step = QSpinBox()
        self.spin_pdal_step.setRange(*RENDIMIENTO_PDAL_STEP_RANGE)
        self.spin_pdal_step.setSingleStep(RENDIMIENTO_PDAL_STEP_STEP)
        self.spin_pdal_step.setValue(PDAL_DECIMATION_STEP)
        self.spin_pdal_step.setToolTip(RENDIMIENTO_TOOLTIP_PDAL_DECIM)
        g3_lay.addWidget(QLabel(RENDIMIENTO_LABEL_PDAL_DECIM), 3, 0)
        g3_lay.addWidget(self.spin_pdal_step, 3, 1)

        self.combo_pdal_out = QComboBox()
        self.combo_pdal_out.addItems(RENDIMIENTO_PDAL_OUT_OPCIONES)
        self.combo_pdal_out.setCurrentText(PDAL_OUTPUT_TYPE)
        self.combo_pdal_out.setToolTip(RENDIMIENTO_TOOLTIP_PDAL_OUT)
        self.combo_pdal_out.setStyleSheet(COMBO_POPUP_STYLE)
        g3_lay.addWidget(QLabel(RENDIMIENTO_LABEL_PDAL_OUT), 4, 0)
        g3_lay.addWidget(self.combo_pdal_out, 4, 1)

        g3.setLayout(g3_lay)
        layout.addWidget(g3)

        # ---------- Grupo: Gestión de memoria y CPU ----------
        g2 = QGroupBox(RENDIMIENTO_GRUPO_MEMORIA)
        g2_lay = QGridLayout()
        g2_lay.setVerticalSpacing(10)

        self.check_proc_paralelo = QCheckBox(RENDIMIENTO_LABEL_PROC_PARALELO)
        self.check_proc_paralelo.setChecked(RENDIMIENTO_PROC_PARALELO_DEFAULT)
        self.check_proc_paralelo.setToolTip(RENDIMIENTO_TOOLTIP_PROC_PARALELO)
        g2_lay.addWidget(self.check_proc_paralelo, 0, 0, 1, 2)

        self.proc_paralelo_spin = QSpinBox()
        self.proc_paralelo_spin.setRange(RENDIMIENTO_PROC_PARALELO_RANGE_MIN, CPU_CORES)
        self.proc_paralelo_spin.setValue(MAX_PROCESOS_SIMULTANEOS)
        self.proc_paralelo_spin.setToolTip(RENDIMIENTO_TOOLTIP_HILOS_TESELAS)
        g2_lay.addWidget(QLabel(RENDIMIENTO_LABEL_HILOS_TESELAS), 1, 0)
        g2_lay.addWidget(self.proc_paralelo_spin, 1, 1)

        self.check_bloques = QCheckBox(RENDIMIENTO_LABEL_USAR_BLOQUES)
        self.check_bloques.setChecked(USAR_PROCESAMIENTO_BLOQUES)
        self.check_bloques.setToolTip(RENDIMIENTO_TOOLTIP_USAR_BLOQUES)
        g2_lay.addWidget(self.check_bloques, 2, 0, 1, 2)

        self.spin_bloque = QSpinBox()
        self.spin_bloque.setRange(*RENDIMIENTO_BLOQUE_RANGE)
        self.spin_bloque.setSingleStep(RENDIMIENTO_BLOQUE_STEP)
        self.spin_bloque.setValue(TAMANO_BLOQUE)
        self.spin_bloque.setToolTip(RENDIMIENTO_TOOLTIP_TAM_BLOQUE)
        g2_lay.addWidget(QLabel(RENDIMIENTO_LABEL_TAM_BLOQUE), 3, 0)
        g2_lay.addWidget(self.spin_bloque, 3, 1)

        self.spin_mem_max = QSpinBox()
        self.spin_mem_max.setRange(*RENDIMIENTO_MEM_RANGE)
        self.spin_mem_max.setSingleStep(RENDIMIENTO_MEM_STEP)
        self.spin_mem_max.setValue(MEMORIA_MAX_MB)
        self.spin_mem_max.setToolTip(RENDIMIENTO_TOOLTIP_LIMITE_CACHE)
        g2_lay.addWidget(QLabel(RENDIMIENTO_LABEL_LIMITE_CACHE), 4, 0)
        g2_lay.addWidget(self.spin_mem_max, 4, 1)

        self.spin_min_mem = QSpinBox()
        self.spin_min_mem.setRange(*RENDIMIENTO_MIN_MEM_RANGE)
        self.spin_min_mem.setSingleStep(RENDIMIENTO_MIN_MEM_STEP)
        self.spin_min_mem.setValue(MIN_MEMORIA_LIBRE_MB)
        self.spin_min_mem.setToolTip(RENDIMIENTO_TOOLTIP_PAUSAR_RAM)
        g2_lay.addWidget(QLabel(RENDIMIENTO_LABEL_PAUSAR_RAM), 5, 0)
        g2_lay.addWidget(self.spin_min_mem, 5, 1)

        self.spin_hilos_int = QSpinBox()
        self.spin_hilos_int.setRange(RENDIMIENTO_HILOS_INTERNOS_RANGE_MIN, RENDIMIENTO_HILOS_INTERNOS_MAX)
        self.spin_hilos_int.setValue(RENDIMIENTO_HILOS_INTERNOS_DEFAULT)
        self.spin_hilos_int.setToolTip(RENDIMIENTO_TOOLTIP_HILOS_INTERNOS)
        g2_lay.addWidget(QLabel(RENDIMIENTO_LABEL_HILOS_INTERNOS), 6, 0)
        g2_lay.addWidget(self.spin_hilos_int, 6, 1)

        g2.setLayout(g2_lay)
        layout.addWidget(g2)

        # ---------- Grupo: Formato GeoTIFF (nuevo) ----------
        grupo_tiff = QGroupBox("Formato GeoTIFF")
        lay_tiff = QGridLayout()
        lay_tiff.setVerticalSpacing(10)

        self.combo_compresion = QComboBox()
        self.combo_compresion.addItems(["LERC_ZSTD", "LZW", "DEFLATE", "LZMA"])
        self.combo_compresion.setCurrentText(TIFF_COMPRESSION)
        self.combo_compresion.setToolTip("Algoritmo de compresión para los GeoTIFF de salida.")
        lay_tiff.addWidget(QLabel("Compresión:"), 0, 0)
        lay_tiff.addWidget(self.combo_compresion, 0, 1)

        self.spin_bloque_tiff = QSpinBox()
        self.spin_bloque_tiff.setRange(128, 1024)
        self.spin_bloque_tiff.setSingleStep(128)
        self.spin_bloque_tiff.setValue(TIFF_BLOCK_SIZE)
        self.spin_bloque_tiff.setToolTip("Tamaño de bloque interno (píxeles).")
        lay_tiff.addWidget(QLabel("Tamaño de bloque (px):"), 1, 0)
        lay_tiff.addWidget(self.spin_bloque_tiff, 1, 1)

        grupo_tiff.setLayout(lay_tiff)
        layout.addWidget(grupo_tiff)

        # ---------- Grupo: Procesamiento por bloques avanzado ----------
        grupo_solape = QGroupBox("Procesamiento por bloques (avanzado)")
        lay_solape = QGridLayout()
        lay_solape.setVerticalSpacing(10)

        self.spin_solape_porcentaje = QDoubleSpinBox()
        self.spin_solape_porcentaje.setRange(0.0, 0.8)
        self.spin_solape_porcentaje.setSingleStep(0.05)
        self.spin_solape_porcentaje.setValue(SOLAPE_PORCENTAJE)
        self.spin_solape_porcentaje.setToolTip("Porcentaje de solape entre bloques (0 = sin solape).")
        lay_solape.addWidget(QLabel("Solape entre bloques (%):"), 0, 0)
        lay_solape.addWidget(self.spin_solape_porcentaje, 0, 1)

        self.spin_blend_width = QSpinBox()
        self.spin_blend_width.setRange(5, 100)
        self.spin_blend_width.setValue(BLEND_WIDTH_DEFAULT)
        self.spin_blend_width.setToolTip("Ancho de la zona de fusión suave (píxeles).")
        lay_solape.addWidget(QLabel("Ancho de fusión (px):"), 1, 0)
        lay_solape.addWidget(self.spin_blend_width, 1, 1)

        grupo_solape.setLayout(lay_solape)
        layout.addWidget(grupo_solape)

        layout.addStretch()
        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Señales y dependencias
    # ------------------------------------------------------------------
    def _conectar_signals(self):
        self.check_proc_paralelo.toggled.connect(self._actualizar_visibilidad_opciones)
        self.check_bloques.toggled.connect(self._actualizar_visibilidad_opciones)
        self.check_pdal.toggled.connect(self._actualizar_visibilidad_opciones)
        self.check_gpu.toggled.connect(self._aviso_gpu_bloques)

    def _aviso_gpu_bloques(self, usando_gpu):
        """Si se activa GPU y el tamaño de bloque es demasiado grande, se reduce."""
        if usando_gpu and self.spin_bloque.value() > RENDIMIENTO_GPU_BLOQUE_MAX_SUGERIDO:
            self.spin_bloque.setValue(RENDIMIENTO_GPU_BLOQUE_MAX_SUGERIDO)

    def _actualizar_visibilidad_opciones(self):
        self.proc_paralelo_spin.setEnabled(self.check_proc_paralelo.isChecked())
        self.spin_bloque.setEnabled(self.check_bloques.isChecked())
        pdal_activo = self.check_pdal.isChecked()
        self.spin_pdal_step.setEnabled(pdal_activo)
        self.combo_pdal_out.setEnabled(pdal_activo)

    # ------------------------------------------------------------------
    # Obtención y aplicación de parámetros
    # ------------------------------------------------------------------
    def obtener_parametros(self) -> dict:
        return {
            "descargas_simultaneas": self.desc_simultaneas.value(),
            "timeout_descarga": self.timeout_descarga.value(),
            "procesamiento_paralelo": self.check_proc_paralelo.isChecked(),
            "proc_paralelo": self.proc_paralelo_spin.value(),
            "usar_bloques": self.check_bloques.isChecked(),
            "tamano_bloque": self.spin_bloque.value(),
            "memoria_max_mb": self.spin_mem_max.value(),
            "min_memoria_libre_mb": self.spin_min_mem.value(),
            "usar_gdal": self.check_gdal.isChecked(),
            "usar_gpu": self.check_gpu.isChecked(),
            "usar_pdal": self.check_pdal.isChecked(),
            "pdal_decimation_step": self.spin_pdal_step.value(),
            "pdal_output_type": self.combo_pdal_out.currentText(),
            "max_hilos_procesamiento": self.spin_hilos_int.value(),
            # Nuevos parámetros
            "tiff_compression": self.combo_compresion.currentText(),
            "tiff_block_size": self.spin_bloque_tiff.value(),
            "solape_porcentaje": self.spin_solape_porcentaje.value(),
            "blend_width": self.spin_blend_width.value(),
        }

    def aplicar_parametros(self, params: dict):
        if "descargas_simultaneas" in params:
            self.desc_simultaneas.setValue(params["descargas_simultaneas"])
        if "timeout_descarga" in params:
            self.timeout_descarga.setValue(params["timeout_descarga"])
        if "procesamiento_paralelo" in params:
            self.check_proc_paralelo.setChecked(params["procesamiento_paralelo"])
        if "proc_paralelo" in params:
            self.proc_paralelo_spin.setValue(params["proc_paralelo"])
        if "usar_bloques" in params:
            self.check_bloques.setChecked(params["usar_bloques"])
        if "tamano_bloque" in params:
            self.spin_bloque.setValue(params["tamano_bloque"])
        if "memoria_max_mb" in params:
            self.spin_mem_max.setValue(params["memoria_max_mb"])
        if "min_memoria_libre_mb" in params:
            self.spin_min_mem.setValue(params["min_memoria_libre_mb"])
        if "usar_gdal" in params and GDAL_DISPONIBLE:
            self.check_gdal.setChecked(params["usar_gdal"])
        if "usar_gpu" in params and PYTORCH_CUDA_DISPONIBLE:
            self.check_gpu.setChecked(params["usar_gpu"])
        if "usar_pdal" in params:
            self.check_pdal.setChecked(params["usar_pdal"])
        if "pdal_decimation_step" in params:
            self.spin_pdal_step.setValue(params["pdal_decimation_step"])
        if "pdal_output_type" in params:
            self.combo_pdal_out.setCurrentText(params["pdal_output_type"])
        if "max_hilos_procesamiento" in params:
            self.spin_hilos_int.setValue(params["max_hilos_procesamiento"])
        if "tiff_compression" in params:
            idx = self.combo_compresion.findText(params["tiff_compression"])
            if idx >= 0:
                self.combo_compresion.setCurrentIndex(idx)
        if "tiff_block_size" in params:
            self.spin_bloque_tiff.setValue(params["tiff_block_size"])
        if "solape_porcentaje" in params:
            self.spin_solape_porcentaje.setValue(params["solape_porcentaje"])
        if "blend_width" in params:
            self.spin_blend_width.setValue(params["blend_width"])
        self._actualizar_visibilidad_opciones()

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------
    def _aplicar_hoja_estilos(self):
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLOR_BORDE};
                border-radius: 6px;
                margin-top: 14px;
                padding-top: 16px;
                background-color: {COLOR_SUPERFICIE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: {COLOR_PRIMARIO_OSC};
            }}
            QCheckBox {{ spacing: 6px; font-size: 12px; }}
            QLabel {{ font-size: 12px; color: #333; }}
            QLabel[heading="true"] {{
                font-size: 13px; font-weight: bold; color: {COLOR_PRIMARIO_OSC};
            }}
            QWidget {{ background-color: {COLOR_FONDO}; }}
        """)