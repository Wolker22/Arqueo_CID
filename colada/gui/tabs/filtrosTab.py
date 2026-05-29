# -*- coding: utf-8 -*-
"""
Pestaña de Filtros de COLADA
-----------------------------

Permite seleccionar una tesela y un derivado (o stack) mediante desplegables,
elegir un algoritmo clásico de procesamiento de imagen (Sobel, Laplace, Gaussiano,
Mediana, Canny) y visualizar el resultado en un visor gráfico.

Todos los textos, opciones y estilos se centralizan en config.py.

MODIFICACIÓN: Muestra también los stacks (carpeta 04_IA_STACKS) y permite cargarlos
como imagen multibanda para predicción (aunque aquí se usa solo la primera banda).
"""

import os
from typing import Optional, Tuple, Any

import numpy as np
import rasterio
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QComboBox,
    QSlider,
    QFormLayout,
    QFileDialog,
    QScrollArea,
    QFrame,
)

from ....config import (
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_FONDO,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    FILTROS_GROUP_DATOS,
    FILTROS_GROUP_AJUSTES,
    FILTROS_GROUP_ACCIONES,
    FILTROS_LABEL_TESELA,
    FILTROS_LABEL_DERIVADO,
    FILTROS_LABEL_ALGORITMO,
    FILTROS_BUTTON_EXAMINAR,
    FILTROS_BUTTON_PROCESAR,
    FILTROS_BUTTON_GUARDAR,
    FILTROS_BUTTON_MAPA,
    FILTROS_DIR_SELECCIONADO,
    FILTROS_OPCIONES,
    FILTROS_LABEL_SIGMA,
    FILTROS_LABEL_VENTANA,
    FILTROS_LABEL_CANNY_LOW,
    FILTROS_LABEL_CANNY_HIGH,
    FILTROS_SIGMA_RANGE,
    FILTROS_SIGMA_DEFAULT,
    FILTROS_VENTANA_RANGE,
    FILTROS_VENTANA_DEFAULT,
    FILTROS_CANNY_RANGE,
    FILTROS_CANNY_LOW_DEFAULT,
    FILTROS_CANNY_HIGH_DEFAULT,
    FILTROS_BOTON_NORMAL_STYLE,
    FILTROS_BOTON_PRINCIPAL_STYLE,
    FILTROS_BOTON_SECUNDARIO_STYLE,
)
from ..visor_derivados import VisorDerivados
from ...core.filtros_imagen import aplicar_filtro
from ....utils.logging import get_logger

logger = get_logger('Colada.gui.filtros')


