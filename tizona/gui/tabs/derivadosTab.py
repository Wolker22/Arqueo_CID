# -*- coding: utf-8 -*-
"""
Pestaña de Derivados: selección de productos morfométricos y sus parámetros.
(Adaptada a los estándares de Arqueo-CID, paleta teal de TIZONA, spinboxes nativos,
con scroll interno)
"""

from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
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
    RADIO_OPENNESS,
    RADIO_LRM,
    RADIO_TPI_MULTIESCALA,
    ANGULOS_MULTIDIR,
    DERIVADOS_POR_DEFECTO,
    DERIVADOS_DESCRIPCIONES,
    DERIVADOS_CATEGORIAS,
    SIGMA_CURVATURE_DEFAULT,
    SIGMA_CURVATURE_RANGE,
    SIGMA_CURVATURE_STEP,
    RIDGE_VALLEY_RADIOS_DEFAULT,
    RIDGE_VALLEY_RADIOS_SEPARATOR,
    MRVBF_SCALES_DEFAULT,
    MRVBF_SCALES_SEPARATOR,
    MRVBF_SLOPE_THRESHOLD_DEFAULT,
    MRVBF_SLOPE_THRESHOLD_RANGE,
    MRVBF_SLOPE_THRESHOLD_STEP,
    RADIO_OPENNESS_RANGE,
    RADIO_OPENNESS_STEP,
    RADIO_LRM_RANGE,
    RADIO_LRM_STEP,
    TOOLTIP_RADIO_OPENNESS,
    TOOLTIP_RADIO_LRM,
    TOOLTIP_RADIO_TPI,
    TOOLTIP_ANGULOS_MULTI,
    TOOLTIP_SIGMA_CURVATURE,
    TOOLTIP_RIDGE_VALLEY_RADIOS,
    TOOLTIP_MRVBF_SCALES,
    TOOLTIP_MRVBF_SLOPE_THRESHOLD,
    LABEL_RADIO_OPENNESS,
    LABEL_RADIO_LRM,
    LABEL_RADIO_TPI,
    LABEL_ANGULOS_MULTI,
    LABEL_SIGMA_CURVATURE,
    LABEL_RIDGE_VALLEY_RADIOS,
    LABEL_MRVBF_SCALES,
    LABEL_MRVBF_SLOPE_THRESHOLD,
    GROUP_TITLE_PARAMETROS,
    GROUP_TITLE_DERIVADOS,
    GROUP_TITLE_ESPECIFICOS,
    BUTTON_SELECCIONAR_TODOS,
    BUTTON_DESELECCIONAR_TODOS,
    # Parámetros del filtro de mediana post‑procesado
    APLICAR_FILTRO_MEDIANA_DERIVADOS,
    FILTRO_MEDIANA_TAMANO,
)
from ....utils.logging import get_logger

logger = get_logger("gui.tabs.derivados")


