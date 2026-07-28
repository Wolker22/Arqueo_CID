# -*- coding: utf-8 -*-
"""
Pestaña de Perfiles de COLADA – Versión Definitiva
---------------------------------------------------

Gestiona la persistencia de configuraciones (I/O de archivos JSON).
Carga, guarda, importa y elimina perfiles de usuario y de sistema.

Características:
- Carga a prueba de fallos: inyecta valores por defecto si el JSON es antiguo.
- Diseño unificado y protección contra colisiones de espacio de nombres.
- Modificación dinámica: excluye la clave 'modelo_prediccion' para no forzar
  el combobox general de algoritmos.
"""

import os
from typing import Optional, Dict, Any, Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
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
    PERFILES_TITULO_PRINCIPAL,
    PERFILES_DESCRIPCION,
    PERFILES_GROUP_TITLE,
    PERFILES_TOOLTIP_LISTA,
    PERFILES_BTN_CARGAR,
    PERFILES_BTN_GUARDAR,
    PERFILES_BTN_ELIMINAR,
    PERFILES_BTN_IMPORTAR,
    PERFILES_MSG_SELECCION_REQUERIDA,
    PERFILES_MSG_SELECCIONE_PERFIL,
    PERFILES_MSG_EXITO,
    PERFILES_MSG_CONFIG_CARGADA,
    PERFILES_MSG_ERROR_LECTURA,
    PERFILES_MSG_PERFIL_INVALIDO,
    PERFILES_MSG_IMPORTACION_EXITO,
    PERFILES_MSG_PERFIL_APLICADO,
    PERFILES_MSG_ERROR_IMPORTACION,
    PERFILES_MSG_FALLO_JSON,
    PERFILES_MSG_ATENCION,
    PERFILES_MSG_SIN_CALLBACK,
    PERFILES_MSG_GUARDADO,
    PERFILES_MSG_PERFIL_REGISTRADO,
    PERFILES_MSG_ERROR_GUARDADO,
    PERFILES_MSG_NO_GUARDADO,
    PERFILES_MSG_SELECCION_ELIMINAR,
    PERFILES_MSG_ACCION_DENEGADA,
    PERFILES_MSG_NO_ELIMINAR_SISTEMA,
    PERFILES_MSG_BORRAR,
    PERFILES_MSG_CONFIRMAR_BORRAR,
    PERFILES_MSG_ERROR_ELIMINAR,
    PERFILES_MSG_ELIMINAR_FALLO,
    PERFILES_MSG_NO_ELIMINAR,
    PERFILES_BOTON_PRINCIPAL_STYLE,
    PERFILES_BOTON_SECUNDARIO_STYLE,
    PERFILES_BOTON_NORMAL_STYLE,
)

from ....utils.perfil import (
    listar_perfiles,
    cargar_perfil,
    guardar_perfil,
    seleccionar_guardar_perfil,
    PERFILES_PLUGIN,
    eliminar_perfil,
)
from ....utils.logging import get_logger

logger = get_logger('Colada.gui.perfiles')


