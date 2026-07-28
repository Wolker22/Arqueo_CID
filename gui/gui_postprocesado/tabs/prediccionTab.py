# -*- coding: utf-8 -*-
"""
Pestaña de Predicción de COLADA – Versión Concurrente
------------------------------------------------------

Orquesta la inferencia del modelo (VAE o Isolation Forest) sobre stacks multibanda.
Mantiene la UI libre de bloqueos mediante QThread y asignación segura de variables.

Permite:
- Cargar un stack GeoTIFF (desde disco o desde la pestaña de filtros).
- Seleccionar algoritmo: VAE (SSIM/MSE) o Isolation Forest.
- Configurar hiperparámetros (tamaño de parche, solape, sigma, umbral, etc.).
- Ejecutar la predicción con cancelación y barra de progreso.
- Visualizar el resultado (mapa de anomalías) en un visor con colormap.
- Guardar el resultado como GeoTIFF o enviarlo al mapa de QGIS.
"""

import os
import tempfile
import uuid
import gc
import threading
import traceback
from typing import Optional, Dict, Any, Callable

import numpy as np
import rasterio
import torch

from qgis.PyQt.QtCore import Qt, pyqtSignal, QThread
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
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QFrame,
)

from ....config import (
    TAMANO_PARCHE,
    SOLAPAMIENTO,
    TAMANIO_LOTE,
    SIGMA_GAUSSIANO,
    UMBRAL_PERCENTIL,
    COLADA_COLOR_PRIMARIO,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_FONDO,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    PREDICCION_GROUP_ALGORITMO,
    PREDICCION_GROUP_MODELO,
    PREDICCION_GROUP_PARAMS,
    PREDICCION_GROUP_SALIDA,
    PREDICCION_LABEL_METODO,
    PREDICCION_LABEL_PARCHE,
    PREDICCION_LABEL_SOLAPE,
    PREDICCION_LABEL_BATCH,
    PREDICCION_LABEL_SIGMA,
    PREDICCION_LABEL_UMBRAL,
    PREDICCION_LABEL_DIRECTORIO,
    PREDICCION_LABEL_SIN_MODELO,
    PREDICCION_LABEL_SIN_DATOS,
    PREDICCION_BTN_EXAMINAR,
    PREDICCION_BTN_CARGAR_MODELO,
    PREDICCION_BTN_SELECCIONAR_ENTRENAMIENTO,
    PREDICCION_BTN_EJECUTAR,
    PREDICCION_BTN_GUARDAR,
    PREDICCION_BTN_MAPA,
    PREDICCION_ALGORITMOS,
    PREDICCION_ALGORITMO_DEFAULT,
    PREDICCION_PARCHE_RANGE,
    PREDICCION_PARCHE_DEFAULT,
    PREDICCION_SOLAPE_RANGE,
    PREDICCION_SOLAPE_DEFAULT,
    PREDICCION_LOTE_RANGE,
    PREDICCION_LOTE_DEFAULT,
    PREDICCION_SIGMA_RANGE,
    PREDICCION_SIGMA_DEFAULT,
    PREDICCION_UMBRAL_RANGE,
    PREDICCION_UMBRAL_DEFAULT,
    PREDICCION_MSG_SIN_IMAGEN_TITULO,
    PREDICCION_MSG_SIN_IMAGEN_TEXTO,
    PREDICCION_MSG_SIN_ENTRENAMIENTO,
    PREDICCION_MSG_SIN_TIF_ENTRENAMIENTO,
    PREDICCION_MSG_SIN_MODELO,
    PREDICCION_MSG_INFERENCIA_COMPLETADA,
    PREDICCION_BOTON_PRINCIPAL_STYLE,
    PREDICCION_BOTON_SECUNDARIO_STYLE,
    PREDICCION_BOTON_NORMAL_STYLE,
    VENTANA_ADAPTATIVA,
    MIN_AREA_ANOMALIA_M2,
    ASPECT_RATIO_MAX,
    CIRCULARITY_MIN,
    ISOLATION_FOREST_N_ESTIMATORS,
    ISOLATION_FOREST_CONTAMINATION,
    ISOLATION_FOREST_MAX_SAMPLES,
)
from ..visor_derivados import VisorDerivados
from ....core.core_postprocesado.predictor import (
    cargar_modelo_vae,
    leer_stack_multibanda,
    extraer_parches_generator,
    inferir_y_reconstruir,
    suavizar_y_umbralizar,
    predecir_anomalia_isolation_forest,
)
from ..dialogoProgreso import ProgresoCOLADA
from ....utils.logging import get_logger

