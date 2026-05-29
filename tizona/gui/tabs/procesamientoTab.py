# -*- coding: utf-8 -*-
"""
Pestaña de Procesamiento: filtrado de suelo, suavizado, bordes y parámetros del MDT.
(Adaptada a los estándares de Arqueo-CID, paleta teal de TIZONA, controles nativos,
con scroll interno y desplegables con popup forzado)
"""

from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QGridLayout,
    QComboBox,
    QSpinBox,
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
    USAR_CLASIFICACION_EXISTENTE,
    GAUSSIAN_BLUR_SIGMA,
    PADDING_REFLECT_PX,
    SMRF_WINDOW,
    SMRF_SLOPE,
    SMRF_THRESHOLD,
    RESOLUCION_MDT,
    Z_FACTOR_HILLSHADE,
    HILLSHADE_MULTIDIR,
    FILTRO_SUELO_OPCIONES,
    FILTRO_SUELO_VALORES,
    CHECK_USAR_CLASIFICACION_TEXTO,
    CHECK_USAR_CLASIFICACION_TOOLTIP,
    CHECK_SMRF_AVANZADO_TEXTO,
    CHECK_SMRF_AVANZADO_TOOLTIP,
    LABEL_ALGORITMO,
    LABEL_VENTANA,
    LABEL_PENDIENTE,
    LABEL_UMBRAL,
    LABEL_RESOLUCION,
    LABEL_Z_FACTOR,
    LABEL_MULTIDIR,
    LABEL_GAUSSIAN_SIGMA,
    LABEL_PADDING,
    TOOLTIP_SMRF_WINDOW,
    TOOLTIP_SMRF_SLOPE,
    TOOLTIP_SMRF_THRESHOLD,
    TOOLTIP_RESOLUCION,
    TOOLTIP_Z_FACTOR,
    TOOLTIP_MULTIDIR,
    TOOLTIP_GAUSSIAN_SIGMA,
    TOOLTIP_PADDING,
    SMRF_WINDOW_RANGE,
    SMRF_WINDOW_STEP,
    SMRF_SLOPE_RANGE,
    SMRF_SLOPE_STEP,
    SMRF_THRESHOLD_RANGE,
    SMRF_THRESHOLD_STEP,
    RESOLUCION_MDT_RANGE,
    RESOLUCION_MDT_STEP,
    Z_FACTOR_RANGE,
    Z_FACTOR_STEP,
    GAUSSIAN_SIGMA_RANGE,
    GAUSSIAN_SIGMA_STEP,
    PADDING_REFLECT_RANGE,
    PADDING_REFLECT_STEP,
    GROUP_FILTRADO_TITLE,
    GROUP_MDT_TITLE,
    GROUP_SUAVIZADO_TITLE,
)
from ....utils.logging import get_logger

logger = get_logger("gui.tabs.procesamiento")


