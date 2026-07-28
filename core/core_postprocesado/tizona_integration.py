# -*- coding: utf-8 -*-
"""
Utilidades de integración con el plugin Tizona para Colada
===========================================================

Permite localizar automáticamente los stacks IA generados por Tizona
dentro de su estructura de carpetas estándar.

Tizona guarda los stacks en la subcarpeta definida en config (por defecto '04_IA_STACKS').
Esta integración facilita la carga de stacks para entrenamiento y predicción sin
que el usuario tenga que navegar manualmente.
"""

import os
from typing import List, Dict, Optional

from ...config import CARPETA_STACKS
from ...utils.logging import get_logger

logger = get_logger('Colada.tizona_integration')

# Tizona guarda los stacks en la subcarpeta definida en config (por defecto '04_IA_STACKS')
_TIZONA_STACKS_SUBDIR = CARPETA_STACKS


def buscar_carpeta_tizona(ruta_base: str) -> List[str]:
    """
    Busca recursivamente en ruta_base todas las subcarpetas que contienen
    la carpeta de stacks (normalmente '04_IA_STACKS').

    Args:
        ruta_base: Ruta base desde la que empezar la búsqueda.

    Returns:
        Lista de rutas absolutas a los directorios de stacks encontrados.
    """
    stack_dirs = []
    if not os.path.isdir(ruta_base):
        logger.warning(f"La ruta base no existe: {ruta_base}")
        return stack_dirs

    for raiz, dirs, _ in os.walk(ruta_base):
        if os.path.basename(raiz) == _TIZONA_STACKS_SUBDIR:
            stack_dirs.append(raiz)
            logger.debug(f"Directorio de stacks encontrado: {raiz}")

    return stack_dirs


def recolectar_stacks(ruta_base: str) -> List[str]:
    """
    Devuelve una lista de rutas a todos los archivos GeoTIFF encontrados
    dentro de cualquier subcarpeta de stacks que cuelgue de ruta_base.

    Args:
        ruta_base: Ruta base para buscar.

    Returns:
        Lista de rutas absolutas a archivos .tif dentro de las carpetas de stacks.
    """
    stacks = []
    for carpeta_stacks in buscar_carpeta_tizona(ruta_base):
        for f in os.listdir(carpeta_stacks):
            if f.lower().endswith('.tif'):
                ruta_completa = os.path.join(carpeta_stacks, f)
                stacks.append(ruta_completa)
                logger.debug(f"Stack encontrado: {ruta_completa}")
    return stacks


def recolectar_stacks_por_tesela(ruta_base: str) -> Dict[str, str]:
    """
    Busca las subcarpetas de salida de Tizona (las teselas) y devuelve un
    diccionario {nombre_tesela: ruta_al_stack}. Útil para la predicción.

    Se asume que la estructura es:
        ruta_base/
            nombre_tesela/
                04_IA_STACKS/
                    nombre_tesela_STACK_5B.tif (u otro .tif)

    Args:
        ruta_base: Ruta base que contiene las carpetas de teselas.

    Returns:
        Diccionario con nombre de tesela como clave y ruta al stack como valor.
    """
    resultado: Dict[str, str] = {}
    if not os.path.isdir(ruta_base):
        logger.warning(f"La ruta base no existe: {ruta_base}")
        return resultado

    for item in os.listdir(ruta_base):
        ruta_tesela = os.path.join(ruta_base, item)
        if not os.path.isdir(ruta_tesela):
            continue

        ruta_stacks = os.path.join(ruta_tesela, _TIZONA_STACKS_SUBDIR)
        if not os.path.isdir(ruta_stacks):
            continue

        # Buscar archivos .tif en la carpeta de stacks
        tifs = [f for f in os.listdir(ruta_stacks) if f.lower().endswith('.tif')]
        if not tifs:
            continue

        # Preferir el que tenga "STACK" en el nombre, o tomar el primero
        stack_path = None
        for tif in tifs:
            if 'STACK' in tif.upper():
                stack_path = os.path.join(ruta_stacks, tif)
                break
        if stack_path is None:
            stack_path = os.path.join(ruta_stacks, tifs[0])

        resultado[item] = stack_path
        logger.debug(f"Tesela '{item}' asociada a stack: {stack_path}")

    logger.info(f"Se encontraron {len(resultado)} stacks en la estructura Tizona")
    return resultado