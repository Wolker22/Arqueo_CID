# -*- coding: utf-8 -*-
"""
Pestaña de Perfiles: guardar, cargar, importar y eliminar configuraciones.
(Adaptada a los estándares de Arqueo-CID, paleta teal de TIZONA, con scroll interno)
"""

import os
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QListWidget, QListWidgetItem, QPushButton,
    QMessageBox, QFileDialog, QScrollArea, QFrame
)
from qgis.PyQt.QtCore import Qt

# Importaciones absolutas
from ....config import (
    COLOR_PRIMARIO, COLOR_PRIMARIO_OSC, COLOR_FONDO, COLOR_SUPERFICIE, COLOR_BORDE,
    PERFILES_TITULO_PRINCIPAL,
    PERFILES_DESCRIPCION,
    PERFILES_GROUP_TITLE,
    PERFILES_BTN_CARGAR,
    PERFILES_BTN_GUARDAR,
    PERFILES_BTN_ELIMINAR,
    PERFILES_BTN_IMPORTAR,
    PERFILES_TOOLTIP_LISTA,
    PERFILES_TOOLTIP_CARGAR,
    PERFILES_TOOLTIP_GUARDAR,
    PERFILES_TOOLTIP_ELIMINAR,
    PERFILES_TOOLTIP_IMPORTAR,
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
    PERFILES_MSG_NO_ELIMINAR,
    PERFILES_BOTON_PRINCIPAL_STYLE,
    PERFILES_BOTON_SECUNDARIO_STYLE,
    PERFILES_BOTON_NORMAL_STYLE,
)
from arqueo_cid.utils.perfil import (
    listar_perfiles,
    cargar_perfil,
    guardar_perfil,
    seleccionar_guardar_perfil,
    PERFILES_PLUGIN,
)
from arqueo_cid.utils.logging import get_logger

logger = get_logger("gui.tabs.perfiles")


