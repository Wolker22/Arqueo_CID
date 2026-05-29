# -*- coding: utf-8 -*-
"""
Pestaña de Datos y Exportación: configuración del flujo de trabajo y productos de salida.
(Adaptada a los estándares de Arqueo-CID, paleta teal de TIZONA, spinboxes nativos,
con scroll interno y desplegables con popup forzado)
"""

from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QGroupBox,
    QGridLayout,
    QPushButton,
    QFileDialog,
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
    GENERAR_IMAGENES_PNG,
    NORMALIZAR_IMAGENES,
    EXPORTAR_STACK_MULTIBANDA,
    NORMALIZAR_STACK,
    INCLUIR_MASCARA_STACK,
    GENERAR_METADATOS_JSON,
    GENERAR_MANIFIESTO_IA,
    PNG_PERC_LOW,
    PNG_PERC_HIGH,
    STACK_PERC_LOW,
    STACK_PERC_HIGH,
    MODOS_EJECUCION,
    MODO_EJECUCION_DEFAULT,
    COBERTURAS_ETIQUETAS,
    TIPO_PRODUCTO_OPCIONES_POR_COBERTURA,
    TIPO_PRODUCTO_DEFAULT,
    TAB_DATOS_LABEL_MODO,
    TAB_DATOS_TOOLTIP_MODO,
    TAB_DATOS_LABEL_CARPETA_LAZ,
    TAB_DATOS_TOOLTIP_CARPETA_LAZ,
    TAB_DATOS_LABEL_CARPETA_RESULTADOS,
    TAB_DATOS_TOOLTIP_CARPETA_RESULTADOS,
    TAB_DATOS_CHECK_LIMPIAR_DESCARGAS,
    TAB_DATOS_CHECK_LIMPIAR_PROCESADOS,
    TAB_DATOS_TOOLTIP_LIMPIAR,
    TAB_DATOS_LABEL_COBERTURA,
    TAB_DATOS_TOOLTIP_COBERTURA,
    TAB_DATOS_LABEL_TIPO_PRODUCTO,
    TAB_DATOS_TOOLTIP_TIPO_PRODUCTO,
    TAB_DATOS_CHECK_PNG,
    TAB_DATOS_TOOLTIP_PNG,
    TAB_DATOS_CHECK_NORM_PNG,
    TAB_DATOS_TOOLTIP_NORM_PNG,
    TAB_DATOS_LABEL_PNG_BAJO,
    TAB_DATOS_LABEL_PNG_ALTO,
    TAB_DATOS_TOOLTIP_PERCENTIL_BAJO,
    TAB_DATOS_TOOLTIP_PERCENTIL_ALTO,
    TAB_DATOS_CHECK_STACK,
    TAB_DATOS_TOOLTIP_STACK,
    TAB_DATOS_CHECK_NORM_STACK,
    TAB_DATOS_TOOLTIP_NORM_STACK,
    TAB_DATOS_CHECK_MASCARA,
    TAB_DATOS_TOOLTIP_MASCARA,
    TAB_DATOS_LABEL_STACK_BAJO,
    TAB_DATOS_LABEL_STACK_ALTO,
    TAB_DATOS_TOOLTIP_PERCENTIL_STACK_BAJO,
    TAB_DATOS_TOOLTIP_PERCENTIL_STACK_ALTO,
    TAB_DATOS_CHECK_JSON,
    TAB_DATOS_TOOLTIP_JSON,
    TAB_DATOS_CHECK_MANIFEST,
    TAB_DATOS_TOOLTIP_MANIFEST,
    COMBO_POPUP_STYLE,
)
from ....utils.logging import get_logger

logger = get_logger("gui.tabs.datos")