class TabPerfiles(QWidget):
    """
    Pestaña de gestión de perfiles de configuración.

    Permite:
    - Aplicar un perfil de sistema o de usuario seleccionado.
    - Guardar la configuración actual como nuevo perfil.
    - Importar un perfil desde un archivo JSON externo.
    - Eliminar perfiles de usuario.

    Attributes:
        on_perfil_cargado: Callback que se ejecuta al cargar un perfil.
        obtener_parametros_callback: Callback que devuelve la configuración actual.
        lista_perfiles: ListWidget con los perfiles disponibles.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_perfil_cargado: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Args:
            parent: Widget padre.
            on_perfil_cargado: Función llamada con los parámetros del perfil cargado.
        """
        super().__init__(parent)
        self.on_perfil_cargado: Optional[Callable[[Dict[str, Any]], None]] = on_perfil_cargado
        self.obtener_parametros_callback: Optional[Callable[[], Dict[str, Any]]] = None
        self._init_ui()
        self._aplicar_hoja_estilos()
        self.cargar_lista()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Título y descripción
        lbl_info = QLabel(PERFILES_TITULO_PRINCIPAL)
        lbl_info.setProperty("heading", "true")
        layout.addWidget(lbl_info)

        lbl_desc = QLabel(PERFILES_DESCRIPCION)
        lbl_desc.setWordWrap(True)
        lbl_desc.setToolTip(PERFILES_TOOLTIP_LISTA)
        layout.addWidget(lbl_desc)

        # Grupo de lista de perfiles
        grupo = QGroupBox(PERFILES_GROUP_TITLE)
        grid = QGridLayout()
        grid.setSpacing(6)

        self.lista_perfiles = QListWidget()
        self.lista_perfiles.setMaximumHeight(200)
        self.lista_perfiles.setMinimumHeight(120)
        self.lista_perfiles.setSelectionMode(QListWidget.SingleSelection)
        self.lista_perfiles.setToolTip(PERFILES_TOOLTIP_LISTA)
        grid.addWidget(self.lista_perfiles, 0, 0, 1, 3)

        # Botones
        self.btn_cargar = QPushButton(PERFILES_BTN_CARGAR)
        self.btn_guardar = QPushButton(PERFILES_BTN_GUARDAR)
        self.btn_eliminar = QPushButton(PERFILES_BTN_ELIMINAR)
        self.btn_importar = QPushButton(PERFILES_BTN_IMPORTAR)

        for btn in [self.btn_cargar, self.btn_guardar, self.btn_eliminar, self.btn_importar]:
            self._forzar_estilo_boton(btn, "secundario")

        self.btn_cargar.clicked.connect(self._cargar_seleccionado)
        self.btn_guardar.clicked.connect(self._guardar_actual)
        self.btn_eliminar.clicked.connect(self._eliminar)
        self.btn_importar.clicked.connect(self._importar_desde_archivo)

        grid.addWidget(self.btn_cargar, 1, 0)
        grid.addWidget(self.btn_guardar, 1, 1)
        grid.addWidget(self.btn_eliminar, 1, 2)
        grid.addWidget(self.btn_importar, 2, 0, 1, 3)

        grupo.setLayout(grid)
        layout.addWidget(grupo)
        layout.addStretch()

        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    def _forzar_estilo_boton(self, boton: QPushButton, tipo: str = "normal") -> None:
        """Aplica el estilo CSS correspondiente al botón."""
        if tipo == "principal":
            css = PERFILES_BOTON_PRINCIPAL_STYLE
        elif tipo == "secundario":
            css = PERFILES_BOTON_SECUNDARIO_STYLE
        else:
            css = PERFILES_BOTON_NORMAL_STYLE
        boton.setStyleSheet(css)

    def _mensaje_estilizado(
        self,
        icono: QMessageBox.Icon,
        titulo: str,
        texto: str,
        botones: QMessageBox.StandardButtons = QMessageBox.Ok,
        boton_por_defecto: Optional[QMessageBox.StandardButton] = None,
    ) -> QMessageBox:
        """Crea un QMessageBox con estilos personalizados."""
        msg = QMessageBox(icono, titulo, texto, botones, self)
        if boton_por_defecto:
            msg.setDefaultButton(boton_por_defecto)
        msg.setStyleSheet(f"""
            QMessageBox {{ background-color: {COLADA_COLOR_FONDO}; }}
            QLabel {{ font-size: 12px; color: #333; }}
        """)
        estilo_boton = f"""
            QPushButton {{
                background-color: {COLADA_COLOR_PRIMARIO_OSC}; color: white;
                border: 1px solid {COLADA_COLOR_PRIMARIO_OSC}; padding: 6px 16px;
                border-radius: 4px; font-weight: bold; font-size: 12px; min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {COLADA_COLOR_PRIMARIO}; }}
            QPushButton:pressed {{ background-color: {COLADA_COLOR_PRIMARIO}; }}
        """
        for button in msg.buttons():
            button.setStyleSheet(estilo_boton)
        return msg

    # ------------------------------------------------------------------
    # Carga de lista de perfiles
    # ------------------------------------------------------------------

    def cargar_lista(self) -> None:
        """Carga la lista de perfiles disponibles (sistema y usuario)."""
        self.lista_perfiles.clear()
        try:
            for nombre, ruta in listar_perfiles():
                item = QListWidgetItem(f"📄 {nombre}")
                item.setData(Qt.UserRole, ruta)
                if ruta is None:
                    # Perfil de sistema (solo lectura)
                    item.setForeground(Qt.darkBlue)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip("Perfil Base del Sistema (Sólo lectura)")
                else:
                    item.setToolTip(f"Perfil de usuario: {ruta}")
                self.lista_perfiles.addItem(item)
        except Exception as e:
            logger.error(f"Error listando perfiles: {e}")

    # ------------------------------------------------------------------
    # Sanitización de parámetros cargados
    # ------------------------------------------------------------------

    def _sanitizar_perfil(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Limpia el diccionario de parámetros cargado del JSON.
        Elimina claves que no queremos forzar en la UI y añade claves
        faltantes si el JSON es de una versión anterior.

        Args:
            params: Diccionario de parámetros cargado.

        Returns:
            Diccionario sanitizado.
        """
        # No forzar el algoritmo de predicción
        if 'modelo_prediccion' in params:
            logger.info("Eliminando 'modelo_prediccion' del perfil para respetar la selección manual.")
            del params['modelo_prediccion']

        # Retrocompatibilidad: si falta loss_function, inyectar valor por defecto
        if 'loss_function' not in params:
            params['loss_function'] = "ssim"

        return params

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _cargar_seleccionado(self) -> None:
        """Carga el perfil seleccionado y lo aplica mediante el callback."""
        item = self.lista_perfiles.currentItem()
        if not item:
            self._mensaje_estilizado(
                QMessageBox.Information,
                PERFILES_MSG_SELECCION_REQUERIDA,
                PERFILES_MSG_SELECCIONE_PERFIL
            ).exec_()
            return

        nombre = item.text().replace("📄 ", "")
        ruta = item.data(Qt.UserRole)

        try:
            raw_params = PERFILES_PLUGIN[nombre] if ruta is None else cargar_perfil(ruta)
            params = self._sanitizar_perfil(raw_params)

            if self.on_perfil_cargado:
                self.on_perfil_cargado(params)
                self._mensaje_estilizado(
                    QMessageBox.Information,
                    PERFILES_MSG_EXITO,
                    PERFILES_MSG_CONFIG_CARGADA.format(nombre)
                ).exec_()
        except Exception as e:
            logger.error(f"Error al cargar perfil {nombre}: {e}", exc_info=True)
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_LECTURA,
                PERFILES_MSG_PERFIL_INVALIDO.format(e)
            ).exec_()

    def _importar_desde_archivo(self) -> None:
        """Importa un perfil desde un archivo JSON externo y lo aplica."""
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar Perfil", "", "JSON (*.json)")
        if not ruta:
            return

        try:
            raw_params = cargar_perfil(ruta)
            params = self._sanitizar_perfil(raw_params)
            nombre = os.path.splitext(os.path.basename(ruta))[0]

            if self.on_perfil_cargado:
                self.on_perfil_cargado(params)
                self._mensaje_estilizado(
                    QMessageBox.Information,
                    PERFILES_MSG_IMPORTACION_EXITO,
                    PERFILES_MSG_PERFIL_APLICADO.format(nombre)
                ).exec_()
        except Exception as e:
            logger.error(f"Error importando perfil: {e}")
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_IMPORTACION,
                PERFILES_MSG_FALLO_JSON.format(e)
            ).exec_()

    def _guardar_actual(self) -> None:
        """Guarda la configuración actual como un nuevo perfil de usuario."""
        if not self.obtener_parametros_callback:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ATENCION,
                PERFILES_MSG_SIN_CALLBACK
            ).exec_()
            return

        ruta = seleccionar_guardar_perfil()
        if not ruta:
            return

        nombre = os.path.splitext(os.path.basename(ruta))[0]
        try:
            params = self.obtener_parametros_callback()
            # Asegurar que no guardamos el algoritmo de predicción
            if 'modelo_prediccion' in params:
                del params['modelo_prediccion']

            guardar_perfil(nombre, params)
            self.cargar_lista()
            self._mensaje_estilizado(
                QMessageBox.Information,
                PERFILES_MSG_GUARDADO,
                PERFILES_MSG_PERFIL_REGISTRADO.format(nombre)
            ).exec_()
        except Exception as e:
            logger.error(f"Error guardando perfil: {e}")
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_GUARDADO,
                PERFILES_MSG_NO_GUARDADO.format(e)
            ).exec_()

    def _eliminar(self) -> None:
        """Elimina el perfil de usuario seleccionado (solo si no es de sistema)."""
        item = self.lista_perfiles.currentItem()
        if not item:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ATENCION,
                PERFILES_MSG_SELECCION_ELIMINAR
            ).exec_()
            return

        ruta = item.data(Qt.UserRole)
        nombre = item.text().replace("📄 ", "")

        # Perfil de sistema (ruta None) no se puede eliminar
        if ruta is None:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ACCION_DENEGADA,
                PERFILES_MSG_NO_ELIMINAR_SISTEMA
            ).exec_()
            return

        confirm = self._mensaje_estilizado(
            QMessageBox.Question,
            PERFILES_MSG_BORRAR,
            PERFILES_MSG_CONFIRMAR_BORRAR.format(nombre),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm.exec_() == QMessageBox.Yes:
            try:
                if eliminar_perfil(nombre):
                    self.cargar_lista()
                    logger.info(f"Perfil eliminado: {nombre}")
                else:
                    self._mensaje_estilizado(
                        QMessageBox.Warning,
                        PERFILES_MSG_ERROR_ELIMINAR,
                        PERFILES_MSG_ELIMINAR_FALLO
                    ).exec_()
            except Exception as e:
                logger.error(f"Error eliminando perfil: {e}")
                self._mensaje_estilizado(
                    QMessageBox.Critical,
                    PERFILES_MSG_ERROR_ELIMINAR,
                    PERFILES_MSG_NO_ELIMINAR.format(e)
                ).exec_()

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
            QListWidget {{
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 4px;
                padding: 4px;
                background-color: white;
                font-size: 13px;
                selection-background-color: {COLADA_COLOR_PRIMARIO};
                selection-color: white;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid #f0f0f0;
            }}
            QListWidget::item:selected {{
                font-weight: bold;
                border-radius: 2px;
            }}
            QLabel {{
                font-size: 12px;
                color: #333;
            }}
            QLabel[heading="true"] {{
                font-size: 15px;
                font-weight: bold;
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QScrollArea {{
                border: none;
            }}
        """)