class TabFiltros(QWidget):
    """
    Pestaña de filtros clásicos de imagen.

    Attributes:
        _carpeta_tizona: Carpeta base con resultados de Tizona.
        _imagen_original: Array 2D o 3D con la imagen cargada.
        _imagen_filtrada: Array 2D con el resultado del filtro.
        _profile_original: Perfil de rasterio de la imagen original.
        _nombre_tesela_activa: Nombre de la tesela actual.
        visor_filtros: Visor de imágenes para mostrar resultados.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._carpeta_tizona: Optional[str] = None
        self._imagen_original: Optional[np.ndarray] = None  # Puede ser 2D o 3D
        self._imagen_filtrada: Optional[np.ndarray] = None
        self._profile_original: Optional[Any] = None
        self._nombre_tesela_activa: str = "Ninguna"

        self.visor_filtros = VisorDerivados()
        self._init_ui()
        self._conectar_senales()
        self._aplicar_hoja_estilos()

    # ------------------------------------------------------------------
    # Propiedades para acceso desde el diálogo principal
    # ------------------------------------------------------------------

    @property
    def imagen_resultante(self) -> Optional[np.ndarray]:
        """Devuelve la imagen filtrada (resultado)."""
        return self._imagen_filtrada

    @property
    def perfil_original(self) -> Optional[Any]:
        """Devuelve el perfil de la imagen original."""
        return self._profile_original

    @property
    def nombre_tesela(self) -> str:
        """Devuelve el nombre de la tesela activa."""
        return self._nombre_tesela_activa

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Construye la interfaz: visor a la izquierda, controles a la derecha."""
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.addWidget(self.visor_filtros, 2)

        # Panel derecho con scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QWidget()
        lay_controles = QVBoxLayout(panel)
        lay_controles.setSpacing(6)
        lay_controles.setContentsMargins(8, 8, 8, 8)

        # --- Bloque 1: Selección de archivos ---
        grupo_datos = QGroupBox(FILTROS_GROUP_DATOS)
        lay_datos = QVBoxLayout(grupo_datos)
        lay_datos.setSpacing(4)

        # Selección de directorio base
        lay_dir = QHBoxLayout()
        self.btn_f_buscar_dir = QPushButton(FILTROS_BUTTON_EXAMINAR)
        self._forzar_estilo_boton(self.btn_f_buscar_dir, "secundario")
        self.lbl_f_dir_ruta = QLabel(FILTROS_DIR_SELECCIONADO)
        self.lbl_f_dir_ruta.setStyleSheet("color: #666; font-style: italic; font-size: 10px;")
        self.lbl_f_dir_ruta.setWordWrap(True)
        lay_dir.addWidget(self.btn_f_buscar_dir)
        lay_dir.addWidget(self.lbl_f_dir_ruta, 1)
        lay_datos.addLayout(lay_dir)

        # Combo de teselas
        lay_datos.addWidget(QLabel(FILTROS_LABEL_TESELA))
        self.combo_teselas = QComboBox()
        self.combo_teselas.setMinimumWidth(160)
        self.combo_teselas.setToolTip("Selecciona una tesela para ver sus archivos.")
        lay_datos.addWidget(self.combo_teselas)

        # Combo de derivados/stacks
        lay_datos.addWidget(QLabel(FILTROS_LABEL_DERIVADO))
        self.combo_derivados = QComboBox()
        self.combo_derivados.setMinimumWidth(160)
        self.combo_derivados.setToolTip("Elige el archivo GeoTIFF a procesar (derivado o stack).")
        lay_datos.addWidget(self.combo_derivados)

        lay_controles.addWidget(grupo_datos)

        # --- Bloque 2: Ajustes del filtro ---
        grupo_ajustes = QGroupBox(FILTROS_GROUP_AJUSTES)
        lay_ajustes = QVBoxLayout(grupo_ajustes)
        lay_ajustes.setSpacing(4)

        self.combo_f_tipo = QComboBox()
        self.combo_f_tipo.addItems(FILTROS_OPCIONES)
        lay_ajustes.addWidget(QLabel(FILTROS_LABEL_ALGORITMO))
        lay_ajustes.addWidget(self.combo_f_tipo)

        self.form_sliders = QFormLayout()

        # Sigma (para Gaussiano y Laplaciano)
        self.lbl_sigma = QLabel(FILTROS_LABEL_SIGMA.format(FILTROS_SIGMA_DEFAULT / 10.0))
        self.slider_sigma = QSlider(Qt.Horizontal)
        self.slider_sigma.setRange(*FILTROS_SIGMA_RANGE)
        self.slider_sigma.setValue(FILTROS_SIGMA_DEFAULT)
        self.form_sliders.addRow(self.lbl_sigma, self.slider_sigma)

        # Ventana (para mediana)
        self.lbl_ventana = QLabel(FILTROS_LABEL_VENTANA.format(FILTROS_VENTANA_DEFAULT))
        self.slider_ventana = QSlider(Qt.Horizontal)
        self.slider_ventana.setRange(*FILTROS_VENTANA_RANGE)
        self.slider_ventana.setValue(FILTROS_VENTANA_DEFAULT)
        self.form_sliders.addRow(self.lbl_ventana, self.slider_ventana)

        # Umbrales Canny
        self.lbl_canny_low = QLabel(FILTROS_LABEL_CANNY_LOW.format(FILTROS_CANNY_LOW_DEFAULT))
        self.slider_canny_low = QSlider(Qt.Horizontal)
        self.slider_canny_low.setRange(*FILTROS_CANNY_RANGE)
        self.slider_canny_low.setValue(FILTROS_CANNY_LOW_DEFAULT)
        self.form_sliders.addRow(self.lbl_canny_low, self.slider_canny_low)

        self.lbl_canny_high = QLabel(FILTROS_LABEL_CANNY_HIGH.format(FILTROS_CANNY_HIGH_DEFAULT))
        self.slider_canny_high = QSlider(Qt.Horizontal)
        self.slider_canny_high.setRange(*FILTROS_CANNY_RANGE)
        self.slider_canny_high.setValue(FILTROS_CANNY_HIGH_DEFAULT)
        self.form_sliders.addRow(self.lbl_canny_high, self.slider_canny_high)

        lay_ajustes.addLayout(self.form_sliders)
        lay_controles.addWidget(grupo_ajustes)

        # Botón procesar
        self.btn_f_procesar = QPushButton(FILTROS_BUTTON_PROCESAR)
        self._forzar_estilo_boton(self.btn_f_procesar, "principal")
        lay_controles.addWidget(self.btn_f_procesar)

        # --- Bloque 3: Acciones de salida ---
        grupo_acciones = QGroupBox(FILTROS_GROUP_ACCIONES)
        lay_acciones = QHBoxLayout(grupo_acciones)
        self.btn_f_guardar = QPushButton(FILTROS_BUTTON_GUARDAR)
        self.btn_f_mapa = QPushButton(FILTROS_BUTTON_MAPA)
        self._forzar_estilo_boton(self.btn_f_guardar, "normal")
        self._forzar_estilo_boton(self.btn_f_mapa, "normal")
        lay_acciones.addWidget(self.btn_f_guardar)
        lay_acciones.addWidget(self.btn_f_mapa)
        lay_controles.addWidget(grupo_acciones)

        lay_controles.addStretch()

        scroll.setWidget(panel)
        layout_principal.addWidget(scroll, 1)

    def _forzar_estilo_boton(self, boton: QPushButton, tipo: str = "normal") -> None:
        """Aplica el estilo CSS correspondiente al botón."""
        if tipo == "principal":
            css = FILTROS_BOTON_PRINCIPAL_STYLE
        elif tipo == "secundario":
            css = FILTROS_BOTON_SECUNDARIO_STYLE
        else:
            css = FILTROS_BOTON_NORMAL_STYLE
        boton.setStyleSheet(css)

    def _conectar_senales(self) -> None:
        """Conecta las señales de los widgets a sus slots."""
        self.combo_teselas.currentIndexChanged.connect(self._actualizar_combo_derivados)
        self.combo_derivados.currentIndexChanged.connect(self._cargar_raster)
        self.combo_f_tipo.currentIndexChanged.connect(self._conmutar_sliders)
        self.slider_sigma.valueChanged.connect(
            lambda v: self.lbl_sigma.setText(FILTROS_LABEL_SIGMA.format(v / 10.0))
        )
        self.slider_ventana.valueChanged.connect(
            lambda v: self.lbl_ventana.setText(FILTROS_LABEL_VENTANA.format(v))
        )
        self.slider_canny_low.valueChanged.connect(
            lambda v: self.lbl_canny_low.setText(FILTROS_LABEL_CANNY_LOW.format(v))
        )
        self.slider_canny_high.valueChanged.connect(
            lambda v: self.lbl_canny_high.setText(FILTROS_LABEL_CANNY_HIGH.format(v))
        )
        self.btn_f_procesar.clicked.connect(self._procesar_filtro)
        self._conmutar_sliders()

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------

    def establecer_carpeta_tizona(self, ruta: str, nombres_teselas: Optional[list] = None) -> None:
        """
        Establece la carpeta base que contiene las teselas (estructura Tizona).
        Si se proporciona una lista de nombres, solo esos se añaden al combo.

        Args:
            ruta: Ruta a la carpeta de resultados de Tizona.
            nombres_teselas: Lista opcional de nombres de tesela a mostrar.
        """
        if not ruta or not os.path.isdir(ruta):
            logger.warning(f"Directorio no válido: {ruta}")
            return

        self._carpeta_tizona = os.path.normpath(ruta)
        self.lbl_f_dir_ruta.setText(self._carpeta_tizona)
        self.combo_teselas.clear()
        self.combo_derivados.clear()

        if nombres_teselas is not None:
            for nombre in nombres_teselas:
                # Verificar que existe la subcarpeta de derivados
                if os.path.isdir(os.path.join(self._carpeta_tizona, nombre, "02_DERIVADOS")):
                    self.combo_teselas.addItem(nombre)
        else:
            for item in sorted(os.listdir(self._carpeta_tizona)):
                if os.path.isdir(os.path.join(self._carpeta_tizona, item, "02_DERIVADOS")):
                    self.combo_teselas.addItem(item)

        if self.combo_teselas.count() > 0:
            self.combo_teselas.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    def _actualizar_combo_derivados(self) -> None:
        """Actualiza el combo de derivados al cambiar la tesela."""
        self.combo_derivados.clear()
        tesela = self.combo_teselas.currentText()
        if not tesela:
            return
        self._nombre_tesela_activa = tesela

        # Derivados de 02_DERIVADOS
        ruta_derivados = os.path.join(self._carpeta_tizona, tesela, "02_DERIVADOS")
        if os.path.isdir(ruta_derivados):
            for archivo in sorted(os.listdir(ruta_derivados)):
                if archivo.lower().endswith('.tif'):
                    self.combo_derivados.addItem(archivo)

        # Stacks de 04_IA_STACKS (con prefijo para distinguirlos)
        ruta_stacks = os.path.join(self._carpeta_tizona, tesela, "04_IA_STACKS")
        if os.path.isdir(ruta_stacks):
            for archivo in sorted(os.listdir(ruta_stacks)):
                if archivo.lower().endswith('.tif'):
                    self.combo_derivados.addItem(f"[STACK] {archivo}")

        # Notificar a la pestaña de predicción que la tesela ha cambiado
        if hasattr(self.parent(), 'tab_prediccion'):
            self.parent().tab_prediccion.limpiar_estado()

    def _cargar_raster(self) -> None:
        """Carga el ráster seleccionado (derivado o stack) y lo muestra en el visor."""
        tesela = self.combo_teselas.currentText()
        item_text = self.combo_derivados.currentText()
        if not tesela or not item_text:
            return

        # Detectar si es stack (tiene prefijo "[STACK] ")
        es_stack = item_text.startswith("[STACK] ")
        if es_stack:
            nombre_archivo = item_text[9:]  # quitar "[STACK] "
            ruta_abs = os.path.join(self._carpeta_tizona, tesela, "04_IA_STACKS", nombre_archivo)
        else:
            ruta_abs = os.path.join(self._carpeta_tizona, tesela, "02_DERIVADOS", item_text)

        ruta_abs = os.path.normpath(ruta_abs)

        try:
            with rasterio.open(ruta_abs) as src:
                if src.count > 1:
                    # Stack multibanda: leer todas
                    self._imagen_original = src.read().astype(np.float32)  # shape (bandas, alto, ancho)
                else:
                    # Derivado de 1 banda
                    self._imagen_original = src.read(1).astype(np.float32)  # shape (alto, ancho)

                # Reemplazar nodata por NaN
                if src.nodata is not None:
                    if self._imagen_original.ndim == 2:
                        self._imagen_original[self._imagen_original == src.nodata] = np.nan
                    else:
                        self._imagen_original[self._imagen_original == src.nodata] = np.nan

                self._profile_original = src.profile

            # Mostrar en el visor (si es 3D, mostrar la primera banda)
            if self._imagen_original.ndim == 3:
                mostrar = self._imagen_original[0, :, :]
            else:
                mostrar = self._imagen_original
            self.visor_filtros.mostrar_imagen(mostrar)
            self._imagen_filtrada = mostrar.copy()  # Para filtros, trabajamos sobre la primera banda

            logger.info(f"Ráster cargado: {ruta_abs}")

        except Exception as e:
            logger.error(f"Error al cargar {ruta_abs}: {e}")
            self._imagen_original = None
            self._profile_original = None

    def _conmutar_sliders(self) -> None:
        """Muestra u oculta los sliders según el tipo de filtro seleccionado."""
        # Ocultar todos
        self.lbl_sigma.hide()
        self.slider_sigma.hide()
        self.lbl_ventana.hide()
        self.slider_ventana.hide()
        self.lbl_canny_low.hide()
        self.slider_canny_low.hide()
        self.lbl_canny_high.hide()
        self.slider_canny_high.hide()

        filtro = self.combo_f_tipo.currentText()
        if filtro in ("Desenfoque Gaussiano", "Laplaciano"):
            self.lbl_sigma.show()
            self.slider_sigma.show()
        elif filtro == "Filtro de Mediana":
            self.lbl_ventana.show()
            self.slider_ventana.show()
        elif filtro == "Algoritmo Canny":
            self.lbl_canny_low.show()
            self.slider_canny_low.show()
            self.lbl_canny_high.show()
            self.slider_canny_high.show()

    def _procesar_filtro(self) -> None:
        """Aplica el filtro seleccionado a la imagen cargada y actualiza el visor."""
        if self._imagen_original is None:
            logger.warning("No hay imagen cargada para filtrar")
            return

        filtro = self.combo_f_tipo.currentText()
        # Mapeo de nombres de interfaz a nombres internos
        mapa_filtros = {
            "Ninguno": "none",
            "Sobel Horizontal": "sobel_h",
            "Sobel Vertical": "sobel_v",
            "Magnitud de Sobel": "sobel",
            "Laplaciano": "laplace",
            "Desenfoque Gaussiano": "gaussian",
            "Filtro de Mediana": "median",
            "Algoritmo Canny": "canny",
        }
        tipo_interno = mapa_filtros.get(filtro, "none")

        # Si la imagen original es 3D, trabajamos sobre la primera banda
        if self._imagen_original.ndim == 3:
            matriz = np.nan_to_num(self._imagen_original[0, :, :])
        else:
            matriz = np.nan_to_num(self._imagen_original)

        try:
            if tipo_interno == "none":
                resultado = matriz.copy()
            elif tipo_interno == "sobel_h":
                from scipy.ndimage import sobel
                resultado = np.abs(sobel(matriz, axis=1))
            elif tipo_interno == "sobel_v":
                from scipy.ndimage import sobel
                resultado = np.abs(sobel(matriz, axis=0))
            elif tipo_interno == "sobel":
                from scipy.ndimage import sobel
                sx = sobel(matriz, axis=1)
                sy = sobel(matriz, axis=0)
                resultado = np.sqrt(sx**2 + sy**2)
            elif tipo_interno == "laplace":
                from scipy.ndimage import gaussian_laplace
                sigma = self.slider_sigma.value() / 10.0
                resultado = np.abs(gaussian_laplace(matriz, sigma=sigma))
            elif tipo_interno == "gaussian":
                from scipy.ndimage import gaussian_filter
                sigma = self.slider_sigma.value() / 10.0
                resultado = gaussian_filter(matriz, sigma=sigma)
            elif tipo_interno == "median":
                from scipy.ndimage import median_filter
                size = self.slider_ventana.value()
                resultado = median_filter(matriz, size=size)
            elif tipo_interno == "canny":
                from skimage.feature import canny
                low = self.slider_canny_low.value() / 255.0
                high = self.slider_canny_high.value() / 255.0
                resultado = canny(
                    matriz,
                    sigma=1.0,
                    low_threshold=low,
                    high_threshold=high
                ).astype(np.float32)
            else:
                resultado = matriz.copy()

            self._imagen_filtrada = resultado
            self.visor_filtros.mostrar_imagen(resultado)
            logger.info(f"Filtro '{filtro}' aplicado correctamente")

        except ImportError as e:
            logger.error(f"Falta dependencia para el filtro '{filtro}': {e}")
            # Mostrar mensaje al usuario
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Dependencia faltante",
                f"El filtro '{filtro}' requiere scipy o scikit-image.\n{e}"
            )
        except Exception as e:
            logger.error(f"Error al aplicar filtro {filtro}: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_hoja_estilos(self) -> None:
        """Aplica la hoja de estilos definida en config."""
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                background-color: {COLADA_COLOR_SUPERFICIE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QScrollArea {{
                border: none;
            }}
        """)