class TabDatos(QWidget):
    """
    Pestaña de configuración de datos y exportación para Tizona.
    Permite seleccionar rutas, modo de ejecución, cobertura, tipo de producto,
    y qué productos generar (PNG, stack IA, metadatos).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._aplicar_hoja_estilos()

    def setup_ui(self):
        """Construye la interfaz de la pestaña."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Área de scroll para ventanas pequeñas
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---------- Flujo de trabajo y directorios ----------
        grupo_rutas = QGroupBox("Flujo de trabajo y Directorios")
        grid_rutas = QGridLayout()
        grid_rutas.setVerticalSpacing(10)

        # Modo de ejecución
        lbl_modo = QLabel(TAB_DATOS_LABEL_MODO)
        lbl_modo.setProperty("heading", "true")
        self.combo_modo = QComboBox()
        self.combo_modo.addItems(MODOS_EJECUCION)
        self.combo_modo.setToolTip(TAB_DATOS_TOOLTIP_MODO)
        self.combo_modo.setStyleSheet(COMBO_POPUP_STYLE)
        grid_rutas.addWidget(lbl_modo, 0, 0)
        grid_rutas.addWidget(self.combo_modo, 0, 1, 1, 3)

        # Carpeta de descarga (LAZ)
        lbl_desc = QLabel(TAB_DATOS_LABEL_CARPETA_LAZ)
        self.ruta_descarga = QLineEdit()
        self.ruta_descarga.setPlaceholderText("Directorio para archivos descargados o locales...")
        self.ruta_descarga.setToolTip(TAB_DATOS_TOOLTIP_CARPETA_LAZ)
        self.btn_desc = QPushButton("Examinar...")
        self.btn_desc.clicked.connect(
            lambda: self._seleccionar_carpeta(self.ruta_descarga, "Seleccionar carpeta de LAZ")
        )
        self.check_limpiar_descargas = QCheckBox(TAB_DATOS_CHECK_LIMPIAR_DESCARGAS)
        self.check_limpiar_descargas.setToolTip(TAB_DATOS_TOOLTIP_LIMPIAR)
        grid_rutas.addWidget(lbl_desc, 1, 0)
        grid_rutas.addWidget(self.ruta_descarga, 1, 1)
        grid_rutas.addWidget(self.btn_desc, 1, 2)
        grid_rutas.addWidget(self.check_limpiar_descargas, 1, 3)

        # Carpeta de resultados
        lbl_proc = QLabel(TAB_DATOS_LABEL_CARPETA_RESULTADOS)
        self.ruta_procesados = QLineEdit()
        self.ruta_procesados.setPlaceholderText("Directorio para MDT, Derivados e Imágenes...")
        self.ruta_procesados.setToolTip(TAB_DATOS_TOOLTIP_CARPETA_RESULTADOS)
        self.btn_proc = QPushButton("Examinar...")
        self.btn_proc.clicked.connect(
            lambda: self._seleccionar_carpeta(self.ruta_procesados, "Seleccionar carpeta de resultados")
        )
        self.check_limpiar_procesados = QCheckBox(TAB_DATOS_CHECK_LIMPIAR_PROCESADOS)
        self.check_limpiar_procesados.setToolTip(TAB_DATOS_TOOLTIP_LIMPIAR)
        grid_rutas.addWidget(lbl_proc, 2, 0)
        grid_rutas.addWidget(self.ruta_procesados, 2, 1)
        grid_rutas.addWidget(self.btn_proc, 2, 2)
        grid_rutas.addWidget(self.check_limpiar_procesados, 2, 3)

        # Estilo para los botones Examinar
        for btn in [self.btn_desc, self.btn_proc]:
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

        # Cobertura
        lbl_cobertura = QLabel(TAB_DATOS_LABEL_COBERTURA)
        self.combo_cobertura = QComboBox()
        self.combo_cobertura.addItems(COBERTURAS_ETIQUETAS)
        self.combo_cobertura.setToolTip(TAB_DATOS_TOOLTIP_COBERTURA)
        self.combo_cobertura.currentIndexChanged.connect(self._actualizar_tipo_producto)
        self.combo_cobertura.setStyleSheet(COMBO_POPUP_STYLE)
        grid_rutas.addWidget(lbl_cobertura, 3, 0)
        grid_rutas.addWidget(self.combo_cobertura, 3, 1)

        # Tipo de producto (RGB/IRC/COL/etc.)
        lbl_tipo = QLabel(TAB_DATOS_LABEL_TIPO_PRODUCTO)
        self.combo_tipo_producto = QComboBox()
        self.combo_tipo_producto.setToolTip(TAB_DATOS_TOOLTIP_TIPO_PRODUCTO)
        self.combo_tipo_producto.setStyleSheet(COMBO_POPUP_STYLE)
        grid_rutas.addWidget(lbl_tipo, 3, 2)
        grid_rutas.addWidget(self.combo_tipo_producto, 3, 3)

        grupo_rutas.setLayout(grid_rutas)
        layout.addWidget(grupo_rutas)

        # Inicializar tipos de producto según cobertura por defecto
        self._actualizar_tipo_producto()

        # ---------- Productos de Visualización ----------
        grupo_vis = QGroupBox("Productos de Visualización")
        grid_vis = QGridLayout()
        grid_vis.setVerticalSpacing(8)

        self.check_png = QCheckBox(TAB_DATOS_CHECK_PNG)
        self.check_png.setChecked(GENERAR_IMAGENES_PNG)
        self.check_png.setToolTip(TAB_DATOS_TOOLTIP_PNG)
        self.check_norm_png = QCheckBox(TAB_DATOS_CHECK_NORM_PNG)
        self.check_norm_png.setChecked(NORMALIZAR_IMAGENES)
        self.check_norm_png.setToolTip(TAB_DATOS_TOOLTIP_NORM_PNG)
        self.check_png.toggled.connect(self._actualizar_dependencias_png)

        self.png_perc_low = QDoubleSpinBox()
        self.png_perc_low.setRange(0.0, 49.9)
        self.png_perc_low.setSingleStep(0.5)
        self.png_perc_low.setDecimals(1)
        self.png_perc_low.setValue(PNG_PERC_LOW)
        self.png_perc_low.setToolTip(TAB_DATOS_TOOLTIP_PERCENTIL_BAJO)
        self.png_perc_high = QDoubleSpinBox()
        self.png_perc_high.setRange(50.0, 100.0)
        self.png_perc_high.setSingleStep(0.5)
        self.png_perc_high.setDecimals(1)
        self.png_perc_high.setValue(PNG_PERC_HIGH)
        self.png_perc_high.setToolTip(TAB_DATOS_TOOLTIP_PERCENTIL_ALTO)
        self.check_norm_png.toggled.connect(self._actualizar_percentiles_png)

        grid_vis.addWidget(self.check_png, 0, 0, 1, 2)
        grid_vis.addWidget(self.check_norm_png, 1, 0)
        grid_vis.addWidget(QLabel(TAB_DATOS_LABEL_PNG_BAJO), 1, 1)
        grid_vis.addWidget(self.png_perc_low, 1, 2)
        grid_vis.addWidget(QLabel(TAB_DATOS_LABEL_PNG_ALTO), 1, 3)
        grid_vis.addWidget(self.png_perc_high, 1, 4)

        grupo_vis.setLayout(grid_vis)
        layout.addWidget(grupo_vis)

        # ---------- Productos para Inteligencia Artificial ----------
        grupo_ia = QGroupBox("Productos para Inteligencia Artificial")
        grid_ia = QGridLayout()
        grid_ia.setVerticalSpacing(8)

        self.check_stack = QCheckBox(TAB_DATOS_CHECK_STACK)
        self.check_stack.setChecked(EXPORTAR_STACK_MULTIBANDA)
        self.check_stack.setToolTip(TAB_DATOS_TOOLTIP_STACK)
        self.check_norm_stack = QCheckBox(TAB_DATOS_CHECK_NORM_STACK)
        self.check_norm_stack.setChecked(NORMALIZAR_STACK)
        self.check_norm_stack.setToolTip(TAB_DATOS_TOOLTIP_NORM_STACK)
        self.check_mascara = QCheckBox(TAB_DATOS_CHECK_MASCARA)
        self.check_mascara.setChecked(INCLUIR_MASCARA_STACK)
        self.check_mascara.setToolTip(TAB_DATOS_TOOLTIP_MASCARA)
        self.check_stack.toggled.connect(self._actualizar_dependencias_stack)

        self.stack_perc_low = QDoubleSpinBox()
        self.stack_perc_low.setRange(0.0, 49.9)
        self.stack_perc_low.setSingleStep(0.5)
        self.stack_perc_low.setDecimals(1)
        self.stack_perc_low.setValue(STACK_PERC_LOW)
        self.stack_perc_low.setToolTip(TAB_DATOS_TOOLTIP_PERCENTIL_STACK_BAJO)
        self.stack_perc_high = QDoubleSpinBox()
        self.stack_perc_high.setRange(50.0, 100.0)
        self.stack_perc_high.setSingleStep(0.5)
        self.stack_perc_high.setDecimals(1)
        self.stack_perc_high.setValue(STACK_PERC_HIGH)
        self.stack_perc_high.setToolTip(TAB_DATOS_TOOLTIP_PERCENTIL_STACK_ALTO)
        self.check_norm_stack.toggled.connect(self._actualizar_percentiles_stack)

        grid_ia.addWidget(self.check_stack, 0, 0, 1, 2)
        grid_ia.addWidget(self.check_norm_stack, 1, 0)
        grid_ia.addWidget(QLabel(TAB_DATOS_LABEL_STACK_BAJO), 1, 1)
        grid_ia.addWidget(self.stack_perc_low, 1, 2)
        grid_ia.addWidget(QLabel(TAB_DATOS_LABEL_STACK_ALTO), 1, 3)
        grid_ia.addWidget(self.stack_perc_high, 1, 4)
        grid_ia.addWidget(self.check_mascara, 2, 0, 1, 5)

        grupo_ia.setLayout(grid_ia)
        layout.addWidget(grupo_ia)

        # ---------- Metadatos y Reproducibilidad ----------
        grupo_meta = QGroupBox("Metadatos y Reproducibilidad")
        grid_meta = QGridLayout()

        self.check_json = QCheckBox(TAB_DATOS_CHECK_JSON)
        self.check_json.setChecked(GENERAR_METADATOS_JSON)
        self.check_json.setToolTip(TAB_DATOS_TOOLTIP_JSON)

        self.check_manifest = QCheckBox(TAB_DATOS_CHECK_MANIFEST)
        self.check_manifest.setChecked(GENERAR_MANIFIESTO_IA)
        self.check_manifest.setToolTip(TAB_DATOS_TOOLTIP_MANIFEST)
        self.check_manifest.setEnabled(False)  # se activa si stack está activo

        grid_meta.addWidget(self.check_json, 0, 0)
        grid_meta.addWidget(self.check_manifest, 1, 0)

        grupo_meta.setLayout(grid_meta)
        layout.addWidget(grupo_meta)

        layout.addStretch()
        scroll.setWidget(w)
        main_layout.addWidget(scroll)

        # Estado inicial de dependencias
        self._actualizar_dependencias_png()
        self._actualizar_dependencias_stack()

    # ------------------------------------------------------------------
    # Métodos internos para actualizar opciones de tipo de producto
    # ------------------------------------------------------------------
    def _actualizar_tipo_producto(self):
        """Actualiza el contenido del combo de tipo de producto según la cobertura seleccionada."""
        idx = self.combo_cobertura.currentIndex()
        opciones = TIPO_PRODUCTO_OPCIONES_POR_COBERTURA.get(idx, ["Todos"])
        self.combo_tipo_producto.clear()
        self.combo_tipo_producto.addItems(opciones)
        # Seleccionar un valor por defecto adecuado
        if idx == 0:  # 1ª cobertura -> COL por defecto
            default = "COL"
        elif idx == 1:  # 2ª cobertura -> IRC por defecto
            default = TIPO_PRODUCTO_DEFAULT
        else:  # 3ª cobertura -> Todos
            default = "Todos"
        idx_default = self.combo_tipo_producto.findText(default)
        if idx_default >= 0:
            self.combo_tipo_producto.setCurrentIndex(idx_default)
        self.combo_tipo_producto.setEnabled(True)

    # ------------------------------------------------------------------
    # Habilitar/deshabilitar controles según dependencias
    # ------------------------------------------------------------------
    def _actualizar_dependencias_png(self):
        png_activo = self.check_png.isChecked()
        self.check_norm_png.setEnabled(png_activo)
        if not png_activo:
            self.check_norm_png.setChecked(False)
        self._actualizar_percentiles_png()

    def _actualizar_percentiles_png(self):
        activo = self.check_png.isChecked() and self.check_norm_png.isChecked()
        self.png_perc_low.setEnabled(activo)
        self.png_perc_high.setEnabled(activo)

    def _actualizar_dependencias_stack(self):
        stack_activo = self.check_stack.isChecked()
        self.check_norm_stack.setEnabled(stack_activo)
        self.check_mascara.setEnabled(stack_activo)
        self.check_manifest.setEnabled(stack_activo)
        if not stack_activo:
            self.check_norm_stack.setChecked(False)
        self._actualizar_percentiles_stack()

    def _actualizar_percentiles_stack(self):
        activo = self.check_stack.isChecked() and self.check_norm_stack.isChecked()
        self.stack_perc_low.setEnabled(activo)
        self.stack_perc_high.setEnabled(activo)

    # ------------------------------------------------------------------
    # Selección de carpetas
    # ------------------------------------------------------------------
    def _seleccionar_carpeta(self, line_edit, titulo):
        """Abre un diálogo para seleccionar carpeta y la asigna al QLineEdit."""
        carpeta = QFileDialog.getExistingDirectory(self, titulo)
        if carpeta:
            line_edit.setText(carpeta)

    # ------------------------------------------------------------------
    # Obtención y aplicación de parámetros
    # ------------------------------------------------------------------
    def obtener_parametros(self) -> dict:
        """Devuelve un diccionario con todos los valores actuales de la pestaña."""
        return {
            "modo_ejecucion": self.combo_modo.currentText(),
            "ruta_descarga": self.ruta_descarga.text().strip() or None,
            "ruta_procesados": self.ruta_procesados.text().strip() or None,
            "limpiar_descargas": self.check_limpiar_descargas.isChecked(),
            "limpiar_procesados": self.check_limpiar_procesados.isChecked(),
            "cobertura": self.combo_cobertura.currentIndex(),
            "tipo_producto": self.combo_tipo_producto.currentText(),
            "generar_imagenes_png": self.check_png.isChecked(),
            "normalizar_imagenes": self.check_norm_png.isChecked(),
            "png_perc_low": self.png_perc_low.value(),
            "png_perc_high": self.png_perc_high.value(),
            "exportar_stack": self.check_stack.isChecked(),
            "normalizar_stack": self.check_norm_stack.isChecked(),
            "stack_perc_low": self.stack_perc_low.value(),
            "stack_perc_high": self.stack_perc_high.value(),
            "incluir_mascara_stack": self.check_mascara.isChecked(),
            "generar_metadatos_json": self.check_json.isChecked(),
            "generar_manifiesto_ia": self.check_manifest.isChecked(),
        }

    def aplicar_parametros(self, params: dict):
        """Carga los valores desde un diccionario (por ejemplo, desde un perfil)."""
        if "modo_ejecucion" in params:
            idx = self.combo_modo.findText(params["modo_ejecucion"])
            if idx >= 0:
                self.combo_modo.setCurrentIndex(idx)

        self.ruta_descarga.setText(params.get("ruta_descarga", ""))
        self.ruta_procesados.setText(params.get("ruta_procesados", ""))
        self.check_limpiar_descargas.setChecked(params.get("limpiar_descargas", False))
        self.check_limpiar_procesados.setChecked(params.get("limpiar_procesados", False))

        if "cobertura" in params:
            self.combo_cobertura.setCurrentIndex(params["cobertura"])
            self._actualizar_tipo_producto()
        if "tipo_producto" in params:
            idx = self.combo_tipo_producto.findText(params["tipo_producto"])
            if idx >= 0:
                self.combo_tipo_producto.setCurrentIndex(idx)

        self.check_png.setChecked(params.get("generar_imagenes_png", GENERAR_IMAGENES_PNG))
        self.check_norm_png.setChecked(params.get("normalizar_imagenes", NORMALIZAR_IMAGENES))
        self.png_perc_low.setValue(params.get("png_perc_low", PNG_PERC_LOW))
        self.png_perc_high.setValue(params.get("png_perc_high", PNG_PERC_HIGH))

        self.check_stack.setChecked(params.get("exportar_stack", EXPORTAR_STACK_MULTIBANDA))
        self.check_norm_stack.setChecked(params.get("normalizar_stack", NORMALIZAR_STACK))
        self.stack_perc_low.setValue(params.get("stack_perc_low", STACK_PERC_LOW))
        self.stack_perc_high.setValue(params.get("stack_perc_high", STACK_PERC_HIGH))
        self.check_mascara.setChecked(params.get("incluir_mascara_stack", INCLUIR_MASCARA_STACK))

        self.check_json.setChecked(params.get("generar_metadatos_json", GENERAR_METADATOS_JSON))
        self.check_manifest.setChecked(params.get("generar_manifiesto_ia", GENERAR_MANIFIESTO_IA))

        self._actualizar_dependencias_png()
        self._actualizar_dependencias_stack()

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------
    def _aplicar_hoja_estilos(self):
        """Aplica la hoja de estilos específica para esta pestaña."""
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
            QCheckBox {{ spacing: 6px; font-size: 12px; }}
            QLabel[heading="true"] {{
                font-size: 13px; font-weight: bold; color: {COLOR_PRIMARIO_OSC};
            }}
            QLabel {{ font-size: 12px; color: #333; }}
            QWidget {{ background-color: {COLOR_FONDO}; }}
        """)