# -*- coding: utf-8 -*-
"""
Diálogo Principal de COLADA – Postprocesado de LiDAR
=====================================================

Versión compacta para pantallas estándar. Orquesta las cinco pestañas modulares:
- Filtros (aplicación de filtros clásicos a derivados)
- Predicción (inferencia con VAE o Isolation Forest)
- Entrenamiento (entrenamiento del VAE)
- Rendimiento (configuración de hardware)
- Perfiles (gestión de perfiles de configuración)

Acepta lista de nombres de tesela para limitar las cargadas.
Las capas enviadas al mapa tienen nombres diferenciados según la pestaña.
"""

import os
import uuid
import tempfile
from typing import Optional, List, Dict, Any

import numpy as np
import rasterio

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsRasterBandStats,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QFileDialog,
    QMessageBox,
)
from qgis.PyQt.QtCore import Qt

from ...config import (
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_FONDO,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    COLADA_DIALOG_TITLE,
    COLADA_DIALOG_WIDTH,
    COLADA_DIALOG_HEIGHT,
    COLADA_DIALOG_MIN_WIDTH,
    COLADA_DIALOG_MIN_HEIGHT,
    COLADA_HEADER_TITLE,
    COLADA_HEADER_SUBTITLE,
    COLADA_BUTTON_CLOSE_TEXT,
    COLADA_BUTTON_CLOSE_OBJECT_NAME,
    COLADA_MSG_NO_DATA_TITLE,
    COLADA_MSG_NO_DATA_TEXT,
    COLADA_MSG_SAVE_ERROR_TITLE,
    COLADA_MSG_SAVE_ERROR_TEXT,
    COLADA_MSG_NO_RESULT_TITLE,
    COLADA_MSG_NO_RESULT_TEXT,
    COLADA_MAP_NORMALIZE_LOW_PERC,
    COLADA_MAP_NORMALIZE_HIGH_PERC,
    PREDICCION_COLORES_RAMPA,
    PREDICCION_ETIQUETAS_RAMPA,
)
from .tabs.filtrosTab import TabFiltros
from .tabs.prediccionTab import TabPrediccion
from .tabs.entrenamientoTab import TabEntrenamiento
from .tabs.rendimientoTab import TabRendimiento
from .tabs.perfilesTab import TabPerfiles
from ...utils.logging import get_logger

logger = get_logger('Colada.gui.dialogoPrincipal')


