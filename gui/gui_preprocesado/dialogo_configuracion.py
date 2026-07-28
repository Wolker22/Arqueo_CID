# -*- coding: utf-8 -*-
"""
Diálogo de configuración de Tizona – Estética teal minimalista (Arqueo-CID)
============================================================================

Centraliza todas las pestañas de configuración del preprocesado LiDAR:
- Datos y exportación
- Procesamiento (MDT, filtrado de suelo)
- Derivados (selección y parámetros)
- Rendimiento (descargas, bloques, GPU/PDAL)
- Perfiles (carga/guardado de configuraciones)

Los valores por defecto y las constantes se obtienen de config.py
para mantener la coherencia con el resto del plugin.
"""

import os
from typing import Dict, Any, Tuple

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QMessageBox, QPushButton
)
from qgis.PyQt.QtCore import Qt

from .tabs.datosTab import TabDatos
from .tabs.procesamientoTab import TabProcesamiento
from .tabs.derivadosTab import TabDerivados
from .tabs.rendimientoTab import TabRendimiento
from .tabs.perfilesTab import TabPerfiles
from ...utils.logging import get_logger

# Importar constantes desde la configuración central
from ...config import (
    COLOR_PRIMARIO,
    COLOR_PRIMARIO_OSC,
    COLOR_BORDE,
    COLOR_SUPERFICIE,
    COLOR_FONDO,
    # Valores por defecto para procesamiento
    RESOLUCION_MDT,
    Z_FACTOR_HILLSHADE,
    HILLSHADE_MULTIDIR,
    RADIO_OPENNESS,
    RADIO_LRM,
    RADIO_TPI_MULTIESCALA,
    ANGULOS_MULTIDIR,
    DERIVADOS_POR_DEFECTO,
    USAR_CLASIFICACION_EXISTENTE,
    GAUSSIAN_BLUR_SIGMA,
    PADDING_REFLECT_PX,
    SMRF_WINDOW,
    SMRF_SLOPE,
    SMRF_THRESHOLD,
    # Valores por defecto para descarga y exportación
    DESCARGAS_SIMULTANEAS,
    TIMEOUT_DESCARGA,
    MAX_PROCESOS_SIMULTANEOS,
    USAR_PROCESAMIENTO_BLOQUES,
    TAMANO_BLOQUE,
    MEMORIA_MAX_MB,
    USAR_PDAL,
    PDAL_DECIMATION_STEP,
    PDAL_OUTPUT_TYPE,
    MIN_MEMORIA_LIBRE_MB,
    MAX_HILOS_PROCESAMIENTO,
    GENERAR_IMAGENES_PNG,
    NORMALIZAR_IMAGENES,
    PNG_PERC_LOW,
    PNG_PERC_HIGH,
    EXPORTAR_STACK_MULTIBANDA,
    NORMALIZAR_STACK,
    INCLUIR_MASCARA_STACK,
    GENERAR_METADATOS_JSON,
    GENERAR_MANIFIESTO_IA,
    STACK_PERC_LOW,
    STACK_PERC_HIGH,
    # Nuevas constantes para la interfaz
    TIZONA_DIALOG_WIDTH,
    TIZONA_DIALOG_HEIGHT,
    MODOS_EJECUCION,
    MODO_EJECUCION_DEFAULT,
    COBERTURA_DEFAULT,
    TIPO_PRODUCTO_DEFAULT,
    LIMPIAR_DESCARGAS_DEFAULT,
    LIMPIAR_PROCESADOS_DEFAULT,
    ALGORITMO_SUELO_DEFAULT,
    USAR_GDAL_DEFAULT,
    USAR_GPU_DEFAULT,
    MENSAJE_RUTA_DESCARGA_VACIA,
    MENSAJE_RUTA_RESULTADOS_VACIA,
    MENSAJE_RESTABLECER_CONFIRMACION,
)

logger = get_logger('Tizona.gui.configuracion')


