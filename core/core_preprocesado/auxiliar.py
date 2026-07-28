# -*- coding: utf-8 -*-
"""
Utilidades auxiliares y funciones trabajadoras para el pipeline de Tizona.

Contiene funciones de bajo nivel para:
- Procesamiento de teselas LiDAR (worker para hilos/procesos)
- Eliminación robusta de directorios (con reintentos ante bloqueos)
- Verificación de espacio en disco antes de operaciones críticas
- Consulta de memoria RAM disponible
- Creación de estructura de directorios de salida (usa constantes de config.py)

Todas las funciones están diseñadas para ser seguras en entornos
multihilo y para fallar gracefulmente, registrando errores sin detener
el flujo principal del plugin.
"""

import os
import gc
import time
import shutil
from dataclasses import fields
from typing import List, Tuple, Optional, Callable, Dict, Any

from ...config import (
    CARPETA_MDT, CARPETA_DERIVADOS, CARPETA_IMAGENES, CARPETA_STACKS
)
from ...utils.processing_config import ConfiguracionProcesamiento
from .procesador_lidar import ProcesadorLiDAR
from ...utils.logging import get_logger

logger = get_logger('Tizona.auxiliar')


# ---------------------------------------------------------------------------
# Worker de procesamiento de teselas
# ---------------------------------------------------------------------------

