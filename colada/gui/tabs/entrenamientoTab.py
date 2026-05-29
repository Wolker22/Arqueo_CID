# -*- coding: utf-8 -*-
"""
Pestaña de Entrenamiento de COLADA – Versión Profesional
---------------------------------------------------------

Gestiona el entrenamiento del modelo VAE (Autoencoder Variacional).
El usuario puede:
- Seleccionar stacks multibanda (desde carpeta raíz de Tizona o directamente).
- Configurar hiperparámetros (tamaño de parche, épocas, batch, learning rate, etc.).
- Elegir la función de pérdida (SSIM o Trimmed MSE).
- Lanzar el entrenamiento con cancelación y barra de progreso.
- Guardar el modelo entrenado en un archivo .pth.

La pestaña también verifica la consistencia del número de bandas de los stacks.
"""

import os
import torch
import rasterio
from typing import Optional, List, Dict, Any, Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QListWidget,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QFrame,
    QListWidgetItem,
)
from qgis.core import QgsApplication

from ....config import (
    EPOCAS,
    BATCH_SIZE,
    LEARNING_RATE,
    VAE_IN_CHANNELS,
    VAE_LATENT_DIM,
    VAE_FEATURES,
    TAMANO_PARCHE,
    PATHS_PER_EPOCH,
    MAX_CACHE_SIZE,
    VAL_SPLIT,
    PATIENCE,
    KL_WEIGHT,
    K_TRIM,
    SEED,
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_FONDO,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    ENTRENAMIENTO_GROUP_ALGORITMO,
    ENTRENAMIENTO_GROUP_MODELO,
    ENTRENAMIENTO_GROUP_OPTIMIZACION,
    ENTRENAMIENTO_GROUP_DATASET,
    ENTRENAMIENTO_GROUP_SALIDA,
    ENTRENAMIENTO_LABEL_ESTRUCTURA,
    ENTRENAMIENTO_LABEL_BANDAS,
    ENTRENAMIENTO_LABEL_PARCHE,
    ENTRENAMIENTO_LABEL_EPOCAS,
    ENTRENAMIENTO_LABEL_LEARNING_RATE,
    ENTRENAMIENTO_LABEL_BATCH_SIZE,
    ENTRENAMIENTO_LABEL_GUARDAR_EN,
    ENTRENAMIENTO_BUTTON_ANADIR,
    ENTRENAMIENTO_BUTTON_LIMPIAR,
    ENTRENAMIENTO_BUTTON_EXAMINAR,
    ENTRENAMIENTO_BUTTON_EJECUTAR,
    ENTRENAMIENTO_MSG_SIN_DATOS_TITULO,
    ENTRENAMIENTO_MSG_SIN_DATOS_TEXTO,
    ENTRENAMIENTO_MSG_RUTA_INVALIDA_TITULO,
    ENTRENAMIENTO_MSG_RUTA_INVALIDA_TEXTO,
    ENTRENAMIENTO_BANDAS_RANGE,
    ENTRENAMIENTO_BANDAS_DEFAULT,
    ENTRENAMIENTO_PARCHE_RANGE,
    ENTRENAMIENTO_PARCHE_DEFAULT,
    ENTRENAMIENTO_EPOCAS_RANGE,
    ENTRENAMIENTO_EPOCAS_DEFAULT,
    ENTRENAMIENTO_LR_RANGE,
    ENTRENAMIENTO_LR_DEFAULT,
    ENTRENAMIENTO_LR_DECIMALS,
    ENTRENAMIENTO_BATCH_RANGE,
    ENTRENAMIENTO_BATCH_DEFAULT,
    ENTRENAMIENTO_RUTA_MODELO_DEFAULT,
    ENTRENAMIENTO_BOTON_PRINCIPAL_STYLE,
    ENTRENAMIENTO_BOTON_SECUNDARIO_STYLE,
    ENTRENAMIENTO_PROGRESO_FORMATO,
    ENTRENAMIENTO_PROGRESO_COMPLETADO,
    ENTRENAMIENTO_PROGRESO_CANCELADO,
    CARPETA_STACKS,
    USAR_GPU,
    NUM_WORKERS_DATALOADER,
)
from ...core.entrenador import entrenar_vae
from ..dialogoProgreso import ProgresoCOLADA
from ...tasks.pipeline_entrenamiento import lanzar_entrenamiento
from ....utils.logging import get_logger