class TabDerivados(QWidget):
    """
    Pestaña de configuración de derivados morfométricos.
    Permite seleccionar qué derivados calcular y ajustar sus parámetros específicos,
    incluyendo un filtro de mediana post‑procesado para reducir ruido.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.check_derivados = {}
        self.paneles_especificos = {}
        self._crear_widgets_parametros()
        self.setup_ui()
        self._aplicar_hoja_estilos()
        # Mostrar paneles para derivados ya marcados
        for clave, cb in self.check_derivados.items():
            if cb.isChecked():
                self._mostrar_panel(clave, True)

    # ------------------------------------------------------------------
    # Creación de paneles específicos (parámetros avanzados)
    # ------------------------------------------------------------------
    def _crear_widgets_parametros(self):
        """Crea los paneles de configuración avanzada para curvaturas, ridge_valley y MRVBF."""

        # --- Panel de Curvaturas (general, vertical, horizontal) ---
        panel_curv = QWidget()
        lay = QGridLayout(panel_curv)
        lay.setContentsMargins(10, 10, 10, 10)

        lbl_curv = QLabel("Curvaturas (general, vertical, horizontal)")
        lbl_curv.setProperty("heading", "true")
        lay.addWidget(lbl_curv, 0, 0, 1, 2)

        self.sigma_curvature = QDoubleSpinBox()
        self.sigma_curvature.setRange(*SIGMA_CURVATURE_RANGE)
        self.sigma_curvature.setSingleStep(SIGMA_CURVATURE_STEP)
        self.sigma_curvature.setValue(SIGMA_CURVATURE_DEFAULT)
        self.sigma_curvature.setToolTip(TOOLTIP_SIGMA_CURVATURE)

        lay.addWidget(QLabel(LABEL_SIGMA_CURVATURE), 1, 0)
        lay.addWidget(self.sigma_curvature, 1, 1)

        panel_curv.hide()
        for k in ["curvature", "curvature_vert", "curvature_horiz"]:
            self.paneles_especificos[k] = panel_curv

        # --- Panel de Ridge / Valley ---
        panel_rv = QWidget()
        lay_rv = QGridLayout(panel_rv)
        lay_rv.setContentsMargins(10, 10, 10, 10)

        lbl_rv = QLabel("Ridge / Valley (crestas y valles)")
        lbl_rv.setProperty("heading", "true")
        lay_rv.addWidget(lbl_rv, 0, 0, 1, 2)

        self.rv_sigmas = QLineEdit(RIDGE_VALLEY_RADIOS_SEPARATOR.join(str(r) for r in RIDGE_VALLEY_RADIOS_DEFAULT))
        self.rv_sigmas.setToolTip(TOOLTIP_RIDGE_VALLEY_RADIOS)
        lay_rv.addWidget(QLabel(LABEL_RIDGE_VALLEY_RADIOS), 1, 0)
        lay_rv.addWidget(self.rv_sigmas, 1, 1)

        panel_rv.hide()
        self.paneles_especificos["ridge_valley"] = panel_rv

        # --- Panel de MRVBF ---
        panel_mrvbf = QWidget()
        lay_mrvbf = QGridLayout(panel_mrvbf)
        lay_mrvbf.setContentsMargins(10, 10, 10, 10)

        lbl_mrvbf = QLabel("MRVBF – Planitud de fondos de valle")
        lbl_mrvbf.setProperty("heading", "true")
        lay_mrvbf.addWidget(lbl_mrvbf, 0, 0, 1, 2)

        self.mrvbf_scales = QLineEdit(MRVBF_SCALES_SEPARATOR.join(str(r) for r in MRVBF_SCALES_DEFAULT))
        self.mrvbf_scales.setToolTip(TOOLTIP_MRVBF_SCALES)
        lay_mrvbf.addWidget(QLabel(LABEL_MRVBF_SCALES), 1, 0)
        lay_mrvbf.addWidget(self.mrvbf_scales, 1, 1)

        self.mrvbf_slope_threshold = QDoubleSpinBox()
        self.mrvbf_slope_threshold.setRange(*MRVBF_SLOPE_THRESHOLD_RANGE)
        self.mrvbf_slope_threshold.setSingleStep(MRVBF_SLOPE_THRESHOLD_STEP)
        self.mrvbf_slope_threshold.setValue(MRVBF_SLOPE_THRESHOLD_DEFAULT)
        self.mrvbf_slope_threshold.setToolTip(TOOLTIP_MRVBF_SLOPE_THRESHOLD)

        lay_mrvbf.addWidget(QLabel(LABEL_MRVBF_SLOPE_THRESHOLD), 2, 0)
        lay_mrvbf.addWidget(self.mrvbf_slope_threshold, 2, 1)

        panel_mrvbf.hide()
        self.paneles_especificos["mrvbf"] = panel_mrvbf

    # ------------------------------------------------------------------
    # Construcción de la interfaz principal
    # ------------------------------------------------------------------
    def setup_ui(self):
        """Construye la interfaz con scroll y grupos."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---------- Parámetros geométricos globales ----------
        grupo_params = QGroupBox(GROUP_TITLE_PARAMETROS)
        grid_params = QGridLayout()
        grid_params.setVerticalSpacing(10)

        self.radio_openness = QDoubleSpinBox()
        self.radio_openness.setRange(*RADIO_OPENNESS_RANGE)
        self.radio_openness.setValue(RADIO_OPENNESS)
        self.radio_openness.setToolTip(TOOLTIP_RADIO_OPENNESS)
        grid_params.addWidget(QLabel(LABEL_RADIO_OPENNESS), 0, 0)
        grid_params.addWidget(self.radio_openness, 0, 1)

        self.radio_lrm = QDoubleSpinBox()
        self.radio_lrm.setRange(*RADIO_LRM_RANGE)
        self.radio_lrm.setValue(RADIO_LRM)
        self.radio_lrm.setToolTip(TOOLTIP_RADIO_LRM)
        grid_params.addWidget(QLabel(LABEL_RADIO_LRM), 0, 2)
        grid_params.addWidget(self.radio_lrm, 0, 3)

        self.radio_tpi = QLineEdit(",".join(str(r) for r in RADIO_TPI_MULTIESCALA))
        self.radio_tpi.setToolTip(TOOLTIP_RADIO_TPI)
        grid_params.addWidget(QLabel(LABEL_RADIO_TPI), 1, 0)
        grid_params.addWidget(self.radio_tpi, 1, 1)

        self.angulos_multi = QLineEdit(",".join(str(a) for a in ANGULOS_MULTIDIR))
        self.angulos_multi.setToolTip(TOOLTIP_ANGULOS_MULTI)
        grid_params.addWidget(QLabel(LABEL_ANGULOS_MULTI), 1, 2)
        grid_params.addWidget(self.angulos_multi, 1, 3)

        grupo_params.setLayout(grid_params)
        layout.addWidget(grupo_params)

        # ---------- Lista de derivados (sin scroll interno, altura fija) ----------
        grupo_lista = QGroupBox(GROUP_TITLE_DERIVADOS)
        lay_lista = QVBoxLayout()

        w2 = QWidget()
        grid_alg = QGridLayout(w2)
        grid_alg.setAlignment(Qt.AlignTop)
        grid_alg.setSpacing(8)
        grid_alg.setContentsMargins(5, 5, 5, 5)

        columna = 0
        todos_default = set(DERIVADOS_POR_DEFECTO)
        for nombre_cat, claves in DERIVADOS_CATEGORIAS.items():
            if not claves:
                continue
            lbl_cat = QLabel(nombre_cat)
            lbl_cat.setProperty("heading", "true")
            grid_alg.addWidget(lbl_cat, 0, columna)
            fila = 1
            for clave in claves:
                cb = QCheckBox(clave)
                cb.setChecked(clave in todos_default)
                cb.setToolTip(DERIVADOS_DESCRIPCIONES.get(clave, clave))
                cb.toggled.connect(lambda checked, c=clave: self._mostrar_panel(c, checked))
                self.check_derivados[clave] = cb
                grid_alg.addWidget(cb, fila, columna)
                fila += 1
            columna += 1

        w2.setMinimumHeight(180)
        lay_lista.addWidget(w2)

        # Botones de selección masiva
        btn_layout = QHBoxLayout()
        btn_todos = QPushButton(BUTTON_SELECCIONAR_TODOS)
        btn_ninguno = QPushButton(BUTTON_DESELECCIONAR_TODOS)
        for btn in [btn_todos, btn_ninguno]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_PRIMARIO_OSC};
                    color: white;
                    border: 1px solid {COLOR_PRIMARIO_OSC};
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ background-color: {COLOR_PRIMARIO}; }}
                QPushButton:pressed {{ background-color: {COLOR_PRIMARIO}; }}
            """)
        btn_todos.clicked.connect(lambda: self._seleccionar_todos(True))
        btn_ninguno.clicked.connect(lambda: self._seleccionar_todos(False))
        btn_layout.addWidget(btn_todos)
        btn_layout.addWidget(btn_ninguno)
        btn_layout.addStretch()
        lay_lista.addLayout(btn_layout)

        grupo_lista.setLayout(lay_lista)
        layout.addWidget(grupo_lista)

        # ---------- Parámetros específicos de derivados (dinámicos) ----------
        grupo_esp = QGroupBox(GROUP_TITLE_ESPECIFICOS)
        grupo_esp.setToolTip("Aquí aparecen los ajustes finos de los derivados seleccionados.")
        self.layout_esp = QVBoxLayout()
        self.layout_esp.setSpacing(6)
        # Añadir todos los paneles (se mostrarán u ocultarán según los checkboxes)
        for panel in set(self.paneles_especificos.values()):
            self.layout_esp.addWidget(panel)
        self.layout_esp.addStretch()
        grupo_esp.setLayout(self.layout_esp)
        layout.addWidget(grupo_esp)

        # ---------- Filtro de mediana post‑procesado (nuevo) ----------
        self.grupo_mediana = QGroupBox("Filtro de mediana post‑procesado")
        self.grupo_mediana.setCheckable(True)
        self.grupo_mediana.setChecked(APLICAR_FILTRO_MEDIANA_DERIVADOS)
        self.grupo_mediana.setToolTip(
            "Aplica un filtro de mediana a los derivados seleccionados para reducir ruido."
        )
        layout_med = QHBoxLayout(self.grupo_mediana)
        self.spin_mediana_tam = QSpinBox()
        self.spin_mediana_tam.setRange(1, 9)
        self.spin_mediana_tam.setSingleStep(2)
        self.spin_mediana_tam.setValue(FILTRO_MEDIANA_TAMANO)
        self.spin_mediana_tam.setToolTip("Tamaño del kernel de mediana (número impar).")
        layout_med.addWidget(QLabel("Tamaño del kernel:"))
        layout_med.addWidget(self.spin_mediana_tam)
        layout_med.addStretch()
        layout.addWidget(self.grupo_mediana)

        layout.addStretch()
        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------
    def _mostrar_panel(self, clave, visible):
        panel = self.paneles_especificos.get(clave)
        if panel:
            panel.setVisible(visible)

    def _seleccionar_todos(self, estado):
        for cb in self.check_derivados.values():
            cb.setChecked(estado)

    # ------------------------------------------------------------------
    # Obtención y aplicación de parámetros
    # ------------------------------------------------------------------
    def obtener_parametros(self) -> dict:
        """Devuelve un diccionario con todos los valores actuales de la pestaña."""
        # Radio TPI
        try:
            radios_tpi = [float(r.strip()) for r in self.radio_tpi.text().split(",") if r.strip()]
            if not radios_tpi:
                radios_tpi = list(RADIO_TPI_MULTIESCALA)
        except ValueError:
            radios_tpi = list(RADIO_TPI_MULTIESCALA)

        # Ángulos multidireccionales
        try:
            angulos = [float(a.strip()) for a in self.angulos_multi.text().split(",") if a.strip()]
            if not angulos:
                angulos = list(ANGULOS_MULTIDIR)
        except ValueError:
            angulos = list(ANGULOS_MULTIDIR)

        # Derivados activos
        derivados = [k for k, cb in self.check_derivados.items() if cb.isChecked()]

        params = {
            "radio_openness": self.radio_openness.value(),
            "radio_lrm": self.radio_lrm.value(),
            "radio_tpi_multiescala": radios_tpi,
            "angulos_multidir": angulos,
            "derivados": derivados,
        }

        # Parámetros específicos solo si los derivados correspondientes están activos
        if any(k in derivados for k in ["curvature", "curvature_vert", "curvature_horiz"]):
            params["sigma_curvature"] = self.sigma_curvature.value()

        if "ridge_valley" in derivados:
            try:
                r = [float(x.strip()) for x in self.rv_sigmas.text().split(",") if x.strip()]
                params["ridge_valley_radios"] = r if r else RIDGE_VALLEY_RADIOS_DEFAULT
            except ValueError:
                params["ridge_valley_radios"] = RIDGE_VALLEY_RADIOS_DEFAULT

        if "mrvbf" in derivados:
            try:
                scales = [float(x.strip()) for x in self.mrvbf_scales.text().split(",") if x.strip()]
                params["mrvbf_scales"] = scales if scales else MRVBF_SCALES_DEFAULT
            except ValueError:
                params["mrvbf_scales"] = MRVBF_SCALES_DEFAULT
            params["mrvbf_slope_threshold"] = self.mrvbf_slope_threshold.value()

        # Filtro de mediana post‑procesado
        params["aplicar_filtro_mediana"] = self.grupo_mediana.isChecked()
        params["filtro_mediana_tamano"] = self.spin_mediana_tam.value()

        return params

    def aplicar_parametros(self, params: dict):
        """Carga los valores desde un diccionario (por ejemplo, desde un perfil)."""
        if "radio_openness" in params:
            self.radio_openness.setValue(params["radio_openness"])
        if "radio_lrm" in params:
            self.radio_lrm.setValue(params["radio_lrm"])
        if "radio_tpi_multiescala" in params:
            self.radio_tpi.setText(",".join(str(r) for r in params["radio_tpi_multiescala"]))
        if "angulos_multidir" in params:
            self.angulos_multi.setText(",".join(str(a) for a in params["angulos_multidir"]))
        if "derivados" in params:
            activos = set(params["derivados"])
            for k, cb in self.check_derivados.items():
                cb.setChecked(k in activos)
        if "sigma_curvature" in params:
            self.sigma_curvature.setValue(params["sigma_curvature"])
        if "ridge_valley_radios" in params:
            self.rv_sigmas.setText(",".join(str(r) for r in params["ridge_valley_radios"]))
        if "mrvbf_scales" in params:
            self.mrvbf_scales.setText(",".join(str(r) for r in params["mrvbf_scales"]))
        if "mrvbf_slope_threshold" in params:
            self.mrvbf_slope_threshold.setValue(params["mrvbf_slope_threshold"])
        if "aplicar_filtro_mediana" in params:
            self.grupo_mediana.setChecked(params["aplicar_filtro_mediana"])
        if "filtro_mediana_tamano" in params:
            self.spin_mediana_tam.setValue(params["filtro_mediana_tamano"])

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
            QCheckBox {{
                spacing: 6px;
                font-size: 12px;
            }}
            QLabel[heading="true"] {{
                font-size: 13px;
                font-weight: bold;
                color: {COLOR_PRIMARIO_OSC};
            }}
            QLabel {{
                font-size: 12px;
                color: #333;
            }}
            QLineEdit {{
                border: 1px solid {COLOR_BORDE};
                border-radius: 3px;
                padding: 4px;
                background-color: white;
                selection-background-color: {COLOR_PRIMARIO};
                font-size: 12px;
            }}
            QWidget {{
                background-color: {COLOR_FONDO};
            }}
        """)