def procesar_tesela_worker(
    ruta_laz: str,
    nombre_base: str,
    carpeta_salida: str,
    params: Dict[str, Any],
    cancel_callback: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[bool, str, float]:
    """
    Procesa una única tesela LiDAR de principio a fin.

    Diseñada para ejecutarse en un hilo o proceso separado como parte
    del pipeline paralelo de procesamiento.

    Args:
        ruta_laz: Ruta completa al archivo LAZ de entrada.
        nombre_base: Nombre identificativo de la tesela (sin extensión).
        carpeta_salida: Directorio donde se generarán los resultados.
        params: Diccionario con los parámetros de procesamiento.
                Se filtran automáticamente para quedarse solo con las claves
                que acepta ConfiguracionProcesamiento.
        cancel_callback: Función opcional que retorna True si se debe cancelar.
        progress_callback: Función opcional para reportar progreso.

    Returns:
        Tupla (éxito, mensaje, duración_en_segundos).
    """
    inicio = time.time()

    try:
        # ── Filtrar parámetros válidos para la dataclass ──────────────
        campos_validos = {f.name for f in fields(ConfiguracionProcesamiento)}
        params_proc = {k: v for k, v in params.items() if k in campos_validos}

        config = ConfiguracionProcesamiento(**params_proc)

        # ── Procesador LiDAR ─────────────────────────────────────────
        proc = ProcesadorLiDAR(
            ruta_laz=ruta_laz,
            carpeta_salida=carpeta_salida,
            config=config,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback
        )

        proc.ejecutar_pipeline_completo()

        duracion = time.time() - inicio
        logger.info(f"Tesela '{nombre_base}' procesada correctamente en {duracion:.1f}s")
        return True, nombre_base, duracion

    except Exception as e:
        logger.error(f"Error procesando '{nombre_base}': {e}", exc_info=True)
        return False, f"{nombre_base}: {e}", 0.0


# ---------------------------------------------------------------------------
# Eliminación robusta de directorios
# ---------------------------------------------------------------------------

def rmtree_robusto(
    ruta: str,
    max_intentos: int = 8,
    espera: float = 2.0
) -> None:
    """
    Elimina un directorio de forma recursiva con reintentos ante errores.

    En Windows, es común que archivos/directorios estén bloqueados temporalmente
    por procesos del sistema (antivirus, indexación, handles abiertos).
    Esta función reintenta la eliminación varias veces con pausas entre intentos.

    Args:
        ruta: Ruta al directorio a eliminar.
        max_intentos: Número máximo de reintentos antes de rendirse.
        espera: Segundos de espera entre reintentos.
    """
    if not os.path.exists(ruta):
        return

    for intento in range(max_intentos):
        try:
            gc.collect()
            time.sleep(0.5)
            shutil.rmtree(ruta)
            logger.debug(f"Directorio eliminado correctamente: {ruta}")
            return
        except (PermissionError, OSError) as e:
            gc.collect()
            if intento < max_intentos - 1:
                logger.warning(
                    f"Permiso denegado al eliminar {ruta}, "
                    f"reintentando en {espera}s... "
                    f"(intento {intento + 1}/{max_intentos}): {e}"
                )
                time.sleep(espera)
            else:
                logger.error(
                    f"No se pudo eliminar {ruta} tras {max_intentos} intentos. "
                    f"Último error: {e}"
                )
        except Exception as e:
            logger.error(f"Error inesperado al eliminar {ruta}: {e}")
            break


# ---------------------------------------------------------------------------
# Verificación de espacio en disco
# ---------------------------------------------------------------------------

def verificar_espacio_disco(
    rutas: List[str],
    margen_mb: int = 1024
) -> Tuple[bool, str]:
    """
    Verifica que haya suficiente espacio libre en las rutas especificadas.

    Args:
        rutas: Lista de directorios a verificar.
        margen_mb: Espacio libre mínimo requerido en megabytes.

    Returns:
        Tupla (suficiente, mensaje). Si no hay suficiente, el mensaje describe el problema.
    """
    for ruta in rutas:
        try:
            os.makedirs(ruta, exist_ok=True)
        except OSError as e:
            return False, f"No se pudo crear el directorio {ruta}: {e}"

        try:
            uso = shutil.disk_usage(ruta)
            libre_mb = uso.free / (1024 * 1024)
        except Exception as e:
            return False, f"No se pudo verificar el espacio en {ruta}: {e}"

        if libre_mb < margen_mb:
            return False, (
                f"Espacio insuficiente en {ruta}: "
                f"{libre_mb:.0f} MB libres "
                f"(se necesitan al menos {margen_mb} MB)."
            )

    return True, ""


# ---------------------------------------------------------------------------
# Consulta de memoria RAM disponible
# ---------------------------------------------------------------------------

def obtener_memoria_disponible_mb() -> float:
    """
    Consulta la memoria RAM disponible en el sistema.

    Returns:
        Memoria disponible en MB. Si no se puede determinar, devuelve float('inf').
    """
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except ImportError:
        logger.debug("psutil no instalado. No se puede verificar memoria disponible.")
        return float('inf')
    except Exception as e:
        logger.warning(f"No se pudo consultar la memoria disponible: {e}")
        return float('inf')


# ---------------------------------------------------------------------------
# Creación de estructura de directorios de salida
# ---------------------------------------------------------------------------

def crear_estructura_salida(carpeta_salida: str) -> Dict[str, str]:
    """
    Crea la estructura estándar de directorios para los resultados del pipeline.

    Las subcarpetas se definen en config.py (CARPETA_MDT, CARPETA_DERIVADOS, etc.)
    para garantizar coherencia con el resto del sistema.

    Args:
        carpeta_salida: Directorio raíz donde se creará la estructura.

    Returns:
        Diccionario con las rutas creadas.
    """
    carpetas = {
        'base': carpeta_salida,
        'mdt': os.path.join(carpeta_salida, CARPETA_MDT),
        'derivados': os.path.join(carpeta_salida, CARPETA_DERIVADOS),
        'png': os.path.join(carpeta_salida, CARPETA_IMAGENES),
        'stacks': os.path.join(carpeta_salida, CARPETA_STACKS),
    }

    for nombre, ruta in carpetas.items():
        if nombre != 'base':
            os.makedirs(ruta, exist_ok=True)
            logger.debug(f"Directorio de salida creado: {ruta}")

    return carpetas