class TabPerfiles(QWidget):
    def __init__(self, parent=None, on_perfil_cargado=None):
        super().__init__(parent)
        self.on_perfil_cargado = on_perfil_cargado
        self.obtener_parametros_callback = None
        self._init_ui()
        self._aplicar_hoja_estilos()
        self.cargar_lista()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_info = QLabel(PERFILES_TITULO_PRINCIPAL)
        lbl_info.setProperty("heading", "true")
        layout.addWidget(lbl_info)

        lbl_desc = QLabel(PERFILES_DESCRIPCION)
        lbl_desc.setWordWrap(True)
        lbl_desc.setToolTip(PERFILES_TOOLTIP_LISTA)
        layout.addWidget(lbl_desc)

        grupo = QGroupBox(PERFILES_GROUP_TITLE)
        grid = QGridLayout()
        grid.setSpacing(10)

        self.lista_perfiles = QListWidget()
        self.lista_perfiles.setMaximumHeight(250)
        self.lista_perfiles.setMinimumHeight(150)
        self.lista_perfiles.setSelectionMode(QListWidget.SingleSelection)
        self.lista_perfiles.setToolTip(PERFILES_TOOLTIP_LISTA)
        grid.addWidget(self.lista_perfiles, 0, 0, 1, 3)

        self.btn_cargar = QPushButton(PERFILES_BTN_CARGAR)
        self.btn_guardar = QPushButton(PERFILES_BTN_GUARDAR)
        self.btn_eliminar = QPushButton(PERFILES_BTN_ELIMINAR)
        self.btn_importar = QPushButton(PERFILES_BTN_IMPORTAR)

        for btn in [self.btn_cargar, self.btn_guardar, self.btn_eliminar, self.btn_importar]:
            self._forzar_estilo_boton(btn, "secundario")

        self.btn_cargar.clicked.connect(self.cargar_perfil_seleccionado)
        self.btn_cargar.setToolTip(PERFILES_TOOLTIP_CARGAR)
        self.btn_guardar.clicked.connect(self.guardar_perfil_actual)
        self.btn_guardar.setToolTip(PERFILES_TOOLTIP_GUARDAR)
        self.btn_eliminar.clicked.connect(self.eliminar_perfil)
        self.btn_eliminar.setToolTip(PERFILES_TOOLTIP_ELIMINAR)
        self.btn_importar.clicked.connect(self.cargar_desde_archivo)
        self.btn_importar.setToolTip(PERFILES_TOOLTIP_IMPORTAR)

        grid.addWidget(self.btn_cargar, 1, 0)
        grid.addWidget(self.btn_guardar, 1, 1)
        grid.addWidget(self.btn_eliminar, 1, 2)
        grid.addWidget(self.btn_importar, 2, 0, 1, 3)

        grupo.setLayout(grid)
        layout.addWidget(grupo)
        layout.addStretch()

        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    def _forzar_estilo_boton(self, boton, tipo="normal"):
        if tipo == "principal":
            css = PERFILES_BOTON_PRINCIPAL_STYLE
        elif tipo == "secundario":
            css = PERFILES_BOTON_SECUNDARIO_STYLE
        else:
            css = PERFILES_BOTON_NORMAL_STYLE
        boton.setStyleSheet(css)

    def _mensaje_estilizado(self, icono, titulo, texto, botones=QMessageBox.Ok, boton_por_defecto=None):
        msg = QMessageBox(icono, titulo, texto, botones, self)
        if boton_por_defecto:
            msg.setDefaultButton(boton_por_defecto)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {COLOR_FONDO};
            }}
            QLabel {{
                font-size: 12px;
                color: #333;
            }}
        """)
        estilo_boton = f"""
            QPushButton {{
                background-color: {COLOR_PRIMARIO_OSC};
                color: white;
                border: 1px solid {COLOR_PRIMARIO_OSC};
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {COLOR_PRIMARIO}; }}
            QPushButton:pressed {{ background-color: {COLOR_PRIMARIO}; }}
        """
        for button in msg.buttons():
            button.setStyleSheet(estilo_boton)
        return msg

    def cargar_lista(self):
        self.lista_perfiles.clear()
        for nombre, ruta in listar_perfiles():
            item = QListWidgetItem(nombre)
            item.setData(Qt.UserRole, ruta)
            if ruta is None:
                item.setForeground(Qt.darkBlue)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip("Perfil del Sistema (Sólo lectura)")
            else:
                item.setToolTip(f"Perfil guardado localmente en: {ruta}")
            self.lista_perfiles.addItem(item)

    def cargar_perfil_seleccionado(self):
        item = self.lista_perfiles.currentItem()
        if not item:
            self._mensaje_estilizado(
                QMessageBox.Information,
                PERFILES_MSG_SELECCION_REQUERIDA,
                PERFILES_MSG_SELECCIONE_PERFIL,
            ).exec_()
            return
        nombre = item.text()
        ruta = item.data(Qt.UserRole)
        try:
            params = PERFILES_PLUGIN[nombre] if ruta is None else cargar_perfil(ruta)
            if self.on_perfil_cargado:
                self.on_perfil_cargado(params)
                self._mensaje_estilizado(
                    QMessageBox.Information,
                    PERFILES_MSG_EXITO,
                    PERFILES_MSG_CONFIG_CARGADA.format(nombre),
                ).exec_()
            else:
                logger.error("Falta el callback 'on_perfil_cargado'")
        except Exception as e:
            logger.error(f"Error al cargar el perfil '{nombre}': {e}")
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_LECTURA,
                PERFILES_MSG_PERFIL_INVALIDO.format(e),
            ).exec_()

    def cargar_desde_archivo(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar Perfil", "", "JSON (*.json)")
        if not ruta:
            return
        try:
            params = cargar_perfil(ruta)
            nombre = os.path.splitext(os.path.basename(ruta))[0]
            if self.on_perfil_cargado:
                self.on_perfil_cargado(params)
                self._mensaje_estilizado(
                    QMessageBox.Information,
                    PERFILES_MSG_IMPORTACION_EXITO,
                    PERFILES_MSG_PERFIL_APLICADO.format(nombre),
                ).exec_()
        except Exception as e:
            logger.error(f"Error importando perfil: {e}")
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_IMPORTACION,
                PERFILES_MSG_FALLO_JSON.format(e),
            ).exec_()

    def guardar_perfil_actual(self):
        if not self.obtener_parametros_callback:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ATENCION,
                PERFILES_MSG_SIN_CALLBACK,
            ).exec_()
            return
        ruta = seleccionar_guardar_perfil()
        if not ruta:
            return
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        try:
            params = self.obtener_parametros_callback()
            guardar_perfil(nombre, params)
            self.cargar_lista()
            self._mensaje_estilizado(
                QMessageBox.Information,
                PERFILES_MSG_GUARDADO,
                PERFILES_MSG_PERFIL_REGISTRADO.format(nombre),
            ).exec_()
        except Exception as e:
            logger.error(f"Error guardando perfil: {e}")
            self._mensaje_estilizado(
                QMessageBox.Critical,
                PERFILES_MSG_ERROR_GUARDADO,
                PERFILES_MSG_NO_GUARDADO.format(e),
            ).exec_()

    def eliminar_perfil(self):
        item = self.lista_perfiles.currentItem()
        if not item:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ATENCION,
                PERFILES_MSG_SELECCION_ELIMINAR,
            ).exec_()
            return
        ruta = item.data(Qt.UserRole)
        nombre = item.text()
        if ruta is None:
            self._mensaje_estilizado(
                QMessageBox.Warning,
                PERFILES_MSG_ACCION_DENEGADA,
                PERFILES_MSG_NO_ELIMINAR_SISTEMA,
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
                os.remove(ruta)
                self.cargar_lista()
                logger.info(f"Perfil eliminado: {nombre}")
            except Exception as e:
                logger.error(f"No se pudo eliminar el perfil {nombre}: {e}")
                self._mensaje_estilizado(
                    QMessageBox.Critical,
                    PERFILES_MSG_ERROR_ELIMINAR,
                    PERFILES_MSG_NO_ELIMINAR.format(e),
                ).exec_()

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
            QListWidget {{
                border: 1px solid {COLOR_BORDE};
                border-radius: 3px;
                padding: 4px;
                background-color: white;
                font-size: 12px;
                selection-background-color: {COLOR_PRIMARIO};
            }}
            QListWidget::item {{
                padding: 5px 8px;
            }}
            QListWidget::item:selected {{
                color: white;
            }}
            QLabel {{
                font-size: 12px;
                color: #333;
            }}
            QLabel[heading="true"] {{
                font-size: 16px;
                font-weight: bold;
                color: {COLOR_PRIMARIO_OSC};
            }}
            QWidget {{
                background-color: {COLOR_FONDO};
            }}
        """)