class TabProcesamiento(QWidget):
    """
    Pestaña de configuración del procesamiento del MDT:
    filtrado de suelo, parámetros del MDT y suavizado/anti-artefactos.
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

        # ---------- Grupo: Filtrado de suelo ----------
        grupo_filtro = QGroupBox(GROUP_FILTRADO_TITLE)
        grid_filtro = QGridLayout()
        grid_filtro.setVerticalSpacing(10)

        lbl_algoritmo = QLabel(LABEL_ALGORITMO)
        self.combo_filtrado = QComboBox()
        self.combo_filtrado.addItems(FILTRO_SUELO_OPCIONES)
        self.combo_filtrado.setToolTip(
            "Elige el algoritmo para eliminar puntos de vegetación/edificios "
            "y obtener el suelo desnudo.\n"
            "SMRF es el más rápido y fiable en terrenos arqueológicos.\n"
            "CSF funciona mejor en zonas con edificios.\n"
            "Ninguno usa la nube original sin filtrar."
        )
        self.combo_filtrado.setStyleSheet(COMBO_POPUP_STYLE)
        grid_filtro.addWidget(lbl_algoritmo, 0, 0)
        grid_filtro.addWidget(self.combo_filtrado, 0, 1)

        self.check_usar_clasificacion = QCheckBox(CHECK_USAR_CLASIFICACION_TEXTO)
        self.check_usar_clasificacion.setChecked(USAR_CLASIFICACION_EXISTENTE)
        self.check_usar_clasificacion.setToolTip(CHECK_USAR_CLASIFICACION_TOOLTIP)
        grid_filtro.addWidget(self.check_usar_clasificacion, 1, 0, 1, 2)

        self.check_smrf_avanzado = QCheckBox(CHECK_SMRF_AVANZADO_TEXTO)
        self.check_smrf_avanzado.setChecked(False)
        self.check_smrf_avanzado.setToolTip(CHECK_SMRF_AVANZADO_TOOLTIP)
        grid_filtro.addWidget(self.check_smrf_avanzado, 2, 0, 1, 2)

        # Panel de parámetros avanzados (SMRF/CSF)
        self.widget_smrf = QWidget()
        smrf_layout = QGridLayout(self.widget_smrf)
        smrf_layout.setContentsMargins(20, 0, 0, 0)
        smrf_layout.setVerticalSpacing(8)

        self.smrf_window = QSpinBox()
        self.smrf_window.setRange(*SMRF_WINDOW_RANGE)
        self.smrf_window.setSingleStep(SMRF_WINDOW_STEP)
        self.smrf_window.setValue(SMRF_WINDOW)
        self.smrf_window.setToolTip(TOOLTIP_SMRF_WINDOW)
        smrf_layout.addWidget(QLabel(LABEL_VENTANA), 0, 0)
        smrf_layout.addWidget(self.smrf_window, 0, 1)

        self.smrf_slope = QDoubleSpinBox()
        self.smrf_slope.setRange(*SMRF_SLOPE_RANGE)
        self.smrf_slope.setSingleStep(SMRF_SLOPE_STEP)
        self.smrf_slope.setDecimals(2)
        self.smrf_slope.setValue(SMRF_SLOPE)
        self.smrf_slope.setToolTip(TOOLTIP_SMRF_SLOPE)
        smrf_layout.addWidget(QLabel(LABEL_PENDIENTE), 1, 0)
        smrf_layout.addWidget(self.smrf_slope, 1, 1)

        self.smrf_threshold = QDoubleSpinBox()
        self.smrf_threshold.setRange(*SMRF_THRESHOLD_RANGE)
        self.smrf_threshold.setSingleStep(SMRF_THRESHOLD_STEP)
        self.smrf_threshold.setDecimals(1)
        self.smrf_threshold.setValue(SMRF_THRESHOLD)
        self.smrf_threshold.setToolTip(TOOLTIP_SMRF_THRESHOLD)
        smrf_layout.addWidget(QLabel(LABEL_UMBRAL), 2, 0)
        smrf_layout.addWidget(self.smrf_threshold, 2, 1)

        grid_filtro.addWidget(self.widget_smrf, 3, 0, 1, 2)
        grupo_filtro.setLayout(grid_filtro)
        layout.addWidget(grupo_filtro)

        # ---------- Grupo: Parámetros del MDT ----------
        grupo_mdt = QGroupBox(GROUP_MDT_TITLE)
        grid_mdt = QGridLayout()
        grid_mdt.setVerticalSpacing(10)

        self.res_mdt = QDoubleSpinBox()
        self.res_mdt.setRange(*RESOLUCION_MDT_RANGE)
        self.res_mdt.setSingleStep(RESOLUCION_MDT_STEP)
        self.res_mdt.setDecimals(2)
        self.res_mdt.setValue(RESOLUCION_MDT)
        self.res_mdt.setToolTip(TOOLTIP_RESOLUCION)
        grid_mdt.addWidget(QLabel(LABEL_RESOLUCION), 0, 0)
        grid_mdt.addWidget(self.res_mdt, 0, 1)

        self.z_factor = QDoubleSpinBox()
        self.z_factor.setRange(*Z_FACTOR_RANGE)
        self.z_factor.setSingleStep(Z_FACTOR_STEP)
        self.z_factor.setDecimals(1)
        self.z_factor.setValue(Z_FACTOR_HILLSHADE)
        self.z_factor.setToolTip(TOOLTIP_Z_FACTOR)
        grid_mdt.addWidget(QLabel(LABEL_Z_FACTOR), 1, 0)
        grid_mdt.addWidget(self.z_factor, 1, 1)

        self.multidir = QCheckBox(LABEL_MULTIDIR)
        self.multidir.setChecked(HILLSHADE_MULTIDIR)
        self.multidir.setToolTip(TOOLTIP_MULTIDIR)
        grid_mdt.addWidget(self.multidir, 2, 0, 1, 2)

        grupo_mdt.setLayout(grid_mdt)
        layout.addWidget(grupo_mdt)

        # ---------- Grupo: Anti-artefactos y bordes ----------
        grupo_suav = QGroupBox(GROUP_SUAVIZADO_TITLE)
        grid_suav = QGridLayout()
        grid_suav.setVerticalSpacing(10)

        self.gaussian_sigma = QDoubleSpinBox()
        self.gaussian_sigma.setRange(*GAUSSIAN_SIGMA_RANGE)
        self.gaussian_sigma.setSingleStep(GAUSSIAN_SIGMA_STEP)
        self.gaussian_sigma.setDecimals(1)
        self.gaussian_sigma.setValue(GAUSSIAN_BLUR_SIGMA)
        self.gaussian_sigma.setToolTip(TOOLTIP_GAUSSIAN_SIGMA)
        grid_suav.addWidget(QLabel(LABEL_GAUSSIAN_SIGMA), 0, 0)
        grid_suav.addWidget(self.gaussian_sigma, 0, 1)

        self.padding_reflect = QSpinBox()
        self.padding_reflect.setRange(*PADDING_REFLECT_RANGE)
        self.padding_reflect.setSingleStep(PADDING_REFLECT_STEP)
        self.padding_reflect.setValue(PADDING_REFLECT_PX)
        self.padding_reflect.setToolTip(TOOLTIP_PADDING)
        grid_suav.addWidget(QLabel(LABEL_PADDING), 1, 0)
        grid_suav.addWidget(self.padding_reflect, 1, 1)

        grupo_suav.setLayout(grid_suav)
        layout.addWidget(grupo_suav)

        layout.addStretch()
        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Señales y dependencias
    # ------------------------------------------------------------------
    def _conectar_signals(self):
        self.check_smrf_avanzado.toggled.connect(self.widget_smrf.setVisible)
        self.combo_filtrado.currentIndexChanged.connect(self._actualizar_visibilidad_opciones)

    def _actualizar_visibilidad_opciones(self):
        idx = self.combo_filtrado.currentIndex()
        es_filtro = idx in (0, 1)  # SMRF o CSF
        self.check_smrf_avanzado.setEnabled(es_filtro)
        if not es_filtro:
            self.check_smrf_avanzado.setChecked(False)
        self.widget_smrf.setVisible(self.check_smrf_avanzado.isChecked() and es_filtro)

    # ------------------------------------------------------------------
    # Obtención y aplicación de parámetros
    # ------------------------------------------------------------------
    def obtener_parametros(self) -> dict:
        idx = self.combo_filtrado.currentIndex()
        alg = FILTRO_SUELO_VALORES[idx] if idx < len(FILTRO_SUELO_VALORES) else "smrf"
        return {
            "algoritmo_suelo": alg,
            "usar_clasificacion_existente": self.check_usar_clasificacion.isChecked(),
            "smrf_window": self.smrf_window.value(),
            "smrf_slope": self.smrf_slope.value(),
            "smrf_threshold": self.smrf_threshold.value(),
            "gaussian_blur_sigma": self.gaussian_sigma.value(),
            "padding_reflect_px": self.padding_reflect.value(),
            "resolucion": self.res_mdt.value(),
            "z_factor": self.z_factor.value(),
            "multidirectional": self.multidir.isChecked(),
        }

    def aplicar_parametros(self, params: dict):
        # Algoritmo de suelo
        alg = params.get("algoritmo_suelo", "smrf")
        if alg in FILTRO_SUELO_VALORES:
            idx = FILTRO_SUELO_VALORES.index(alg)
            self.combo_filtrado.setCurrentIndex(idx)
        else:
            self.combo_filtrado.setCurrentIndex(0)  # fallback a SMRF
        # Otros parámetros
        if "usar_clasificacion_existente" in params:
            self.check_usar_clasificacion.setChecked(params["usar_clasificacion_existente"])
        if "smrf_window" in params:
            self.smrf_window.setValue(params["smrf_window"])
        if "smrf_slope" in params:
            self.smrf_slope.setValue(params["smrf_slope"])
        if "smrf_threshold" in params:
            self.smrf_threshold.setValue(params["smrf_threshold"])
        if "gaussian_blur_sigma" in params:
            self.gaussian_sigma.setValue(params["gaussian_blur_sigma"])
        if "padding_reflect_px" in params:
            self.padding_reflect.setValue(params["padding_reflect_px"])
        if "resolucion" in params:
            self.res_mdt.setValue(params["resolucion"])
        if "z_factor" in params:
            self.z_factor.setValue(params["z_factor"])
        if "multidirectional" in params:
            self.multidir.setChecked(params["multidirectional"])
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