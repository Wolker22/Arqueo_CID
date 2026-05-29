# -*- coding: utf-8 -*-
"""
Tarea QGIS que coordina la descarga y procesamiento en paralelo de teselas LiDAR.
(Arqueo-CID – Tizona)
==============================================================================

Incluye filtro de variante RGB/IRC/COL/CIR antes de cualquier descarga,
respetando la cobertura seleccionada (1ª, 2ª o 3ª).

Soporta cancelación, reporte de progreso y ejecución paralela.
"""

import os
import time
import threading
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import List, Dict, Any, Tuple, Optional, Callable

from qgis.core import QgsTask, Qgis, QgsApplication
from qgis.utils import iface

# Importar constantes desde la configuración central
from ...config import (
    DESCARGAS_SIMULTANEAS,
    MAX_PROCESOS_SIMULTANEOS,
    MAX_HILOS_TOTALES,
    MIN_MEMORIA_LIBRE_MB,
    ESPACIO_LIBRE_MINIMO_MB,
    TAMANO_MINIMO_LAZ_BYTES,
    MEMORIA_PAUSA_SEGUNDOS,
    ESPERA_ENTRE_COMPROBACIONES,
)
from ..core.descargador import DescargadorCNIG, archivo_coincide_tipo
from ...utils.logging import get_logger
from ..core.auxiliar import (
    procesar_tesela_worker,
    rmtree_robusto,
    verificar_espacio_disco,
    obtener_memoria_disponible_mb,
)

logger = get_logger('Tizona.tasks.pipeline')