class DialogoConfiguracion(QDialog):
    """
    Diálogo principal de configuración de Tizona.
    Contiene las pestañas de datos, procesamiento, derivados, rendimiento y perfiles.
    """

    # Claves de los parámetros de rendimiento que pertenecen al procesamiento (no a descarga)
    CLAVES_RENDIMIENTO_PROCESAMIENTO = {
        "usar_bloques",
        "tamano_bloque",
        "memoria_max_mb",
        "usar_gdal",
        "usar_gpu",
        "usar_pdal",
        "pdal_decimation_step",
        "pdal_output_type",
        "min_memoria_libre_mb",
        "max_hilos_procesamiento",
    }

    # Claves de los parámetros de rendimiento relacionados con la descarga
    CLAVES_RENDIMIENTO_DESCARGA = {
        "descargas_simultaneas",
        "timeout_descarga",
        "procesamiento_paralelo",
        "proc_paralelo",
    }

    def __init__(self, parent: QDialog = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tizona – Procesamiento LiDAR")
        self.resize(TIZONA_DIALOG_WIDTH, TIZONA_DIALOG_HEIGHT)
        self.setMinimumSize(TIZONA_DIALOG_WIDTH, TIZONA_DIALOG_HEIGHT)
        self._init_ui()
        self._aplicar_estilo_global()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Construye la interfaz: cabecera, pestañas y botones."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Cabecera con título y subtítulo
        header = QLabel(
            f"<h1 style='color: {COLOR_PRIMARIO}; font-size: 24px; margin: 0;'>TIZONA</h1>"
            f"<p style='color: {COLOR_PRIMARIO_OSC}; font-size: 14px;'>"
            "Procesamiento LiDAR para Arqueología</p>"
        )
        header.setWordWrap(True)
        main_layout.addWidget(header)

        # Panel de pestañas
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)

        self.tab_datos = TabDatos()
        self.tabs.addTab(self.tab_datos, "Datos y Exportación")

        self.tab_procesamiento = TabProcesamiento()
        self.tabs.addTab(self.tab_procesamiento, "Procesamiento")

        self.tab_derivados = TabDerivados()
        self.tabs.addTab(self.tab_derivados, "Derivados")

        self.tab_rendimiento = TabRendimiento()
        self.tabs.addTab(self.tab_rendimiento, "Rendimiento")

        self.tab_perfiles = TabPerfiles(on_perfil_cargado=self.aplicar_perfil)
        self.tab_perfiles.obtener_parametros_callback = self.obtener_parametros_completos
        self.tabs.addTab(self.tab_perfiles, "Perfiles")

        main_layout.addWidget(self.tabs, 1)

        # Botones de acción
        barra_layout = QHBoxLayout()
        barra_layout.addStretch()

        self.btn_reset = QPushButton("Restablecer")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_aceptar = QPushButton("Aceptar")

        barra_layout.addWidget(self.btn_reset)
        barra_layout.addWidget(self.btn_cancelar)
        barra_layout.addWidget(self.btn_aceptar)
        main_layout.addLayout(barra_layout)

        # Conectar señales
        self.btn_aceptar.clicked.connect(self._validate_and_accept)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self.restablecer_valores_por_defecto)

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_estilo_global(self) -> None:
        """Hoja de estilos unificada (teal minimalista)."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_FONDO};
            }}
            QTabWidget::pane {{
                border: 1px solid {COLOR_BORDE};
                background: {COLOR_FONDO};
                border-radius: 4px;
                top: -1px;
            }}
            QTabBar::tab {{
                background: {COLOR_SUPERFICIE};
                border: 1px solid {COLOR_BORDE};
                padding: 6px 20px;
                min-height: 28px;
                min-width: 120px;
                font-size: 11px;
                font-weight: bold;
                color: {COLOR_PRIMARIO_OSC};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {COLOR_FONDO};
                border-bottom: 2px solid {COLOR_FONDO};
                color: {COLOR_PRIMARIO};
            }}
            QTabBar::tab:hover:!selected {{
                background: {COLOR_BORDE};
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

            QLabel {{
                font-size: 12px;
                color: #333;
            }}

            QComboBox QAbstractItemView {{
                color: black;
                background: white;
                selection-background-color: #d0ece7;
                selection-color: black;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #d0ece7;
                color: black;
            }}
        """)

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------

    def _validate_and_accept(self) -> None:
        """Valida que las rutas de descarga y resultados no estén vacías."""
        datos = self.tab_datos.obtener_parametros()
        if not datos.get("ruta_descarga"):
            QMessageBox.warning(self, "Ruta de descarga vacía", MENSAJE_RUTA_DESCARGA_VACIA)
            return
        if not datos.get("ruta_procesados"):
            QMessageBox.warning(self, "Ruta de resultados vacía", MENSAJE_RUTA_RESULTADOS_VACIA)
            return
        self.accept()

    # ------------------------------------------------------------------
    # Obtención de parámetros
    # ------------------------------------------------------------------

    def obtener_parametros_completos(self) -> Dict[str, Any]:
        """
        Reúne todos los parámetros de todas las pestañas.
        Devuelve un diccionario con dos claves: 'procesamiento' y 'descarga'.
        """
        # Parámetros de procesamiento (pestañas Procesamiento + Derivados)
        params_proc = {}
        params_proc.update(self.tab_procesamiento.obtener_parametros())
        params_proc.update(self.tab_derivados.obtener_parametros())

        # Parámetros de exportación desde la pestaña Datos
        datos = self.tab_datos.obtener_parametros()
        params_proc.update(
            {
                "generar_imagenes_png": datos["generar_imagenes_png"],
                "normalizar_imagenes": datos["normalizar_imagenes"],
                "png_perc_low": datos["png_perc_low"],
                "png_perc_high": datos["png_perc_high"],
                "exportar_stack": datos["exportar_stack"],
                "normalizar_stack": datos["normalizar_stack"],
                "stack_perc_low": datos["stack_perc_low"],
                "stack_perc_high": datos["stack_perc_high"],
                "incluir_mascara_stack": datos["incluir_mascara_stack"],
                "generar_metadatos_json": datos["generar_metadatos_json"],
                "generar_manifiesto_ia": datos["generar_manifiesto_ia"],
            }
        )

        # Parámetros de rendimiento (filtrar los que van a procesamiento vs descarga)
        rend = self.tab_rendimiento.obtener_parametros()
        for clave in self.CLAVES_RENDIMIENTO_PROCESAMIENTO:
            if clave in rend:
                params_proc[clave] = rend[clave]

        # Parámetros específicos de descarga
        config_descarga = {
            "modo_ejecucion": datos["modo_ejecucion"],
            "ruta_descarga": datos["ruta_descarga"],
            "ruta_procesados": datos["ruta_procesados"],
            "limpiar_descargas": datos["limpiar_descargas"],
            "limpiar_procesados": datos["limpiar_procesados"],
            "tipo_producto": datos.get("tipo_producto", TIPO_PRODUCTO_DEFAULT),
            "cobertura": datos.get("cobertura", COBERTURA_DEFAULT),
            "resolucion": params_proc.get("resolucion", RESOLUCION_MDT),
        }
        for clave in self.CLAVES_RENDIMIENTO_DESCARGA:
            if clave in rend:
                config_descarga[clave] = rend[clave]

        return {"procesamiento": params_proc, "descarga": config_descarga}

    def obtener_parametros(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Método de compatibilidad: devuelve (parametros_procesamiento, parametros_descarga)."""
        completo = self.obtener_parametros_completos()
        return completo["procesamiento"], completo["descarga"]

    # ------------------------------------------------------------------
    # Aplicación de perfil
    # ------------------------------------------------------------------

    def aplicar_perfil(self, params: Dict[str, Any]) -> None:
        """
        Aplica un perfil (cargado desde JSON) a las pestañas.
        El perfil puede contener las claves 'procesamiento' y/o 'descarga'.
        """
        proc = params.get("procesamiento", params)
        desc = params.get("descarga", {})
        # La pestaña Datos recibe tanto parámetros de exportación como de descarga
        self.tab_datos.aplicar_parametros({**proc, **desc})
        self.tab_procesamiento.aplicar_parametros(proc)
        self.tab_derivados.aplicar_parametros(proc)
        self.tab_rendimiento.aplicar_parametros({**proc, **desc})

    # ------------------------------------------------------------------
    # Restablecimiento de valores por defecto
    # ------------------------------------------------------------------

    def restablecer_valores_por_defecto(self) -> None:
        """Restablece todas las pestañas a los valores por defecto definidos en config.py."""
        if (
            QMessageBox.question(
                self, "Restablecer", MENSAJE_RESTABLECER_CONFIRMACION
            )
            != QMessageBox.Yes
        ):
            return

        # Valores por defecto para la pestaña Datos
        self.tab_datos.aplicar_parametros(
            {
                "modo_ejecucion": MODO_EJECUCION_DEFAULT,
                "limpiar_descargas": LIMPIAR_DESCARGAS_DEFAULT,
                "limpiar_procesados": LIMPIAR_PROCESADOS_DEFAULT,
                "cobertura": COBERTURA_DEFAULT,
                "tipo_producto": TIPO_PRODUCTO_DEFAULT,
                "generar_imagenes_png": GENERAR_IMAGENES_PNG,
                "normalizar_imagenes": NORMALIZAR_IMAGENES,
                "png_perc_low": PNG_PERC_LOW,
                "png_perc_high": PNG_PERC_HIGH,
                "exportar_stack": EXPORTAR_STACK_MULTIBANDA,
                "normalizar_stack": NORMALIZAR_STACK,
                "stack_perc_low": STACK_PERC_LOW,
                "stack_perc_high": STACK_PERC_HIGH,
                "incluir_mascara_stack": INCLUIR_MASCARA_STACK,
                "generar_metadatos_json": GENERAR_METADATOS_JSON,
                "generar_manifiesto_ia": GENERAR_MANIFIESTO_IA,
            }
        )

        # Valores por defecto para la pestaña Procesamiento
        self.tab_procesamiento.aplicar_parametros(
            {
                "resolucion": RESOLUCION_MDT,
                "z_factor": Z_FACTOR_HILLSHADE,
                "multidirectional": HILLSHADE_MULTIDIR,
                "algoritmo_suelo": ALGORITMO_SUELO_DEFAULT,
                "usar_clasificacion_existente": USAR_CLASIFICACION_EXISTENTE,
                "smrf_window": SMRF_WINDOW,
                "smrf_slope": SMRF_SLOPE,
                "smrf_threshold": SMRF_THRESHOLD,
                "gaussian_blur_sigma": GAUSSIAN_BLUR_SIGMA,
                "padding_reflect_px": PADDING_REFLECT_PX,
                "max_hilos_procesamiento": MAX_HILOS_PROCESAMIENTO,
            }
        )

        # Valores por defecto para la pestaña Derivados
        self.tab_derivados.aplicar_parametros(
            {
                "radio_openness": RADIO_OPENNESS,
                "radio_lrm": RADIO_LRM,
                "radio_tpi_multiescala": list(RADIO_TPI_MULTIESCALA),
                "angulos_multidir": list(ANGULOS_MULTIDIR),
                "derivados": list(DERIVADOS_POR_DEFECTO),
            }
        )

        # Valores por defecto para la pestaña Rendimiento
        self.tab_rendimiento.aplicar_parametros(
            {
                "descargas_simultaneas": DESCARGAS_SIMULTANEAS,
                "timeout_descarga": TIMEOUT_DESCARGA,
                "procesamiento_paralelo": True,
                "proc_paralelo": MAX_PROCESOS_SIMULTANEOS,
                "usar_bloques": USAR_PROCESAMIENTO_BLOQUES,
                "tamano_bloque": TAMANO_BLOQUE,
                "memoria_max_mb": MEMORIA_MAX_MB,
                "usar_gdal": USAR_GDAL_DEFAULT,
                "usar_gpu": USAR_GPU_DEFAULT,
                "usar_pdal": USAR_PDAL,
                "pdal_decimation_step": PDAL_DECIMATION_STEP,
                "pdal_output_type": PDAL_OUTPUT_TYPE,
                "min_memoria_libre_mb": MIN_MEMORIA_LIBRE_MB,
            }
        )