logger = get_logger('Colada.gui.prediccion')


class PrediccionWorker(QThread):
    """
    Hilo de trabajo para ejecutar la predicción (VAE o Isolation Forest) sin bloquear la UI.

    Señales:
        proceso_terminado: (éxito, mensaje)
        progress: (porcentaje, mensaje)
        log: (nivel, mensaje)
    """

    proceso_terminado = pyqtSignal(bool, str)
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)

    def __init__(
        self,
        idx: int,
        imagen_original: np.ndarray,
        profile_original: Dict[str, Any],
        modelo_ruta: Optional[str],
        if_dir: Optional[str],
        params: Dict[str, Any],
    ) -> None:
        """
        Args:
            idx: Índice del algoritmo (0=VAE SSIM, 1=VAE MSE, 2=Isolation Forest)
            imagen_original: Array (bandas, alto, ancho) o (alto, ancho)
            profile_original: Perfil de rasterio de la imagen original
            modelo_ruta: Ruta al archivo .pth del modelo VAE (si aplica)
            if_dir: Directorio con stacks de entrenamiento para Isolation Forest
            params: Diccionario con parámetros de inferencia
        """
        super().__init__()
        self.idx = idx
        self.imagen_original = imagen_original
        self.profile_original = profile_original
        self.modelo_ruta = modelo_ruta
        self.if_dir = if_dir
        self.params = params
        self._cancel_event = threading.Event()
        self.prediccion_result: Optional[np.ndarray] = None

    def cancel(self) -> None:
        """Solicita la cancelación del hilo."""
        self._cancel_event.set()

    def run(self) -> None:
        """Método principal del hilo (ejecuta la inferencia)."""
        temp_stack = None
        try:
            self.log.emit("info", "Preparando stack de análisis...")
            fd, temp_stack = tempfile.mkstemp(suffix=".tif", prefix="colada_stack_")
            os.close(fd)

            perfil = self.profile_original.copy()
            with rasterio.open(temp_stack, "w", **perfil) as dst:
                if self.imagen_original.ndim == 2:
                    dst.write(np.expand_dims(self.imagen_original, 0), 1)
                else:
                    for b in range(self.imagen_original.shape[0]):
                        dst.write(self.imagen_original[b], b + 1)

            prediccion: Optional[np.ndarray] = None

            # Isolation Forest (índice 2)
            if self.idx == 2:
                self.log.emit("info", "=== INICIANDO ISOLATION FOREST ===")
                if not self.if_dir:
                    raise RuntimeError(PREDICCION_MSG_SIN_ENTRENAMIENTO)

                if self._cancel_event.is_set():
                    return

                # Buscar todos los archivos .tif en el directorio de entrenamiento
                archivos_entrenamiento = []
                for root, _, files in os.walk(self.if_dir):
                    for f in files:
                        if f.lower().endswith(".tif"):
                            archivos_entrenamiento.append(os.path.join(root, f))

                if not archivos_entrenamiento:
                    raise RuntimeError(PREDICCION_MSG_SIN_TIF_ENTRENAMIENTO)

                # Verificar número de bandas
                with rasterio.open(temp_stack) as src:
                    expected_bands = src.count

                archivos_validos = []
                for archivo in archivos_entrenamiento:
                    try:
                        with rasterio.open(archivo) as src:
                            if src.count == expected_bands:
                                archivos_validos.append(archivo)
                    except Exception:
                        pass

                if not archivos_validos:
                    raise RuntimeError(f"No hay stacks de entrenamiento válidos con {expected_bands} bandas.")

                def progress_cb(pct: int, msg: str) -> None:
                    if not self._cancel_event.is_set():
                        self.progress.emit(pct, msg)

                self.log.emit("info", "Procesando matriz mediante Isolation Forest...")
                prediccion = predecir_anomalia_isolation_forest(
                    ruta_stack=temp_stack,
                    archivos_entrenamiento=archivos_validos,
                    output_tif=None,
                    sigma=self.params.get("sigma", SIGMA_GAUSSIANO),
                    umbral_pct=self.params.get("umbral", UMBRAL_PERCENTIL),
                    min_area_m2=self.params.get("min_area", MIN_AREA_ANOMALIA_M2),
                    n_estimators=self.params.get("if_estimators", ISOLATION_FOREST_N_ESTIMATORS),
                    contamination=self.params.get("if_contamination", ISOLATION_FOREST_CONTAMINATION),
                    max_samples=self.params.get("if_max_samples", ISOLATION_FOREST_MAX_SAMPLES),
                    cpu_workers=self.params.get("cpu_workers", 2),
                    progress_callback=progress_cb,
                    cancel_event=self._cancel_event,
                )

            # VAE (índices 0 y 1)
            else:
                self.log.emit("info", "=== INICIANDO RED NEURONAL VAE ===")
                if not self.modelo_ruta:
                    raise RuntimeError(PREDICCION_MSG_SIN_MODELO)

                # Cargar modelo
                modelo, meta, norm_params = cargar_modelo_vae(
                    self.modelo_ruta,
                    "cuda" if torch.cuda.is_available() else "cpu"
                )
                _, _, _, patch_modelo = meta
                tamanio_parche = self.params.get("parche", TAMANO_PARCHE)

                if patch_modelo != tamanio_parche:
                    self.log.emit("warning", f"Forzando tamaño de parche a {patch_modelo} px (requerido por el modelo)")
                    tamanio_parche = patch_modelo

                # Leer stack
                arr, geotrans, (cols, filas), proj = leer_stack_multibanda(temp_stack)

                # Generador de parches
                gen = extraer_parches_generator(
                    arr,
                    tamanio=tamanio_parche,
                    solape=self.params.get("solape", SOLAPAMIENTO),
                    norm_params=norm_params,
                )

                def inferencia_callback(pct: int) -> None:
                    if not self._cancel_event.is_set():
                        self.progress.emit(int(10 + pct * 0.75), f"Inferencia tensorial... {pct}%")

                self.log.emit("info", "Inyectando bloques en VAE...")
                mapa_anomalia = inferir_y_reconstruir(
                    modelo,
                    gen,
                    (filas, cols),
                    dispositivo="cuda" if torch.cuda.is_available() else "cpu",
                    tamanio_lote=self.params.get("lote", TAMANIO_LOTE),
                    callback=inferencia_callback,
                    cancel_event=self._cancel_event,
                )

                self.log.emit("info", "Generando topología suavizada...")
                self.progress.emit(85, "Calculando topología final...")
                mapa_suave, _ = suavizar_y_umbralizar(
                    mapa_anomalia,
                    sigma=self.params.get("sigma", SIGMA_GAUSSIANO),
                    umbral_pct=self.params.get("umbral", UMBRAL_PERCENTIL),
                    ventana_adaptativa=self.params.get("ventana_adapt", VENTANA_ADAPTATIVA),
                )
                prediccion = mapa_suave

            if prediccion is None:
                raise RuntimeError("Falló la generación de matriz espacial")

            self.prediccion_result = prediccion
            self.progress.emit(100, "Renderizando visualización raster...")
            self.proceso_terminado.emit(True, PREDICCION_MSG_INFERENCIA_COMPLETADA)

        except InterruptedError:
            self.log.emit("info", "Proceso abortado por el usuario.")
            self.proceso_terminado.emit(False, "Cancelada")
        except Exception as e:
            self.log.emit("error", f"Error en hilo de inferencia: {str(e)}\n{traceback.format_exc()}")
            self.proceso_terminado.emit(False, str(e))
        finally:
            if temp_stack and os.path.exists(temp_stack):
                try:
                    os.remove(temp_stack)
                except Exception:
                    pass
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()