class TareaPipeline(QgsTask):
    """
    Tarea de QGIS que coordina el pipeline completo de descarga y procesamiento.
    Soporta cancelación, reporte de progreso y ejecución paralela.

    Attributes:
        nombres: Lista de nombres de tesela.
        params: Parámetros de procesamiento.
        config: Configuración de descarga.
        progress_dialog: Diálogo de progreso (opcional).
        ruta_descarga: Carpeta donde se guardan los LAZ.
        ruta_procesados: Carpeta donde se generan resultados.
        total_archivos: Número total de archivos a procesar.
        descargados: Contador de descargas completadas.
        procesados: Contador de procesamientos completados.
        errores_descarga: Lista de errores de descarga.
        errores_proc: Lista de errores de procesamiento.
        tiempos_teselas: Diccionario con duraciones por tesela.
        modo: Modo de ejecución ('Descargar y procesar', 'Solo descarga', 'Solo procesamiento').
        max_descargas: Número máximo de descargas simultáneas.
        max_procesos: Número máximo de procesamientos simultáneos.
        timeout_descarga: Timeout para cada descarga.
        cancel_event: Evento de cancelación.
        _executor_desc: Executor para descargas.
        _executor_proc: Executor para procesamientos.
        _futures_desc: Diccionario futuro → nombre de tesela (descarga).
        _futures_proc: Diccionario futuro → nombre de tesela (procesamiento).
        _archivos_pendientes: Cola de archivos pendientes de descarga.
    """

    def __init__(
        self,
        nombres: List[str],
        params_proc: Dict[str, Any],
        config: Dict[str, Any],
        progress_dialog: Optional[Any] = None,
    ) -> None:
        """
        Args:
            nombres: Lista de nombres de tesela (sin extensión).
            params_proc: Parámetros de procesamiento.
            config: Configuración de descarga (rutas, modo, etc.).
            progress_dialog: Diálogo de progreso (DialogoProgreso).
        """
        super().__init__("Tizona Pipeline", QgsTask.CanCancel)

        # ─── Datos de entrada ───
        self.nombres: List[str] = nombres
        self.params: Dict[str, Any] = params_proc
        self.config: Dict[str, Any] = config
        self.progress_dialog: Optional[Any] = progress_dialog

        # ─── Rutas de trabajo ───
        self.ruta_descarga: str = ""
        self.ruta_procesados: str = ""

        # ─── Contadores y estado ───
        self.total_archivos: int = len(nombres)
        self.descargados: int = 0
        self.procesados: int = 0

        # ─── Registro de errores ───
        self.errores_descarga: List[str] = []
        self.errores_proc: List[str] = []
        self.tiempos_teselas: Dict[str, float] = {}

        # ─── Configuración del modo de ejecución ───
        self.modo: str = config.get("modo_ejecucion", "Descargar y procesar")

        # ─── Configuración de paralelismo ───
        self.max_descargas: int = config.get("descargas_simultaneas", DESCARGAS_SIMULTANEAS)
        self.max_procesos: int = config.get("proc_paralelo", MAX_PROCESOS_SIMULTANEOS)

        # Si el usuario desactivó el procesamiento paralelo, forzamos a 1
        if not config.get("procesamiento_paralelo", True):
            self.max_procesos = 1

        # Limitamos el total de hilos para no saturar el sistema
        total_hilos = self.max_descargas + self.max_procesos
        if total_hilos > MAX_HILOS_TOTALES:
            self.max_procesos = max(1, MAX_HILOS_TOTALES - self.max_descargas)

        self.timeout_descarga: int = config.get("timeout_descarga", 120)
        self.cancel_event: threading.Event = threading.Event()

        # Ejecutores de hilos (se crean en run)
        self._executor_desc: Optional[ThreadPoolExecutor] = None
        self._executor_proc: Optional[ThreadPoolExecutor] = None
        self._futures_desc: Dict[Future, str] = {}
        self._futures_proc: Dict[Future, str] = {}
        self._archivos_pendientes: List[str] = []

    # -------------------------------------------------------------------
    # Configuración de rutas
    # -------------------------------------------------------------------

    def _establecer_rutas(self) -> None:
        """Define las rutas de descarga y procesamiento, creándolas si no existen."""
        base = QgsApplication.qgisSettingsDirPath()
        self.ruta_descarga = self.config.get(
            "ruta_descarga", os.path.join(base, "downloads", "tizona")
        )
        self.ruta_procesados = self.config.get(
            "ruta_procesados", os.path.join(base, "output", "tizona")
        )
        os.makedirs(self.ruta_descarga, exist_ok=True)
        os.makedirs(self.ruta_procesados, exist_ok=True)

    # -------------------------------------------------------------------
    # Descarga de un único archivo
    # -------------------------------------------------------------------

    def _descargar_uno(self, fichero: str) -> Tuple[str, str, bool, str]:
        """
        Descarga un archivo LAZ del CNIG.

        Args:
            fichero: Nombre de la tesela (con o sin extensión .laz).

        Returns:
            (nombre_base, ruta_archivo, éxito, mensaje)
        """
        d = DescargadorCNIG(timeout=self.timeout_descarga)
        nombre_con_ext = (
            fichero if fichero.lower().endswith(".laz") else fichero + ".laz"
        )
        tipo = self.config.get("tipo_producto", "Ambos")
        ruta, ok, msg = d.descargar_archivo(
            nombre_con_ext, self.ruta_descarga, tipo_producto=tipo
        )
        return Path(fichero).stem, ruta, ok, msg

    # -------------------------------------------------------------------
    # Logging y progreso
    # -------------------------------------------------------------------

    def _log(self, nivel: str, msg: str) -> None:
        """
        Envía un mensaje al diálogo de progreso y al logger.

        Args:
            nivel: 'info', 'error' o 'warning'.
            msg: Mensaje a registrar.
        """
        if self.progress_dialog:
            if nivel == "info":
                self.progress_dialog.log_info(msg)
            elif nivel == "error":
                self.progress_dialog.log_error(msg)
            elif nivel == "warning":
                self.progress_dialog.log_warning(msg)
        log_func = getattr(logger, nivel, logger.info)
        log_func(msg)

    def _actualizar_barra(self, tipo: str) -> None:
        """
        Actualiza la barra de descarga o procesamiento con el porcentaje global.

        Args:
            tipo: 'descarga' o 'proc'.
        """
        if not self.progress_dialog:
            return
        if tipo == "descarga":
            pct = int(self.descargados / self.total_archivos * 100) if self.total_archivos else 0
            self.progress_dialog.actualizar_barra_descarga(
                pct, f"Descarga: {self.descargados}/{self.total_archivos}"
            )
        elif tipo == "proc":
            pct = int(self.procesados / self.total_archivos * 100) if self.total_archivos else 0
            self.progress_dialog.actualizar_barra_procesamiento(
                pct, f"Procesamiento: {self.procesados}/{self.total_archivos}"
            )

    def _update_tile_status(self, nombre_base: str, estado: str, progreso: int = 0) -> None:
        """
        Actualiza el estado de una tesela en la tabla del diálogo.

        Args:
            nombre_base: Nombre de la tesela.
            estado: Texto de estado.
            progreso: Porcentaje (0-100).
        """
        if self.progress_dialog:
            self.progress_dialog.actualizar_estado_tesela(nombre_base, estado, progreso)

    def _crear_callback_progreso(self, nombre_base: str) -> Callable[[str, int, Optional[str]], None]:
        """
        Crea un callback que actualiza el estado de la tesela y la barra global.
        La barra global se calcula combinando el progreso de la tesela actual
        con las teselas ya completadas, ofreciendo un avance mucho más fino.

        Args:
            nombre_base: Nombre de la tesela.

        Returns:
            Función callback con firma (etapa, pct, msg).
        """
        def cb(etapa: str, pct: int, msg: Optional[str] = None) -> None:
            self._update_tile_status(nombre_base, f"{etapa} {pct}%", pct)
            # Actualizar barra global combinando el progreso de la tesela actual
            if self.total_archivos > 0:
                global_pct = int((self.procesados + pct / 100.0) / self.total_archivos * 100)
                if self.progress_dialog:
                    self.progress_dialog.actualizar_barra_procesamiento(
                        global_pct,
                        f"Procesamiento: {self.procesados}/{self.total_archivos} (actual {pct}%)",
                    )
        return cb

    # -------------------------------------------------------------------
    # Punto de entrada principal
    # -------------------------------------------------------------------

    def run(self) -> bool:
        """
        Ejecuta el pipeline completo según el modo de ejecución.

        Returns:
            True si al menos un archivo se descargó/procesó correctamente.
        """
        self._establecer_rutas()

        # Configurar visibilidad de las barras en el diálogo de progreso
        if self.progress_dialog:
            self.progress_dialog.configurar_barras(self.modo)

        # ─── FASE 1: Filtrado por tipo de producto ───
        tipo = self.config.get("tipo_producto", "Ambos")
        cobertura = self.config.get("cobertura", 1)  # 0=1ª, 1=2ª, 2=3ª

        if self.modo != "Solo procesamiento" and cobertura != 2 and tipo not in ("Ambos", "Todos"):
            nombres_filtrados = []
            for nombre in self.nombres:
                nombre_base_archivo = os.path.basename(nombre)
                nombre_check = (
                    nombre_base_archivo
                    if nombre_base_archivo.lower().endswith(".laz")
                    else nombre_base_archivo + ".laz"
                )
                if archivo_coincide_tipo(nombre_check, tipo):
                    nombres_filtrados.append(nombre)
                else:
                    self._log("info", f"Omitido por filtro {tipo}: {nombre}")
            self.nombres = nombres_filtrados

        nombres_finales = self.nombres
        self.total_archivos = len(nombres_finales)
        self._log("info", f"Iniciando pipeline con {self.total_archivos} archivo(s). Modo: {self.modo}")

        if self.total_archivos == 0:
            self._log(
                "error", f"No hay archivos que coincidan con el filtro '{tipo}'. Revisa la selección."
            )
            return False

        # ─── FASE 2: Verificación de espacio en disco ───
        rutas_a_verificar = []
        if self.modo != "Solo procesamiento":
            rutas_a_verificar.append(self.ruta_descarga)
        if self.modo != "Solo descarga":
            rutas_a_verificar.append(self.ruta_procesados)

        ok, err = verificar_espacio_disco(rutas_a_verificar, margen_mb=ESPACIO_LIBRE_MINIMO_MB)
        if not ok:
            self._log("error", err)
            return False

        # ─── FASE 3: Limpieza opcional de directorios ───
        if self.config.get("limpiar_descargas", False):
            rmtree_robusto(self.ruta_descarga)
            os.makedirs(self.ruta_descarga, exist_ok=True)
        if self.config.get("limpiar_procesados", False):
            rmtree_robusto(self.ruta_procesados)
            os.makedirs(self.ruta_procesados, exist_ok=True)

        # ─── FASE 4: Inicializar estado de todas las teselas ───
        for nombre in nombres_finales:
            self._update_tile_status(Path(nombre).stem, "Pendiente", 0)

        # ─── FASE 5: Ejecución según modo ───
        if self.modo == "Solo procesamiento":
            archivos = []
            for nombre in nombres_finales:
                fname = nombre if nombre.lower().endswith(".laz") else nombre + ".laz"
                ruta = os.path.join(self.ruta_descarga, fname)
                if os.path.exists(ruta) and os.path.getsize(ruta) > TAMANO_MINIMO_LAZ_BYTES:
                    archivos.append((ruta, Path(ruta).stem))
                else:
                    self.errores_descarga.append(f"{nombre}: no encontrado en local")
                    self._update_tile_status(Path(nombre).stem, "No encontrado", 0)
            if not archivos:
                self._log("error", "No se encontraron archivos LAZ locales válidos.")
                return False
            self.total_archivos = len(archivos)
            self._procesar_archivos_locales(archivos)
            return self.procesados > 0

        # Modo descarga (con o sin procesamiento posterior)
        self._archivos_pendientes = list(nombres_finales)
        hacer_procesamiento = self.modo == "Descargar y procesar"
        if not hacer_procesamiento:
            self.max_procesos = 0

        with ThreadPoolExecutor(max_workers=self.max_descargas) as desc_exec:
            self._executor_desc = desc_exec
            if hacer_procesamiento and self.max_procesos > 0:
                self._executor_proc = ThreadPoolExecutor(max_workers=self.max_procesos)

            # Lanzar las primeras descargas
            for _ in range(min(self.max_descargas, len(self._archivos_pendientes))):
                if self.cancel_event.is_set():
                    break
                fichero = self._archivos_pendientes.pop(0)
                fut = self._executor_desc.submit(self._descargar_uno, fichero)
                self._futures_desc[fut] = fichero

            try:
                while self._futures_desc or self._futures_proc:
                    if self.cancel_event.is_set():
                        self._cancelar_todo()
                        break
                    self._recoger_descargas_finalizadas(hacer_procesamiento)
                    if hacer_procesamiento:
                        self._recoger_procesos_finalizados()
                    if not self._futures_desc and not self._archivos_pendientes and not self._futures_proc:
                        break
                    time.sleep(ESPERA_ENTRE_COMPROBACIONES)
            finally:
                if self._executor_proc:
                    self._executor_proc.shutdown(wait=False, cancel_futures=True)

        if not hacer_procesamiento:
            return self.descargados > 0
        return self.procesados > 0

    # -------------------------------------------------------------------
    # Procesamiento local (modo Solo procesamiento)
    # -------------------------------------------------------------------

    def _procesar_archivos_locales(self, archivos: List[Tuple[str, str]]) -> None:
        """
        Procesa una lista de archivos locales en paralelo.

        Args:
            archivos: Lista de tuplas (ruta, nombre).
        """
        with ThreadPoolExecutor(max_workers=self.max_procesos) as executor:
            futuros = {}
            for ruta, nombre in archivos:
                if self.cancel_event.is_set():
                    break
                carpeta_salida = os.path.join(self.ruta_procesados, nombre)
                cb = self._crear_callback_progreso(nombre)
                futuros[
                    executor.submit(
                        procesar_tesela_worker,
                        ruta,
                        nombre,
                        carpeta_salida,
                        self.params,
                        cancel_callback=self.cancel_event.is_set,
                        progress_callback=cb,
                    )
                ] = nombre

            for future in as_completed(futuros):
                nombre = futuros[future]
                try:
                    ok, msg, dur = future.result()
                    if ok:
                        self.tiempos_teselas[nombre] = dur
                except Exception as e:
                    ok, msg, dur = False, str(e), 0.0
                self._finalizar_procesamiento(nombre, ok, msg, dur if ok else 0)

    # -------------------------------------------------------------------
    # Gestión de descargas
    # -------------------------------------------------------------------

    def _recoger_descargas_finalizadas(self, procesar: bool) -> None:
        """
        Recoge descargas terminadas y lanza nuevas si quedan pendientes.

        Args:
            procesar: Si es True, encola el procesamiento de la tesela descargada.
        """
        terminados = [f for f in self._futures_desc if f.done()]
        for future in terminados:
            fichero = self._futures_desc.pop(future)
            nombre_base = Path(fichero).stem
            try:
                nb, ruta, ok, msg = future.result(timeout=30)
            except Exception as e:
                nb, ruta, ok, msg = nombre_base, None, False, f"Excepción: {e}"

            self.descargados += 1
            self._actualizar_barra("descarga")

            if ok:
                self._log("info", f"✅ Descargado: {nb}")
                self._update_tile_status(nb, "Descargado", 100)
                if procesar:
                    self._encolar_procesamiento(nb, ruta)
            else:
                self._log("error", f"❌ Descarga {nb}: {msg}")
                self.errores_descarga.append(f"{nb}: {msg}")
                self._update_tile_status(nb, "Error descarga", 0)

            # Lanzar siguiente descarga si quedan pendientes
            if self._archivos_pendientes and not self.cancel_event.is_set():
                sig = self._archivos_pendientes.pop(0)
                fut = self._executor_desc.submit(self._descargar_uno, sig)
                self._futures_desc[fut] = sig

    def _encolar_procesamiento(self, nombre: str, ruta: str) -> None:
        """
        Verifica recursos y encola el procesamiento de una tesela descargada.

        Args:
            nombre: Nombre de la tesela.
            ruta: Ruta al archivo LAZ descargado.
        """
        if self.cancel_event.is_set():
            return

        # Verificar memoria disponible
        mem = obtener_memoria_disponible_mb()
        if mem < MIN_MEMORIA_LIBRE_MB:
            self._log(
                "warning", f"Memoria baja ({mem:.0f} MB), pausando {MEMORIA_PAUSA_SEGUNDOS}s para {nombre}"
            )
            time.sleep(MEMORIA_PAUSA_SEGUNDOS)

        # Verificar espacio en disco
        try:
            libre_mb = shutil.disk_usage(self.ruta_procesados).free / (1024 * 1024)
            if libre_mb < ESPACIO_LIBRE_MINIMO_MB:
                self._log(
                    "error",
                    f"Espacio insuficiente ({libre_mb:.0f} MB) para {nombre}. Se omite.",
                )
                self.errores_proc.append(
                    f"{nombre}: espacio insuficiente ({libre_mb:.0f} MB)"
                )
                self._update_tile_status(nombre, "Error espacio", 0)
                return
        except Exception as e:
            logger.warning(f"No se pudo verificar espacio para {nombre}: {e}")

        carpeta = os.path.join(self.ruta_procesados, nombre)
        cb = self._crear_callback_progreso(nombre)
        fut = self._executor_proc.submit(
            procesar_tesela_worker,
            ruta,
            nombre,
            carpeta,
            self.params,
            cancel_callback=self.cancel_event.is_set,
            progress_callback=cb,
        )
        self._futures_proc[fut] = nombre

    def _recoger_procesos_finalizados(self) -> None:
        """Recoge los procesamientos que han terminado."""
        if not self._executor_proc or not self._futures_proc:
            return
        terminados = [f for f in self._futures_proc if f.done()]
        for future in terminados:
            nombre = self._futures_proc.pop(future)
            try:
                ok, msg, dur = future.result(timeout=1)
                if ok:
                    self.tiempos_teselas[nombre] = dur
            except Exception as e:
                ok, msg = False, str(e)
            self._finalizar_procesamiento(nombre, ok, msg, dur if ok else 0)

    def _finalizar_procesamiento(
        self, nombre: str, exito: bool, mensaje: str, duracion: float
    ) -> None:
        """
        Registra el resultado final de una tesela.

        Args:
            nombre: Nombre de la tesela.
            exito: True si el procesamiento fue exitoso.
            mensaje: Mensaje asociado.
            duracion: Duración en segundos (si éxito).
        """
        if exito:
            self.procesados += 1
            self._actualizar_barra("proc")
            self._log("info", f"⚙️ Procesado: {nombre} ({duracion:.1f}s)")
            self._update_tile_status(nombre, "Completado", 100)
        else:
            self.errores_proc.append(f"{nombre}: {mensaje}")
            self._log("error", f"❌ Procesamiento {nombre}: {mensaje}")
            self._update_tile_status(nombre, "Error proc", 0)

    # -------------------------------------------------------------------
    # Cancelación
    # -------------------------------------------------------------------

    def _cancelar_todo(self) -> None:
        """Cancela todos los futuros de descarga y procesamiento."""
        self.cancel_event.set()
        for f in list(self._futures_desc.keys()):
            f.cancel()
        for f in list(self._futures_proc.keys()):
            f.cancel()
        self._futures_desc.clear()
        self._futures_proc.clear()

    def cancel(self) -> None:
        """Solicitud de cancelación por parte del usuario."""
        self.cancel_event.set()
        super().cancel()

    # -------------------------------------------------------------------
    # Finalización
    # -------------------------------------------------------------------

    def finished(self, result: bool) -> None:
        """
        Se ejecuta cuando la tarea termina (con éxito, error o cancelación).
        Muestra un resumen en la barra de mensajes de QGIS y finaliza el diálogo.

        Args:
            result: True si la tarea completó al menos una operación exitosa.
        """
        if self.isCanceled():
            iface.messageBar().pushMessage("Tizona", "Proceso cancelado.", level=Qgis.Warning)
            if self.progress_dialog:
                self.progress_dialog.finalizar(False, "Proceso cancelado.")
        elif result:
            resumen = (
                f"Completado: {self.descargados} descargas, {self.procesados} procesados."
            )
            iface.messageBar().pushMessage("Tizona", resumen, level=Qgis.Success)
            if self.progress_dialog:
                self.progress_dialog.finalizar(True, resumen)
        else:
            iface.messageBar().pushMessage(
                "Tizona", "No se procesó ni descargó ningún archivo.", level=Qgis.Warning
            )
            if self.progress_dialog:
                self.progress_dialog.finalizar(False, "Proceso detenido sin procesar.")