class DialogoPrincipal(QDialog):
    """
    Diálogo principal de Colada. Integra todas las funcionalidades de postprocesado.

    Attributes:
        tab_filtros: Pestaña de filtros.
        tab_prediccion: Pestaña de predicción.
        tab_entrenamiento: Pestaña de entrenamiento.
        tab_rendimiento: Pestaña de rendimiento.
        tab_perfiles: Pestaña de perfiles.
        tabs: QTabWidget contenedor.
    """

    def __init__(self, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(COLADA_DIALOG_TITLE)
        self.setModal(False)
        self.resize(COLADA_DIALOG_WIDTH, COLADA_DIALOG_HEIGHT)
        self.setMinimumSize(COLADA_DIALOG_MIN_WIDTH, COLADA_DIALOG_MIN_HEIGHT)

        # Crear las pestañas
        self.tab_filtros = TabFiltros()
        self.tab_prediccion = TabPrediccion()
        self.tab_entrenamiento = TabEntrenamiento()
        self.tab_rendimiento = TabRendimiento()
        self.tab_perfiles = TabPerfiles(on_perfil_cargado=self._aplicar_perfil)
        self.tab_perfiles.obtener_parametros_callback = self._obtener_parametros_actuales

        self._init_ui()
        self._conectar_pestanas()
        self._aplicar_hoja_estilos()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Configura el layout principal y las pestañas."""
        layout_raiz = QVBoxLayout(self)
        layout_raiz.setSpacing(6)
        layout_raiz.setContentsMargins(10, 10, 10, 10)

        # Cabecera
        cabecera_titulo = QLabel(COLADA_HEADER_TITLE)
        cabecera_titulo.setProperty("heading", "true")
        cabecera_sub = QLabel(COLADA_HEADER_SUBTITLE)
        cabecera_sub.setProperty("subheading", "true")
        layout_raiz.addWidget(cabecera_titulo)
        layout_raiz.addWidget(cabecera_sub)

        # Pestañas
        self.tabs = QTabWidget()
        self.tabs.addTab(self.tab_filtros, "Filtros")
        self.tabs.addTab(self.tab_prediccion, "Predicción")
        self.tabs.addTab(self.tab_entrenamiento, "Entrenamiento")
        self.tabs.addTab(self.tab_rendimiento, "Rendimiento")
        self.tabs.addTab(self.tab_perfiles, "Perfiles")
        layout_raiz.addWidget(self.tabs)

        # Botón cerrar
        barra_pie = QHBoxLayout()
        barra_pie.addStretch()
        btn_cerrar = QPushButton(COLADA_BUTTON_CLOSE_TEXT)
        btn_cerrar.setObjectName(COLADA_BUTTON_CLOSE_OBJECT_NAME)
        btn_cerrar.clicked.connect(self.close)
        barra_pie.addWidget(btn_cerrar)
        layout_raiz.addLayout(barra_pie)

    def _conectar_pestanas(self) -> None:
        """Conecta las señales entre pestañas y acciones comunes."""
        self.tab_filtros.btn_f_buscar_dir.clicked.connect(self._seleccionar_directorio_comun)
        self.tab_filtros.combo_derivados.currentIndexChanged.connect(self._sincronizar_imagen_a_prediccion)
        self.tab_filtros.btn_f_guardar.clicked.connect(self._guardar_imagen)
        self.tab_filtros.btn_f_mapa.clicked.connect(self._plasmar_en_mapa)
        self.tab_prediccion.btn_guardar.clicked.connect(self._guardar_imagen)
        self.tab_prediccion.btn_mapa.clicked.connect(self._plasmar_en_mapa)

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------

    def establecer_carpeta_tizona(self, ruta: str, nombres_teselas: Optional[List[str]] = None) -> None:
        """
        Establece la carpeta base de Tizona y carga las teselas en las pestañas.

        Args:
            ruta: Ruta a la carpeta de resultados de Tizona.
            nombres_teselas: Lista opcional de nombres de tesela a cargar.
        """
        if not ruta or not os.path.isdir(ruta):
            return
        self.tab_filtros.establecer_carpeta_tizona(ruta, nombres_teselas)
        if hasattr(self.tab_prediccion, "establecer_carpeta_tizona"):
            self.tab_prediccion.establecer_carpeta_tizona(ruta, nombres_teselas)

    # ------------------------------------------------------------------
    # Acciones comunes (guardar, enviar a mapa)
    # ------------------------------------------------------------------

    def _seleccionar_directorio_comun(self) -> None:
        """Abre un diálogo para seleccionar la carpeta base de Tizona."""
        directorio = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta Base")
        if directorio:
            self.establecer_carpeta_tizona(directorio)

    def _sincronizar_imagen_a_prediccion(self) -> None:
        """Sincroniza la imagen cargada en Filtros con la pestaña de Predicción."""
        if self.tab_filtros._imagen_original is not None:
            self.tab_prediccion.establecer_imagen_original(
                self.tab_filtros._imagen_original,
                self.tab_filtros._profile_original,
                self.tab_filtros._nombre_tesela_activa,
            )

    def _obtener_tab_activa(self):
        """Devuelve la pestaña actual (Filtros o Predicción) según el índice."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            return self.tab_filtros
        elif idx == 1:
            return self.tab_prediccion
        return None

    def _guardar_imagen(self) -> None:
        """Guarda el resultado procesado actual (filtro o predicción) como GeoTIFF."""
        tab = self._obtener_tab_activa()
        if tab is None:
            return

        matriz = tab.imagen_resultante
        perfil = tab.perfil_original
        if matriz is None:
            QMessageBox.warning(self, COLADA_MSG_NO_DATA_TITLE, COLADA_MSG_NO_DATA_TEXT)
            return

        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Ráster", "", "GeoTIFF (*.tif)")
        if not ruta:
            return

        try:
            perfil_out = perfil.copy()
            perfil_out.update(dtype=matriz.dtype, count=1)
            with rasterio.open(ruta, "w", **perfil_out) as dst:
                nodata = perfil_out.get("nodata", -9999.0)
                dst.write(np.where(np.isnan(matriz), nodata, matriz), 1)
        except Exception as e:
            QMessageBox.critical(self, COLADA_MSG_SAVE_ERROR_TITLE, COLADA_MSG_SAVE_ERROR_TEXT.format(e))

    def _plasmar_en_mapa(self) -> None:
        """Envía el resultado procesado actual al lienzo de QGIS como capa raster."""
        tab = self._obtener_tab_activa()
        if tab is None:
            return

        matriz = tab.imagen_resultante
        perfil = tab.perfil_original
        nombre_tesela = tab.nombre_tesela
        if matriz is None:
            QMessageBox.warning(self, COLADA_MSG_NO_RESULT_TITLE, COLADA_MSG_NO_RESULT_TEXT)
            return

        # Determinar el sufijo según la pestaña
        if tab is self.tab_filtros:
            sufijo_nombre = "filtro"
        elif tab is self.tab_prediccion:
            sufijo_nombre = "prediccion"
        else:
            sufijo_nombre = "resultado"

        nombre_base = f"COLADA_{nombre_tesela}_{sufijo_nombre}"

        # Eliminar capa anterior con el mismo nombre
        for capa in QgsProject.instance().mapLayers().values():
            if capa.name() == nombre_base:
                QgsProject.instance().removeMapLayer(capa.id())
                break

        # Normalizar la matriz para guardar como uint8
        matriz_segura = np.nan_to_num(matriz, nan=np.nanmin(matriz))
        vmin, vmax = np.percentile(
            matriz_segura, [COLADA_MAP_NORMALIZE_LOW_PERC, COLADA_MAP_NORMALIZE_HIGH_PERC]
        )
        if vmax > vmin:
            img_norm = np.clip(matriz_segura, vmin, vmax)
            img_norm = ((img_norm - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        else:
            img_norm = np.zeros_like(matriz_segura, dtype=np.uint8)

        sufijo_uuid = uuid.uuid4().hex[:8]
        ruta_temp = os.path.join(tempfile.gettempdir(), f"{nombre_base}_{sufijo_uuid}.tif")

        try:
            perfil_out = perfil.copy()
            perfil_out.pop("nodata", None)
            perfil_out.update(dtype=np.uint8, count=1)
            with rasterio.open(ruta_temp, "w", **perfil_out) as dst:
                dst.write(img_norm, 1)

            capa = QgsRasterLayer(ruta_temp, nombre_base)
            if capa.isValid():
                QgsProject.instance().addMapLayer(capa)
                if tab is self.tab_prediccion:
                    self._aplicar_estilo_mapa_anomalia(capa)
            else:
                raise RuntimeError("Capa raster no válida")
        except Exception as e:
            QMessageBox.critical(self, COLADA_MSG_SAVE_ERROR_TITLE, COLADA_MSG_SAVE_ERROR_TEXT.format(e))

    # ------------------------------------------------------------------
    # Estilo para mapa de anomalías
    # ------------------------------------------------------------------

    @staticmethod
    def _aplicar_estilo_mapa_anomalia(capa: QgsRasterLayer) -> None:
        """Aplica una rampa de color azul‑rojo al ráster de anomalías."""
        provider = capa.dataProvider()
        if not provider:
            return

        stats = provider.bandStatistics(1, QgsRasterBandStats.All, capa.extent(), 25000)
        min_val = stats.minimumValue
        max_val = stats.maximumValue
        if min_val == max_val:
            min_val = 0.0
            max_val = 1.0

        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Interpolated)

        rng = max_val - min_val
        items = []
        for i, (rgb, label) in enumerate(zip(PREDICCION_COLORES_RAMPA, PREDICCION_ETIQUETAS_RAMPA)):
            value = min_val + rng * i / (len(PREDICCION_COLORES_RAMPA) - 1.0)
            color = QColor(*rgb)
            items.append(QgsColorRampShader.ColorRampItem(value, color, label))

        shader.setColorRampItemList(items)
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader)
        renderer = QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
        renderer.setOpacity(0.8)
        capa.setRenderer(renderer)
        capa.triggerRepaint()

    # ------------------------------------------------------------------
    # Gestión de perfiles (placeholder por ahora)
    # ------------------------------------------------------------------

    def _obtener_parametros_actuales(self) -> Dict[str, Any]:
        """
        Recoge los parámetros actuales de todas las pestañas para guardarlos.
        Se excluye 'modelo_prediccion' para no almacenar el algoritmo en el perfil.
        """
        params: Dict[str, Any] = {}
        # Aquí se pueden añadir los parámetros de las pestañas (filtros, predicción, etc.)
        # Por ahora se devuelve vacío; se puede implementar según necesidad.
        return params

    def _aplicar_perfil(self, params: Dict[str, Any]) -> None:
        """
        Aplica un perfil cargado a todas las pestañas.
        No se toca el combo box del algoritmo de predicción.
        """
        # Aplicar parámetros a la pestaña de filtros
        if hasattr(self.tab_filtros, 'cargar_parametros'):
            self.tab_filtros.cargar_parametros(params)
        # Aplicar parámetros a la pestaña de predicción (excepto el algoritmo)
        if hasattr(self.tab_prediccion, 'cargar_parametros'):
            params_pred = params.copy()
            params_pred.pop('modelo_prediccion', None)
            self.tab_prediccion.cargar_parametros(params_pred)
        # Aplicar parámetros a la pestaña de entrenamiento
        if hasattr(self.tab_entrenamiento, 'cargar_parametros'):
            self.tab_entrenamiento.cargar_parametros(params)
        # Aplicar parámetros a la pestaña de rendimiento
        if hasattr(self.tab_rendimiento, 'cargar_parametros'):
            self.tab_rendimiento.cargar_parametros(params)

        logger.info(f"Perfil aplicado (excluyendo modelo_prediccion): {list(params.keys())}")

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_hoja_estilos(self) -> None:
        """Aplica la hoja de estilos definida en config (paleta coral de Colada)."""
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLADA_COLOR_FONDO}; }}
            QLabel[heading="true"] {{
                font-size: 22px; font-weight: 900; color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QLabel[subheading="true"] {{
                font-size: 13px; font-weight: bold; color: {COLADA_COLOR_PRIMARIO}; margin-bottom: 6px;
            }}
            QTabWidget::pane {{
                border: 1px solid {COLADA_COLOR_BORDE}; background: {COLADA_COLOR_FONDO};
                border-radius: 4px; top: -1px;
            }}
            QTabBar::tab {{
                background: {COLADA_COLOR_SUPERFICIE};
                border: 1px solid {COLADA_COLOR_BORDE};
                padding: 4px 14px;
                min-height: 24px;
                min-width: 80px;
                font-size: 10px;
                font-weight: bold;
                color: #444;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {COLADA_COLOR_FONDO}; border-bottom: 2px solid {COLADA_COLOR_FONDO};
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QPushButton#{COLADA_BUTTON_CLOSE_OBJECT_NAME} {{
                background-color: #888; border: 1px solid #666; color: white;
                padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 11px;
            }}
            QPushButton#{COLADA_BUTTON_CLOSE_OBJECT_NAME}:hover {{ background-color: #666; }}
        """)