class TabPrediccion(QWidget):
    """
    Pestaña de predicción de anomalías.

    Attributes:
        _imagen_original: Array original (bandas, alto, ancho) o (alto, ancho)
        _imagen_prediccion: Resultado de la predicción (alto, ancho)
        _profile_original: Perfil rasterio de la imagen original
        _nombre_tesela_activa: Nombre de la tesela activa
        _modelo_ruta: Ruta al modelo VAE
        _if_dir: Directorio con stacks de entrenamiento para IF
        _worker: Hilo de trabajo (PrediccionWorker)
        _progreso: Diálogo de progreso
        visor_prediccion: Visor de imágenes
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._imagen_original: Optional[np.ndarray] = None
        self._imagen_prediccion: Optional[np.ndarray] = None
        self._profile_original: Optional[Dict[str, Any]] = None
        self._nombre_tesela_activa: str = "Ninguna"
        self._modelo_ruta: Optional[str] = None
        self._if_dir: Optional[str] = None
        self._worker: Optional[PrediccionWorker] = None
        self._progreso: Optional[ProgresoCOLADA] = None

        self.visor_prediccion = VisorDerivados()
        self._init_ui()
        self._conectar_senales()
        self._aplicar_hoja_estilos()

    # ------------------------------------------------------------------
    # Propiedades públicas
    # ------------------------------------------------------------------

    @property
    def imagen_resultante(self) -> Optional[np.ndarray]:
        return self._imagen_prediccion

    @property
    def perfil_original(self) -> Optional[Dict[str, Any]]:
        return self._profile_original

    @property
    def nombre_tesela(self) -> str:
        return self._nombre_tesela_activa

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------

    def establecer_imagen_original(
        self,
        matriz: Optional[np.ndarray],
        perfil: Optional[Dict[str, Any]],
        nombre_tesela: str,
    ) -> None:
        """
        Establece la imagen original (desde la pestaña de filtros).

        Args:
            matriz: Array de imagen (2D o 3D)
            perfil: Perfil de rasterio
            nombre_tesela: Nombre de la tesela
        """
        self._imagen_original = matriz.copy() if matriz is not None else None
        self._profile_original = perfil
        self._nombre_tesela_activa = nombre_tesela
        self._imagen_prediccion = None
        if hasattr(self, 'visor_prediccion'):
            self.visor_prediccion.mostrar_imagen(None)
        if hasattr(self, 'lbl_dir_ruta') and perfil and 'source' in perfil:
            self.lbl_dir_ruta.setText(f"Imagen Activa: {nombre_tesela}")
        else:
            self.lbl_dir_ruta.setText(PREDICCION_LABEL_DIRECTORIO)

    def limpiar_estado(self) -> None:
        """Limpia el estado cuando cambia la tesela."""
        self._imagen_prediccion = None
        if hasattr(self, 'visor_prediccion'):
            self.visor_prediccion.mostrar_imagen(None)

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout_principal = QHBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.addWidget(self.visor_prediccion, 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        panel = QWidget()
        lay_controles = QVBoxLayout(panel)
        lay_controles.setSpacing(6)
        lay_controles.setContentsMargins(8, 8, 8, 8)

        # Directorio actual
        self.lbl_dir_ruta = QLabel(PREDICCION_LABEL_DIRECTORIO)
        self.lbl_dir_ruta.setStyleSheet("color: #666; font-style: italic; font-size: 10px;")
        self.lbl_dir_ruta.setWordWrap(True)
        lay_controles.addWidget(self.lbl_dir_ruta)

        # Botón para cargar stack manual
        self.btn_buscar_archivo = QPushButton(PREDICCION_BTN_EXAMINAR)
        self._forzar_estilo_boton(self.btn_buscar_archivo, "secundario")
        lay_controles.addWidget(self.btn_buscar_archivo)

        # Grupo: Algoritmo
        grupo_algo = QGroupBox(PREDICCION_GROUP_ALGORITMO)
        form_algo = QFormLayout(grupo_algo)
        self.combo_algoritmo = QComboBox()
        self.combo_algoritmo.addItems(PREDICCION_ALGORITMOS)
        self.combo_algoritmo.setCurrentIndex(PREDICCION_ALGORITMO_DEFAULT)
        self.combo_algoritmo.currentIndexChanged.connect(self._actualizar_panel_modelo)
        form_algo.addRow(PREDICCION_LABEL_METODO, self.combo_algoritmo)
        lay_controles.addWidget(grupo_algo)

        # Grupo: Modelo / Datos (VAE o Isolation Forest)
        self.grupo_modelo = QGroupBox(PREDICCION_GROUP_MODELO)
        self.form_modelo = QFormLayout(self.grupo_modelo)

        # Botón cargar modelo VAE
        self.btn_cargar_modelo = QPushButton(PREDICCION_BTN_CARGAR_MODELO)
        self._forzar_estilo_boton(self.btn_cargar_modelo, "secundario")
        self.lbl_modelo_ruta = QLabel(PREDICCION_LABEL_SIN_MODELO)
        self.lbl_modelo_ruta.setWordWrap(True)
        self.form_modelo.addRow(self.btn_cargar_modelo, self.lbl_modelo_ruta)

        # Panel para Isolation Forest
        self.panel_if = QWidget()
        lay_if = QVBoxLayout(self.panel_if)
        self.btn_entrenamiento_if = QPushButton(PREDICCION_BTN_SELECCIONAR_ENTRENAMIENTO)
        self._forzar_estilo_boton(self.btn_entrenamiento_if, "secundario")
        self.lbl_if_ruta = QLabel(PREDICCION_LABEL_SIN_DATOS)
        self.lbl_if_ruta.setWordWrap(True)
        lay_if.addWidget(self.btn_entrenamiento_if)
        lay_if.addWidget(self.lbl_if_ruta)
        self.panel_if.hide()
        self.form_modelo.addRow(self.panel_if)

        lay_controles.addWidget(self.grupo_modelo)

        # Grupo: Parámetros de inferencia
        grupo_params = QGroupBox(PREDICCION_GROUP_PARAMS)
        form_params = QFormLayout(grupo_params)

        self.spin_parche = QSpinBox()
        self.spin_parche.setRange(*PREDICCION_PARCHE_RANGE)
        self.spin_parche.setValue(PREDICCION_PARCHE_DEFAULT)
        form_params.addRow(PREDICCION_LABEL_PARCHE, self.spin_parche)

        self.spin_solape = QSpinBox()
        self.spin_solape.setRange(*PREDICCION_SOLAPE_RANGE)
        self.spin_solape.setValue(PREDICCION_SOLAPE_DEFAULT)
        form_params.addRow(PREDICCION_LABEL_SOLAPE, self.spin_solape)

        self.spin_lote = QSpinBox()
        self.spin_lote.setRange(*PREDICCION_LOTE_RANGE)
        self.spin_lote.setValue(PREDICCION_LOTE_DEFAULT)
        form_params.addRow(PREDICCION_LABEL_BATCH, self.spin_lote)

        self.spin_sigma = QDoubleSpinBox()
        self.spin_sigma.setRange(*PREDICCION_SIGMA_RANGE)
        self.spin_sigma.setValue(PREDICCION_SIGMA_DEFAULT)
        form_params.addRow(PREDICCION_LABEL_SIGMA, self.spin_sigma)

        self.spin_umbral = QSpinBox()
        self.spin_umbral.setRange(*PREDICCION_UMBRAL_RANGE)
        self.spin_umbral.setValue(PREDICCION_UMBRAL_DEFAULT)
        form_params.addRow(PREDICCION_LABEL_UMBRAL, self.spin_umbral)

        self.spin_ventana_adapt = QSpinBox()
        self.spin_ventana_adapt.setRange(0, 500)
        self.spin_ventana_adapt.setValue(VENTANA_ADAPTATIVA)
        form_params.addRow("Umbral adaptativo (px):", self.spin_ventana_adapt)

        self.spin_min_area = QDoubleSpinBox()
        self.spin_min_area.setRange(0.1, 1000)
        self.spin_min_area.setValue(MIN_AREA_ANOMALIA_M2)
        form_params.addRow("Área mínima (m²):", self.spin_min_area)

        self.spin_aspect_ratio = QDoubleSpinBox()
        self.spin_aspect_ratio.setRange(0, 20)
        self.spin_aspect_ratio.setValue(ASPECT_RATIO_MAX)
        form_params.addRow("Aspect ratio máximo:", self.spin_aspect_ratio)

        self.spin_circularity = QDoubleSpinBox()
        self.spin_circularity.setRange(0, 1)
        self.spin_circularity.setValue(CIRCULARITY_MIN)
        form_params.addRow("Circularidad mínima:", self.spin_circularity)

        lay_controles.addWidget(grupo_params)

        # Grupo avanzado Isolation Forest
        self.grupo_if = QGroupBox("Isolation Forest (avanzado)")
        self.grupo_if.setVisible(False)
        lay_if_avanzado = QFormLayout(self.grupo_if)

        self.spin_if_estimators = QSpinBox()
        self.spin_if_estimators.setRange(10, 500)
        self.spin_if_estimators.setValue(ISOLATION_FOREST_N_ESTIMATORS)
        lay_if_avanzado.addRow("N. estimadores:", self.spin_if_estimators)

        self.spin_if_contamination = QDoubleSpinBox()
        self.spin_if_contamination.setRange(0.01, 0.5)
        self.spin_if_contamination.setValue(ISOLATION_FOREST_CONTAMINATION)
        lay_if_avanzado.addRow("Contaminación esperada:", self.spin_if_contamination)

        self.spin_if_max_samples = QSpinBox()
        self.spin_if_max_samples.setRange(1000, 200000)
        self.spin_if_max_samples.setValue(ISOLATION_FOREST_MAX_SAMPLES)
        lay_if_avanzado.addRow("Máx. muestras:", self.spin_if_max_samples)

        lay_controles.addWidget(self.grupo_if)

        # Botón ejecutar
        self.btn_ejecutar = QPushButton(PREDICCION_BTN_EJECUTAR)
        self._forzar_estilo_boton(self.btn_ejecutar, "principal")
        lay_controles.addWidget(self.btn_ejecutar)

        # Grupo de acciones
        grupo_salida = QGroupBox(PREDICCION_GROUP_SALIDA)
        lay_acciones = QHBoxLayout(grupo_salida)
        self.btn_guardar = QPushButton(PREDICCION_BTN_GUARDAR)
        self.btn_mapa = QPushButton(PREDICCION_BTN_MAPA)
        self._forzar_estilo_boton(self.btn_guardar, "normal")
        self._forzar_estilo_boton(self.btn_mapa, "normal")
        lay_acciones.addWidget(self.btn_guardar)
        lay_acciones.addWidget(self.btn_mapa)
        lay_controles.addWidget(grupo_salida)

        lay_controles.addStretch()
        scroll.setWidget(panel)
        layout_principal.addWidget(scroll, 1)

        self._actualizar_panel_modelo()

    def _forzar_estilo_boton(self, boton: QPushButton, tipo: str = "normal") -> None:
        estilos = {
            "principal": PREDICCION_BOTON_PRINCIPAL_STYLE,
            "secundario": PREDICCION_BOTON_SECUNDARIO_STYLE,
            "normal": PREDICCION_BOTON_NORMAL_STYLE,
        }
        boton.setStyleSheet(estilos.get(tipo, PREDICCION_BOTON_NORMAL_STYLE))

    def _conectar_senales(self) -> None:
        self.btn_buscar_archivo.clicked.connect(self._cargar_archivo_stack)
        self.btn_cargar_modelo.clicked.connect(self._cargar_modelo)
        self.btn_entrenamiento_if.clicked.connect(self._seleccionar_directorio_entrenamiento)
        self.btn_ejecutar.clicked.connect(self._ejecutar_inferencia)

    def _actualizar_panel_modelo(self) -> None:
        """Muestra u oculta los controles según el algoritmo seleccionado."""
        es_if = self.combo_algoritmo.currentIndex() == 2
        self.btn_cargar_modelo.setVisible(not es_if)
        self.lbl_modelo_ruta.setVisible(not es_if)
        self.panel_if.setVisible(es_if)
        self.grupo_if.setVisible(es_if)

    def _cargar_archivo_stack(self) -> None:
        """Carga un stack multibanda desde el sistema de archivos."""
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar stack multibanda (GeoTIFF)",
            "",
            "GeoTIFF (*.tif *.tiff);;Todos los archivos (*.*)"
        )
        if not ruta:
            return

        try:
            with rasterio.open(ruta) as src:
                imagen = src.read().astype(np.float32)
                perfil = src.profile
                if src.nodata is not None:
                    imagen[imagen == src.nodata] = np.nan
                self._imagen_original = imagen
                self._profile_original = perfil
                self._nombre_tesela_activa = os.path.splitext(os.path.basename(ruta))[0]
                self._imagen_prediccion = None
                self.visor_prediccion.mostrar_imagen(imagen[0, :, :])
                self.lbl_dir_ruta.setText(f"Stack cargado: {os.path.basename(ruta)}")
        except Exception as e:
            logger.error(f"Error al cargar stack: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo cargar el archivo:\n{e}")

    def _cargar_modelo(self) -> None:
        """Carga un modelo VAE entrenado (.pth)."""
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar modelo VAE",
            "",
            "Modelos PyTorch (*.pth *.pt);;Todos los archivos (*.*)"
        )
        if ruta:
            self.lbl_modelo_ruta.setText(os.path.basename(ruta))
            self._modelo_ruta = ruta

    def _seleccionar_directorio_entrenamiento(self) -> None:
        """Selecciona el directorio con stacks de entrenamiento para Isolation Forest."""
        directorio = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta con stacks de entrenamiento"
        )
        if directorio:
            self.lbl_if_ruta.setText(directorio)
            self._if_dir = directorio

    # ------------------------------------------------------------------
    # Ejecución de inferencia
    # ------------------------------------------------------------------

    def _ejecutar_inferencia(self) -> None:
        """Inicia la predicción en un hilo separado."""
        if self._imagen_original is None:
            QMessageBox.warning(
                self,
                PREDICCION_MSG_SIN_IMAGEN_TITULO,
                PREDICCION_MSG_SIN_IMAGEN_TEXTO
            )
            return

        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(self, "Proceso en curso", "Ya hay una predicción ejecutándose.")
            return

        idx = self.combo_algoritmo.currentIndex()

        self._progreso = ProgresoCOLADA(modo="prediction", parent=self)
        self._progreso.show()

        # Obtener número de hilos CPU desde la pestaña de rendimiento (si está disponible)
        hilos_cpu = 2
        try:
            # Navegar: self -> parent (tab_widget) -> parent (dialogoPrincipal) -> tab_rendimiento
            parent_dialog = self.parent().parent()
            if hasattr(parent_dialog, 'tab_rendimiento'):
                hilos_cpu = parent_dialog.tab_rendimiento.spin_cpu.value()
        except Exception as e:
            logger.debug(f"No se pudo obtener cpu_workers de la UI: {e}")

        params = {
            "sigma": self.spin_sigma.value(),
            "umbral": self.spin_umbral.value(),
            "min_area": self.spin_min_area.value(),
            "ventana_adapt": self.spin_ventana_adapt.value(),
            "aspect_ratio": self.spin_aspect_ratio.value(),
            "circularity": self.spin_circularity.value(),
            "if_estimators": self.spin_if_estimators.value(),
            "if_contamination": self.spin_if_contamination.value(),
            "if_max_samples": self.spin_if_max_samples.value(),
            "parche": self.spin_parche.value(),
            "solape": self.spin_solape.value(),
            "lote": self.spin_lote.value(),
            "cpu_workers": hilos_cpu,
        }

        self._worker = PrediccionWorker(
            idx,
            self._imagen_original,
            self._profile_original,
            self._modelo_ruta,
            self._if_dir,
            params,
        )

        self._worker.proceso_terminado.connect(self._on_prediccion_finished)
        self._worker.finished.connect(self._limpiar_worker)
        self._worker.progress.connect(self._on_prediccion_progress)
        self._worker.log.connect(self._on_prediccion_log)

        if self._progreso:
            self._progreso.btn_cancelar.clicked.connect(self._cancelar_prediccion)

        self._worker.start()

    # ------------------------------------------------------------------
    # Callbacks del hilo
    # ------------------------------------------------------------------

    def _on_prediccion_progress(self, pct: int, msg: str) -> None:
        if self._progreso and not self._progreso._finalizado_flag:
            self._progreso.actualizar_global(pct, msg)

    def _on_prediccion_log(self, nivel: str, mensaje: str) -> None:
        if self._progreso:
            if nivel == "info":
                self._progreso.log_info(mensaje)
            elif nivel == "warning":
                self._progreso.log_warning(mensaje)
            elif nivel == "error":
                self._progreso.log_error(mensaje)

    def _on_prediccion_finished(self, exito: bool, mensaje: str) -> None:
        if exito and self._worker and self._worker.prediccion_result is not None:
            self._imagen_prediccion = self._worker.prediccion_result
            if self._imagen_prediccion is not None:
                try:
                    self.visor_prediccion.mostrar_imagen(self._imagen_prediccion, colormap=True)
                    self.visor_prediccion.repaint()
                    self.visor_prediccion.update()
                except Exception as e:
                    logger.error(f"Error pintando imagen final: {e}")

        if self._progreso:
            self._progreso.finalizar(exito, mensaje)

    def _limpiar_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _cancelar_prediccion(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            if not self._worker.wait(3000):
                self._worker.terminate()
                self._worker.wait()
            if self._progreso:
                self._progreso.finalizar(False, "Predicción abortada manual.")

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_hoja_estilos(self) -> None:
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