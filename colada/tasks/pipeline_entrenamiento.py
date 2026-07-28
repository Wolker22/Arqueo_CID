# -*- coding: utf-8 -*-
"""
Tarea de entrenamiento del VAE para COLADA
==========================================

Ejecuta el entrenamiento del Autoencoder Variacional en segundo plano
sin bloquear la interfaz de QGIS. Soporta cancelación y reporte de
progreso detallado (percentiles, dataloader, épocas, batches).

Centraliza textos, mensajes y parámetros en config.py.
"""

import os
import threading
import torch
from typing import Dict, Any, List, Optional, Callable

from qgis.core import QgsTask, Qgis, QgsApplication
from qgis.utils import iface

from ...utils.logging import get_logger
from ...core.core_postprocesado.entrenador import entrenar_vae
from ...config import (
    VAE_IN_CHANNELS,
    VAE_LATENT_DIM,
    VAE_FEATURES,
    EPOCAS,
    BATCH_SIZE,
    LEARNING_RATE,
    K_TRIM,
    KL_WEIGHT,
    USAR_GPU,
    VAL_SPLIT,
    PATIENCE,
    SEED,
    PATHS_PER_EPOCH,
    NUM_WORKERS_DATALOADER,
    ENTRENAMIENTO_MENSAJE_PREPARACION,
    ENTRENAMIENTO_MENSAJE_EPOCA,
    ENTRENAMIENTO_MENSAJE_PREPARACION_INICIANDO,
    ENTRENAMIENTO_MENSAJE_PREPARACION_COMPLETADO,
    ENTRENAMIENTO_MENSAJE_MODELO_GUARDADO,
    ENTRENAMIENTO_MENSAJE_CANCELADO,
    ENTRENAMIENTO_MENSAJE_ERROR,
    ENTRENAMIENTO_PROGRESO_PREPARACION_MAX,
    ENTRENAMIENTO_PROGRESO_ENTRENAMIENTO_INICIO,
    ENTRENAMIENTO_FORMATO_MENSAJE_EPOCA,
    ENTRENAMIENTO_FORMATO_PROGRESO_GLOBAL,
)

logger = get_logger('Colada.tasks.entrenamiento')