logger = get_logger('Colada.gui.entrenamiento')

# Mensajes específicos de la pestaña
MSG_BANDAS_INCONSISTENTES = "Los archivos seleccionados tienen diferente número de bandas.\nSe esperaba un único valor.\nBandas encontradas: {}"
MSG_BANDAS_DETECTADAS = "Número de bandas detectado: {}"


class TabEntrenamiento(QWidget):
    """
    Pestaña de entrenamiento del VAE.

    Attributes:
        _bandas_actuales: Número de bandas detectado en los stacks (None si no hay o inconsistentes)
        _tarea_actual: Referencia a la tarea de entrenamiento en curso
        list_dataset: Lista de rutas de stacks seleccionados
        spin_bandas: Número de bandas (se autoajusta)
        spin_parche: Tamaño del parche
        spin_epocas: Número de épocas
        spin_lr: Learning rate
        spin_batch: Batch size
        combo_loss: Función de pérdida (SSIM/MSE)
        spin_kl_weight: Peso del término KL
        spin_k_trim: Fracción de recorte para trimmed MSE
        spin_val_split: Fracción de validación
        spin_patience: Paciencia para early stopping
        spin_patches_epoch: Parches por época
        spin_cache_size: Tamaño de la caché de archivos
        spin_seed: Semilla aleatoria
        edit_ruta_salida: Ruta donde guardar el modelo
        btn_ejecutar: Botón de inicio de entrenamiento
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._bandas_actuales: Optional[int] = None
        self._tarea_actual: Optional[Any] = None
        self._init_ui()
        self._conectar_senales()
        self._aplicar_hoja_estilos()
        self._actualizar_bandas_desde_lista()

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

        # ── Algoritmo de Red (solo VAE por ahora) ──────────────────────────
        grupo_estrategia = QGroupBox(ENTRENAMIENTO_GROUP_ALGORITMO)
        form_est = QFormLayout(grupo_estrategia)
        form_est.setSpacing(4)
        self.combo_modelo = QComboBox()
        self.combo_modelo.addItems(["Autoencoder Variacional (VAE)"])
        self.combo_modelo.setCurrentIndex(0)
        self.combo_modelo.setEnabled(False)  # Solo VAE por ahora
        form_est.addRow(ENTRENAMIENTO_LABEL_ESTRUCTURA, self.combo_modelo)
        layout.addWidget(grupo_estrategia)

        # ── Parámetros del Modelo ──────────────────────────────────────────
        grupo_modelo = QGroupBox(ENTRENAMIENTO_GROUP_MODELO)
        form_modelo = QFormLayout(grupo_modelo)
        form_modelo.setSpacing(4)

        self.spin_bandas = QSpinBox()
        self.spin_bandas.setRange(*ENTRENAMIENTO_BANDAS_RANGE)
        self.spin_bandas.setValue(ENTRENAMIENTO_BANDAS_DEFAULT)
        self.spin_bandas.setToolTip("Número de bandas de entrada. Se autoajustará al añadir stacks.")
        form_modelo.addRow(ENTRENAMIENTO_LABEL_BANDAS, self.spin_bandas)

        self.spin_parche = QSpinBox()
        self.spin_parche.setRange(*ENTRENAMIENTO_PARCHE_RANGE)
        self.spin_parche.setValue(ENTRENAMIENTO_PARCHE_DEFAULT)
        form_modelo.addRow(ENTRENAMIENTO_LABEL_PARCHE, self.spin_parche)

        layout.addWidget(grupo_modelo)

        # ── Hiperparámetros básicos ────────────────────────────────────────
        grupo_hiper = QGroupBox(ENTRENAMIENTO_GROUP_OPTIMIZACION)
        form_hiper = QFormLayout(grupo_hiper)
        form_hiper.setSpacing(4)

        self.spin_epocas = QSpinBox()
        self.spin_epocas.setRange(*ENTRENAMIENTO_EPOCAS_RANGE)
        self.spin_epocas.setValue(ENTRENAMIENTO_EPOCAS_DEFAULT)
        form_hiper.addRow(ENTRENAMIENTO_LABEL_EPOCAS, self.spin_epocas)

        self.spin_lr = QDoubleSpinBox()
        self.spin_lr.setRange(*ENTRENAMIENTO_LR_RANGE)
        self.spin_lr.setDecimals(ENTRENAMIENTO_LR_DECIMALS)
        self.spin_lr.setValue(ENTRENAMIENTO_LR_DEFAULT)
        form_hiper.addRow(ENTRENAMIENTO_LABEL_LEARNING_RATE, self.spin_lr)

        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(*ENTRENAMIENTO_BATCH_RANGE)
        self.spin_batch.setValue(ENTRENAMIENTO_BATCH_DEFAULT)
        form_hiper.addRow(ENTRENAMIENTO_LABEL_BATCH_SIZE, self.spin_batch)

        layout.addWidget(grupo_hiper)

        # ── Parámetros avanzados ───────────────────────────────────────────
        grupo_avanzado = QGroupBox("Avanzado (hiperparámetros)")
        form_avanzado = QFormLayout(grupo_avanzado)
        form_avanzado.setSpacing(4)

        self.combo_loss = QComboBox()
        self.combo_loss.addItems(["SSIM", "MSE"])
        self.combo_loss.setToolTip(
            "SSIM: Mejor para bordes y texturas. MSE: Mejor para cota y formas globales."
        )
        form_avanzado.addRow("Función de pérdida:", self.combo_loss)

        self.spin_kl_weight = QDoubleSpinBox()
        self.spin_kl_weight.setRange(0, 0.1)
        self.spin_kl_weight.setDecimals(6)
        self.spin_kl_weight.setSingleStep(0.0001)
        self.spin_kl_weight.setValue(KL_WEIGHT)
        form_avanzado.addRow("Peso KL:", self.spin_kl_weight)

        self.spin_k_trim = QDoubleSpinBox()
        self.spin_k_trim.setRange(0, 0.5)
        self.spin_k_trim.setDecimals(3)
        self.spin_k_trim.setSingleStep(0.005)
        self.spin_k_trim.setValue(K_TRIM)
        self.spin_k_trim.setToolTip(
            "Si usas MSE, recorta el peor X% de píxeles para ignorar anomalías."
        )
        form_avanzado.addRow("Recorte (Trimmed MSE):", self.spin_k_trim)

        self.spin_val_split = QDoubleSpinBox()
        self.spin_val_split.setRange(0, 0.5)
        self.spin_val_split.setDecimals(2)
        self.spin_val_split.setSingleStep(0.05)
        self.spin_val_split.setValue(VAL_SPLIT)
        form_avanzado.addRow("Fracción validación:", self.spin_val_split)

        self.spin_patience = QSpinBox()
        self.spin_patience.setRange(1, 50)
        self.spin_patience.setValue(PATIENCE)
        form_avanzado.addRow("Paciencia (early stopping):", self.spin_patience)

        self.spin_patches_epoch = QSpinBox()
        self.spin_patches_epoch.setRange(500, 50000)
        self.spin_patches_epoch.setSingleStep(1000)
        self.spin_patches_epoch.setValue(PATHS_PER_EPOCH)
        form_avanzado.addRow("Parches por época:", self.spin_patches_epoch)

        self.spin_cache_size = QSpinBox()
        self.spin_cache_size.setRange(1, 50)
        self.spin_cache_size.setValue(MAX_CACHE_SIZE)
        form_avanzado.addRow("Tamaño caché (archivos):", self.spin_cache_size)

        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(1, 999999)
        self.spin_seed.setValue(SEED)
        form_avanzado.addRow("Semilla aleatoria:", self.spin_seed)

        layout.addWidget(grupo_avanzado)

        # ── Dataset GeoTIFF ────────────────────────────────────────────────
        grupo_dataset = QGroupBox(ENTRENAMIENTO_GROUP_DATASET)
        lay_data = QVBoxLayout(grupo_dataset)
        lay_data.setSpacing(4)

        self.list_dataset = QListWidget()
        self.list_dataset.setMinimumHeight(140)
        self.list_dataset.setMaximumHeight(200)
        self.list_dataset.setAlternatingRowColors(True)
        self.list_dataset.setWordWrap(True)
        self.list_dataset.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        lay_data.addWidget(self.list_dataset)

        lay_botones = QHBoxLayout()
        lay_botones.setSpacing(4)
        self.btn_anadir = QPushButton(ENTRENAMIENTO_BUTTON_ANADIR)
        self.btn_limpiar = QPushButton(ENTRENAMIENTO_BUTTON_LIMPIAR)
        self._forzar_estilo_boton(self.btn_anadir, "secundario")
        self._forzar_estilo_boton(self.btn_limpiar, "secundario")
        lay_botones.addWidget(self.btn_anadir)
        lay_botones.addWidget(self.btn_limpiar)
        lay_data.addLayout(lay_botones)

        self.lbl_estado_bandas = QLabel("")
        self.lbl_estado_bandas.setStyleSheet("color: #666; font-size: 11px;")
        lay_data.addWidget(self.lbl_estado_bandas)

        layout.addWidget(grupo_dataset)

        # ── Ruta de salida del modelo ──────────────────────────────────────
        grupo_salida = QGroupBox(ENTRENAMIENTO_GROUP_SALIDA)
        form_salida = QFormLayout(grupo_salida)
        form_salida.setSpacing(4)

        self.edit_ruta_salida = QLineEdit(ENTRENAMIENTO_RUTA_MODELO_DEFAULT)
        self.btn_buscar_salida = QPushButton(ENTRENAMIENTO_BUTTON_EXAMINAR)
        self._forzar_estilo_boton(self.btn_buscar_salida, "secundario")
        layout_salida = QHBoxLayout()
        layout_salida.setSpacing(4)
        layout_salida.addWidget(self.edit_ruta_salida)
        layout_salida.addWidget(self.btn_buscar_salida)
        form_salida.addRow(ENTRENAMIENTO_LABEL_GUARDAR_EN, layout_salida)
        layout.addWidget(grupo_salida)

        # ── Botón de entrenamiento ─────────────────────────────────────────
        self.btn_ejecutar = QPushButton(ENTRENAMIENTO_BUTTON_EJECUTAR)
        self._forzar_estilo_boton(self.btn_ejecutar, "principal")
        layout.addWidget(self.btn_ejecutar)

        layout.addStretch()
        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    def _forzar_estilo_boton(self, boton: QPushButton, tipo: str = "normal") -> None:
        """Aplica el estilo CSS correspondiente al botón."""
        if tipo == "principal":
            css = ENTRENAMIENTO_BOTON_PRINCIPAL_STYLE
        else:
            css = ENTRENAMIENTO_BOTON_SECUNDARIO_STYLE
        boton.setStyleSheet(css)

    def _conectar_senales(self) -> None:
        """Conecta las señales de los botones a sus slots."""
        self.btn_anadir.clicked.connect(self._anadir_directorio)
        self.btn_limpiar.clicked.connect(self._limpiar_lista)
        self.btn_buscar_salida.clicked.connect(self._seleccionar_ruta_salida)
        self.btn_ejecutar.clicked.connect(self._iniciar_entrenamiento)

    # ------------------------------------------------------------------
    # Validación de bandas de los stacks
    # ------------------------------------------------------------------

    def _verificar_bandas_archivos(self, rutas: List[str]) -> tuple:
        """
        Verifica que todos los archivos tengan el mismo número de bandas.

        Args:
            rutas: Lista de rutas a archivos GeoTIFF.

        Returns:
            (exito, num_bandas, errores)
        """
        bandas_set = set()
        errores = []
        for ruta in rutas:
            try:
                with rasterio.open(ruta) as src:
                    bandas_set.add(src.count)
            except Exception as e:
                errores.append(f"{os.path.basename(ruta)}: {e}")
        if errores:
            return False, None, errores
        if len(bandas_set) == 0:
            return False, None, ["No hay archivos válidos"]
        if len(bandas_set) > 1:
            return False, None, [MSG_BANDAS_INCONSISTENTES.format(sorted(bandas_set))]
        return True, bandas_set.pop(), []

    def _actualizar_bandas_desde_lista(self) -> None:
        """Actualiza el número de bandas según los stacks seleccionados."""
        if self.list_dataset.count() == 0:
            self.spin_bandas.setValue(ENTRENAMIENTO_BANDAS_DEFAULT)
            self.spin_bandas.setEnabled(True)
            self.lbl_estado_bandas.setText("")
            self._bandas_actuales = None
            return

        rutas = [self.list_dataset.item(i).text() for i in range(self.list_dataset.count())]
        exito, num_bandas, errores = self._verificar_bandas_archivos(rutas)

        if exito:
            self.spin_bandas.setValue(num_bandas)
            self.spin_bandas.setEnabled(False)
            self.lbl_estado_bandas.setText(MSG_BANDAS_DETECTADAS.format(num_bandas))
            self.lbl_estado_bandas.setStyleSheet("color: green; font-size: 11px;")
            self._bandas_actuales = num_bandas
            self.btn_ejecutar.setEnabled(True)
        else:
            self.spin_bandas.setEnabled(True)
            self.lbl_estado_bandas.setText(" | ".join(errores))
            self.lbl_estado_bandas.setStyleSheet("color: red; font-size: 11px;")
            self._bandas_actuales = None
            self.btn_ejecutar.setEnabled(False)

    # ------------------------------------------------------------------
    # Manejo de la lista de archivos
    # ------------------------------------------------------------------

    def _limpiar_lista(self) -> None:
        """Limpia la lista de stacks seleccionados."""
        self.list_dataset.clear()
        self._actualizar_bandas_desde_lista()
        self.btn_ejecutar.setEnabled(True)

    def _anadir_directorio(self) -> None:
        """Añade todos los stacks (archivos .tif con 'STACK' en el nombre) de una carpeta raíz."""
        directorio = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta raíz de teselas"
        )
        if not directorio:
            return

        nuevas_rutas = []
        # Buscar recursivamente carpetas '04_IA_STACKS' y archivos .tif que contengan 'STACK'
        for root, dirs, files in os.walk(directorio):
            if os.path.basename(root) == CARPETA_STACKS:
                for file in files:
                    if file.lower().endswith('.tif') and 'STACK' in file.upper():
                        ruta_completa = os.path.join(root, file)
                        if not self.list_dataset.findItems(ruta_completa, Qt.MatchExactly):
                            nuevas_rutas.append(ruta_completa)

        if not nuevas_rutas:
            QMessageBox.information(
                self,
                "No se encontraron stacks",
                f"No se encontraron archivos GeoTIFF en carpetas '{CARPETA_STACKS}' que contengan 'STACK' en su nombre."
            )
            return

        # Verificar consistencia de bandas
        exito, num_bandas, errores = self._verificar_bandas_archivos(nuevas_rutas)
        if not exito:
            QMessageBox.warning(self, "Error en dataset", "\n".join(errores))
            return

        # Si ya hay archivos, verificar que las nuevas bandas coincidan
        if self.list_dataset.count() > 0 and self._bandas_actuales is not None:
            if num_bandas != self._bandas_actuales:
                QMessageBox.warning(
                    self,
                    "Inconsistencia de bandas",
                    f"Los stacks existentes tienen {self._bandas_actuales} bandas, pero los nuevos tienen {num_bandas}."
                )
                return

        # Añadir a la lista
        for ruta in nuevas_rutas:
            item = QListWidgetItem(ruta)
            item.setToolTip(ruta)
            self.list_dataset.addItem(item)

        self._actualizar_bandas_desde_lista()

    # ------------------------------------------------------------------
   # Ruta de salida del modelo
    # ------------------------------------------------------------------

    def _seleccionar_ruta_salida(self) -> None:
        """Abre un diálogo para seleccionar dónde guardar el modelo entrenado."""
        ruta, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar modelo entrenado",
            self.edit_ruta_salida.text(),
            "PyTorch (*.pth)"
        )
        if ruta:
            self.edit_ruta_salida.setText(ruta)

    # ------------------------------------------------------------------
    # Iniciar entrenamiento
    # ------------------------------------------------------------------

    def _iniciar_entrenamiento(self) -> None:
        """Valida la configuración y lanza la tarea de entrenamiento."""
        # Validar que hay stacks seleccionados
        if self.list_dataset.count() == 0:
            QMessageBox.warning(
                self,
                ENTRENAMIENTO_MSG_SIN_DATOS_TITULO,
                ENTRENAMIENTO_MSG_SIN_DATOS_TEXTO
            )
            return

        # Validar consistencia de bandas
        if self._bandas_actuales is None:
            QMessageBox.warning(
                self,
                "Error de dataset",
                "Los archivos no tienen un número de bandas consistente."
            )
            return

        # Validar ruta de salida
        ruta_salida = self.edit_ruta_salida.text().strip()
        if not ruta_salida:
            QMessageBox.warning(
                self,
                ENTRENAMIENTO_MSG_RUTA_INVALIDA_TITULO,
                ENTRENAMIENTO_MSG_RUTA_INVALIDA_TEXTO
            )
            return

        # Recoger parámetros
        archivos = [self.list_dataset.item(i).text() for i in range(self.list_dataset.count())]
        in_channels = self.spin_bandas.value()
        patch_size = self.spin_parche.value()
        epocas = self.spin_epocas.value()
        batch_size = self.spin_batch.value()
        lr = self.spin_lr.value()
        features = VAE_FEATURES
        latent_dim = VAE_LATENT_DIM
        loss_fn = self.combo_loss.currentText().lower()

        # Obtener num_workers desde la pestaña de rendimiento (si está disponible)
        num_workers = NUM_WORKERS_DATALOADER
        try:
            parent_dialog = self.parent().parent()
            if hasattr(parent_dialog, 'tab_rendimiento'):
                num_workers = parent_dialog.tab_rendimiento.spin_dataloader.value()
        except Exception as e:
            logger.debug(f"No se pudo obtener num_workers de la UI: {e}")

        config_entrenamiento = {
            'in_channels': in_channels,
            'latent_dim': latent_dim,
            'features': features,
            'tamanio_parche': patch_size,
            'epocas': epocas,
            'batch_size': batch_size,
            'learning_rate': lr,
            'k_trim': self.spin_k_trim.value(),
            'kl_weight': self.spin_kl_weight.value(),
            'val_split': self.spin_val_split.value(),
            'patience': self.spin_patience.value(),
            'patches_per_epoch': self.spin_patches_epoch.value(),
            'seed': self.spin_seed.value(),
            'num_workers': num_workers,
            'loss_function': loss_fn,
            'dispositivo': 'cuda' if USAR_GPU and torch.cuda.is_available() else 'cpu',
        }

        # Crear diálogo de progreso
        progreso = ProgresoCOLADA(modo='training', parent=self)
        progreso.show()

        # Lanzar tarea de entrenamiento
        tarea = lanzar_entrenamiento(
            archivos=archivos,
            ruta_modelo=ruta_salida,
            config=config_entrenamiento,
            dialog=progreso
        )

        # Conectar cancelación
        progreso.btn_cancelar.clicked.connect(tarea.cancel)
        self._tarea_actual = tarea

        # Añadir tarea al gestor de QGIS
        QgsApplication.taskManager().addTask(tarea)

        # Deshabilitar botón de ejecución durante el entrenamiento
        self.btn_ejecutar.setEnabled(False)
        tarea.taskCompleted.connect(lambda: self.btn_ejecutar.setEnabled(True))
        tarea.taskTerminated.connect(lambda: self.btn_ejecutar.setEnabled(True))

        # Log inicial
        progreso.log_info("=== INICIO DEL ENTRENAMIENTO VAE (QgsTask) ===")
        progreso.log_info(f"Función de pérdida principal: {loss_fn.upper()}")
        progreso.log_info(f"Archivos de entrenamiento: {len(archivos)} stacks")
        progreso.log_info(f"Número de bandas: {in_channels}")
        progreso.log_info(f"Tamaño de parche: {patch_size} px")
        progreso.log_info(f"Batch size: {batch_size}, Learning rate: {lr}")
        progreso.log_info(f"Dispositivo: {config_entrenamiento['dispositivo'].upper()}")

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
                border-radius: 3px;
                padding: 4px;
                background-color: white;
                alternate-background-color: #f5f5f5;
                selection-background-color: {COLADA_COLOR_PRIMARIO};
                font-size: 12px;
            }}
            QListWidget::item {{ padding: 4px 6px; }}
            QListWidget::item:selected {{ color: white; }}
            QLineEdit {{
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 3px;
                padding: 4px;
                background-color: white;
                font-size: 12px;
            }}
            QLabel {{ font-size: 12px; }}
            QScrollArea {{ border: none; }}
        """)