class TareaEntrenamiento(QgsTask):
    """
    Tarea QGIS para entrenar el VAE de Colada en segundo plano con desglose detallado.

    Attributes:
        archivos: Lista de rutas a los stacks de entrenamiento.
        ruta_salida: Ruta donde guardar el modelo entrenado (.pth).
        config: Diccionario con la configuración del entrenamiento.
        dialog: Diálogo de progreso (ProgresoCOLADA).
        params_modelo: Parámetros de arquitectura del VAE.
        hiperparams: Hiperparámetros de entrenamiento.
        dispositivo: 'cpu' o 'cuda'.
        cancel_event: Evento para cancelar el entrenamiento.
    """

    def __init__(
        self,
        archivos_entrenamiento: List[str],
        ruta_salida_modelo: str,
        config_entrenamiento: Dict[str, Any],
        progress_dialog: Optional[Any] = None,
    ) -> None:
        """
        Args:
            archivos_entrenamiento: Lista de rutas a stacks GeoTIFF.
            ruta_salida_modelo: Ruta para guardar el modelo .pth.
            config_entrenamiento: Diccionario con configuración completa.
            progress_dialog: Diálogo de progreso (ProgresoCOLADA).
        """
        super().__init__("COLADA - Entrenamiento", QgsTask.CanCancel)
        self.archivos: List[str] = archivos_entrenamiento
        self.ruta_salida: str = ruta_salida_modelo
        self.config: Dict[str, Any] = config_entrenamiento
        self.dialog: Optional[Any] = progress_dialog

        # Parámetros del modelo
        self.params_modelo: Dict[str, Any] = {
            "in_channels": self.config.get("in_channels", VAE_IN_CHANNELS),
            "latent_dim": self.config.get("latent_dim", VAE_LATENT_DIM),
            "features": self.config.get("features", VAE_FEATURES),
            "tamanio_parche": self.config.get("tamanio_parche", 256),
        }

        # Hiperparámetros
        self.hiperparams: Dict[str, Any] = {
            "epocas": self.config.get("epocas", EPOCAS),
            "batch_size": self.config.get("batch_size", BATCH_SIZE),
            "learning_rate": self.config.get("learning_rate", LEARNING_RATE),
            "k_trim": self.config.get("k_trim", K_TRIM),
            "kl_weight": self.config.get("kl_weight", KL_WEIGHT),
            "val_split": self.config.get("val_split", VAL_SPLIT),
            "patience": self.config.get("patience", PATIENCE),
            "patches_per_epoch": self.config.get("patches_per_epoch", PATHS_PER_EPOCH),
            "seed": self.config.get("seed", SEED),
            "num_workers": self.config.get("num_workers", NUM_WORKERS_DATALOADER),
            "loss_function": self.config.get("loss_function", "ssim"),
        }

        self.dispositivo: str = self.config.get(
            "dispositivo",
            "cuda" if USAR_GPU and torch.cuda.is_available() else "cpu",
        )
        self.cancel_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------
    # Método principal de la tarea
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """
        Ejecuta el entrenamiento con callbacks de progreso.

        Returns:
            True si el entrenamiento se completó con éxito, False en caso contrario.
        """
        self.log_info(f"Iniciando entrenamiento con {len(self.archivos)} archivo(s).")

        # Filtrar archivos existentes
        archivos_validos = [f for f in self.archivos if os.path.exists(f)]
        if not archivos_validos:
            self.log_error("Ningún archivo de entrenamiento existe.")
            return False

        if len(archivos_validos) != len(self.archivos):
            self.log_warning(
                f"{len(self.archivos) - len(archivos_validos)} archivos no encontrados y serán ignorados."
            )

        # Optimizaciones para GPU
        if self.dispositivo == "cuda":
            torch.backends.cudnn.benchmark = True

        # Identificadores para filas fijas en el diálogo de progreso
        FILA_PERCENTILES = "1. Cálculo de Percentiles Globales"
        FILA_DATALOADER = "2. Configuración de Tensores y Datos"

        # ------------------------------------------------------------------
        # Callback de preparación (percentiles y dataloader)
        # ------------------------------------------------------------------
        def preparacion_callback(msg: str, pct: int) -> None:
            """Actualiza la UI durante la fase de preparación."""
            self.log_info(msg)
            if self.dialog:
                # La fase de preparación ocupa el primer 15% de la barra global
                pct_global = int(pct * (15 / 85))
                self.dialog.actualizar_global(pct_global, f"Preparando: {msg}")

                if "Percentiles" in msg:
                    pct_sub = min(100, int((pct / 50) * 100))
                    self.dialog.actualizar_fila(FILA_PERCENTILES, msg, pct_sub, 0.0)
                else:
                    self.dialog.actualizar_fila(FILA_PERCENTILES, "Completado", 100, 0.0)
                    pct_sub = min(100, int(((pct - 55) / 30) * 100))
                    self.dialog.actualizar_fila(FILA_DATALOADER, msg, pct_sub, 0.0)

        # ------------------------------------------------------------------
        # Callback por batch (actualización dentro de cada época)
        # ------------------------------------------------------------------
        def batch_callback(epoca: int, batch_actual: int, total_batches: int, loss: float) -> None:
            """Actualiza la UI durante el procesamiento de batches."""
            total_epocas = self.hiperparams.get("epocas", EPOCAS)

            if total_epocas > 0 and total_batches > 0:
                # Progreso global: 15% + 85% * (época_completa + fracción de época actual)
                pct_global = 15 + int(((epoca - 1) / total_epocas) * 85)
                pct_global += int((batch_actual / total_batches) * (85 / total_epocas))
                pct_lote = int((batch_actual / total_batches) * 100)
            else:
                pct_global, pct_lote = 15, 0

            pct_global = min(100, max(0, pct_global))
            txt_global = f"Entrenando: Época {epoca}/{total_epocas} ({batch_actual}/{total_batches} lotes)"

            # Fila dinámica para la época actual
            fila_epoca_dinamica = f"3. Época {epoca}/{total_epocas}"

            if self.dialog:
                self.dialog.actualizar_fila(FILA_PERCENTILES, "Completado", 100, 0.0)
                self.dialog.actualizar_fila(FILA_DATALOADER, "Completado", 100, 0.0)
                self.dialog.actualizar_global(pct_global, txt_global)
                self.dialog.actualizar_fila(
                    fila_epoca_dinamica,
                    f"Procesando lotes: {batch_actual}/{total_batches}",
                    pct_lote,
                    loss,
                )

        # ------------------------------------------------------------------
        # Callback al final de cada época (validación)
        # ------------------------------------------------------------------
        def progress_callback(epoca_actual: int, total_epocas: int, train_loss: float, val_loss: float) -> None:
            """Actualiza la UI al completar una época."""
            if total_epocas > 0:
                pct_global = 15 + int((epoca_actual / total_epocas) * 85)
            else:
                pct_global = 15

            mensaje_log = ENTRENAMIENTO_FORMATO_MENSAJE_EPOCA.format(
                epoca_actual, total_epocas, train_loss, val_loss
            )
            self.log_info(mensaje_log)

            fila_epoca_dinamica = f"3. Época {epoca_actual}/{total_epocas}"

            if self.dialog:
                self.dialog.actualizar_global(pct_global, f"Época {epoca_actual}/{total_epocas} evaluada.")
                self.dialog.actualizar_fila(
                    fila_epoca_dinamica,
                    f"Completada (Train Loss: {train_loss:.4f})",
                    100,
                    val_loss,
                )

        # ------------------------------------------------------------------
        # Inicializar diálogo de progreso
        # ------------------------------------------------------------------
        if self.dialog:
            self.dialog.actualizar_global(0, "Inicializando canal de entrenamiento...")
            self.dialog.actualizar_fila(FILA_PERCENTILES, "En espera...", 0, 0.0)
            self.dialog.actualizar_fila(FILA_DATALOADER, "En espera...", 0, 0.0)

        # ------------------------------------------------------------------
        # Ejecutar entrenamiento
        # ------------------------------------------------------------------
        try:
            resultado = entrenar_vae(
                lista_archivos=archivos_validos,
                params_modelo=self.params_modelo,
                hiperparams=self.hiperparams,
                ruta_salida=self.ruta_salida,
                dispositivo=self.dispositivo,
                callback_progreso=progress_callback,
                callback_preparacion=preparacion_callback,
                callback_batch=batch_callback,
                cancel_event=self.cancel_event,
                seed=self.hiperparams.get("seed", SEED),
            )
        except Exception as e:
            self.log_error(f"Error inesperado en el bucle de optimización: {e}")
            return False

        if not resultado:
            self.log_error("El entrenamiento fue interrumpido o falló.")
            return False

        self.log_info("Entrenamiento completado.")
        if self.dialog:
            self.dialog.actualizar_global(100, ENTRENAMIENTO_MENSAJE_MODELO_GUARDADO)
        return True

    # ------------------------------------------------------------------
    # Métodos auxiliares de logging
    # ------------------------------------------------------------------

    def log_info(self, msg: str) -> None:
        """Registra un mensaje de nivel INFO."""
        if self.dialog:
            self.dialog.log_info(msg)
        logger.info(msg)

    def log_warning(self, msg: str) -> None:
        """Registra un mensaje de nivel WARNING."""
        if self.dialog:
            self.dialog.log_warning(msg)
        logger.warning(msg)

    def log_error(self, msg: str) -> None:
        """Registra un mensaje de nivel ERROR."""
        if self.dialog:
            self.dialog.log_error(msg)
        logger.error(msg)

    # ------------------------------------------------------------------
    # Cancelación
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Solicita la cancelación de la tarea."""
        self.cancel_event.set()
        super().cancel()

    # ------------------------------------------------------------------
    # Finalización
    # ------------------------------------------------------------------

    def finished(self, result: bool) -> None:
        """Maneja la finalización de la tarea (éxito, cancelación o error)."""
        if self.isCanceled():
            iface.messageBar().pushMessage(
                "COLADA", ENTRENAMIENTO_MENSAJE_CANCELADO, level=Qgis.Warning
            )
            if self.dialog:
                self.dialog.finalizar(False, ENTRENAMIENTO_MENSAJE_CANCELADO)
        elif result:
            iface.messageBar().pushMessage(
                "COLADA", ENTRENAMIENTO_MENSAJE_MODELO_GUARDADO, level=Qgis.Success
            )
            if self.dialog:
                self.dialog.finalizar(True, ENTRENAMIENTO_MENSAJE_MODELO_GUARDADO)
        else:
            iface.messageBar().pushMessage(
                "COLADA", ENTRENAMIENTO_MENSAJE_ERROR, level=Qgis.Critical
            )
            if self.dialog:
                self.dialog.finalizar(False, ENTRENAMIENTO_MENSAJE_ERROR)


# ------------------------------------------------------------------
# Función de lanzamiento
# ------------------------------------------------------------------

def lanzar_entrenamiento(
    archivos: List[str],
    ruta_modelo: str,
    config: Dict[str, Any],
    dialog: Optional[Any],
) -> TareaEntrenamiento:
    """
    Crea y agrega la tarea de entrenamiento al administrador de QGIS.

    Args:
        archivos: Lista de rutas a stacks de entrenamiento.
        ruta_modelo: Ruta donde guardar el modelo.
        config: Configuración del entrenamiento.
        dialog: Diálogo de progreso.

    Returns:
        Instancia de TareaEntrenamiento.
    """
    tarea = TareaEntrenamiento(archivos, ruta_modelo, config, dialog)
    QgsApplication.taskManager().addTask(tarea)
    return tarea