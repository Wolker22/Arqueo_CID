# -*- coding: utf-8 -*-
"""
Gestión de perfiles de configuración para Arqueo-CID
====================================================

Permite guardar y cargar configuraciones completas (parámetros de Tizona y Colada)
en archivos JSON, tanto a nivel de usuario como de sistema (solo lectura).

Las rutas de los directorios de perfiles se obtienen de `config.py`.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union

from qgis.PyQt.QtWidgets import QFileDialog
from qgis.utils import iface

from .logging import get_logger
from ..config import PERFILES_SISTEMA, PERFILES_USUARIO

logger = get_logger('ArqueoCid.perfil')

# Cache de perfiles de sistema por tipo ('tizona', 'colada')
_SYSTEM_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _cargar_json_perfil(ruta: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Carga un archivo JSON y devuelve su contenido como diccionario.
    Si el archivo no contiene la clave 'nombre', se añade a partir del nombre del archivo.

    Args:
        ruta: Ruta al archivo JSON.

    Returns:
        Diccionario con los datos, o None si hay error.
    """
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        if not isinstance(datos, dict):
            logger.warning(f"Archivo {os.path.basename(ruta)} no es un diccionario JSON")
            return None
        if 'nombre' not in datos:
            datos['nombre'] = os.path.splitext(os.path.basename(ruta))[0]
        return datos
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error cargando {os.path.basename(ruta)}: {e}")
        return None


def _cargar_perfiles_sistema(tipo: str) -> Dict[str, Dict[str, Any]]:
    """
    Carga todos los perfiles de sistema de un tipo dado (tizona/colada)
    desde el directorio correspondiente.

    Args:
        tipo: 'tizona' o 'colada'.

    Returns:
        Diccionario {nombre_perfil: datos_del_perfil}.
    """
    directorio = PERFILES_SISTEMA.get(tipo)
    if not directorio or not os.path.isdir(directorio):
        logger.warning(f"Directorio de perfiles de sistema no encontrado: {directorio}")
        return {}

    perfiles = {}
    try:
        for archivo in sorted(os.listdir(directorio)):
            if not archivo.endswith('.json'):
                continue
            ruta = os.path.join(directorio, archivo)
            if not os.path.isfile(ruta):
                continue
            datos = _cargar_json_perfil(ruta)
            if datos and 'nombre' in datos:
                perfiles[datos['nombre']] = datos
                logger.debug(f"Perfil sistema '{tipo}' cargado: {datos['nombre']}")
    except OSError as e:
        logger.error(f"Error leyendo {directorio}: {e}")
    return perfiles


def obtener_perfiles_sistema(tipo: str) -> Dict[str, Dict[str, Any]]:
    """
    Obtiene los perfiles de sistema de un tipo, usando caché.

    Args:
        tipo: 'tizona' o 'colada'.

    Returns:
        Diccionario {nombre: datos}.
    """
    if tipo not in _SYSTEM_PROFILES:
        _SYSTEM_PROFILES[tipo] = _cargar_perfiles_sistema(tipo)
    return _SYSTEM_PROFILES[tipo]


def recargar_perfiles_sistema(tipo: str) -> Dict[str, Dict[str, Any]]:
    """
    Fuerza la recarga de los perfiles de sistema de un tipo.

    Args:
        tipo: 'tizona' o 'colada'.

    Returns:
        Diccionario {nombre: datos} actualizado.
    """
    _SYSTEM_PROFILES[tipo] = _cargar_perfiles_sistema(tipo)
    return _SYSTEM_PROFILES[tipo]


# Compatibilidad con el código existente (Tizona usa PERFILES_PLUGIN)
PERFILES_PLUGIN = obtener_perfiles_sistema('tizona')


def recargar_perfiles_plugin() -> Dict[str, Dict[str, Any]]:
    """Recarga los perfiles de Tizona (compatibilidad)."""
    return recargar_perfiles_sistema('tizona')


def _sanitizar_nombre(nombre: str) -> str:
    """
    Elimina caracteres no válidos para nombres de archivo.

    Args:
        nombre: Nombre original.

    Returns:
        Nombre saneado.
    """
    return re.sub(r'[\\/*?:"<>|]', "", nombre).strip()


def guardar_perfil(nombre: str, params: Dict[str, Any]) -> str:
    """
    Guarda un perfil de usuario en el directorio correspondiente (Tizona por defecto).

    Args:
        nombre: Nombre del perfil (se usará como base del archivo).
        params: Diccionario con los parámetros a guardar.

    Returns:
        Ruta absoluta del archivo guardado.

    Raises:
        OSError: Si no se puede escribir en el directorio.
    """
    nombre_sanitizado = _sanitizar_nombre(nombre) or "Perfil_Sin_Nombre"
    datos = dict(params)
    datos['nombre'] = nombre
    ruta = os.path.join(PERFILES_USUARIO['tizona'], f"{nombre_sanitizado}.json")
    os.makedirs(PERFILES_USUARIO['tizona'], exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False, sort_keys=True)
    logger.info(f"Perfil de usuario guardado: {nombre} en {ruta}")
    return ruta


def cargar_perfil(ruta: str) -> Dict[str, Any]:
    """
    Carga un perfil desde un archivo JSON.

    Args:
        ruta: Ruta al archivo.

    Returns:
        Diccionario con los parámetros.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el JSON es inválido.
    """
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"Archivo no encontrado: {ruta}")
    datos = _cargar_json_perfil(ruta)
    if datos is None:
        raise ValueError(f"JSON inválido: {ruta}")
    return datos


def listar_perfiles() -> List[Tuple[str, Optional[str]]]:
    """
    Lista todos los perfiles disponibles (sistema y usuario) para Tizona.

    Returns:
        Lista de tuplas (nombre_perfil, ruta_del_archivo_usuario_o_None).
        Los perfiles de sistema tienen ruta None.
    """
    perfiles: List[Tuple[str, Optional[str]]] = []

    # Perfiles de sistema
    for nombre in obtener_perfiles_sistema('tizona'):
        perfiles.append((nombre, None))

    # Perfiles de usuario
    try:
        for archivo in sorted(os.listdir(PERFILES_USUARIO['tizona'])):
            if not archivo.endswith('.json'):
                continue
            nombre = archivo[:-5]  # quitar extensión
            ruta = os.path.join(PERFILES_USUARIO['tizona'], archivo)
            # Evitar duplicados si un perfil de usuario tiene el mismo nombre que uno de sistema
            if nombre not in obtener_perfiles_sistema('tizona'):
                perfiles.append((nombre, ruta))
    except OSError as e:
        logger.error(f"Error leyendo perfiles de usuario: {e}")

    perfiles.sort(key=lambda x: (0 if x[1] is None else 1, x[0].lower()))
    return perfiles


def obtener_perfil_por_nombre(nombre: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un perfil por su nombre, buscando primero en sistema y luego en usuario.

    Args:
        nombre: Nombre del perfil.

    Returns:
        Diccionario con los parámetros, o None si no existe.
    """
    # Buscar en sistema
    if nombre in obtener_perfiles_sistema('tizona'):
        return obtener_perfiles_sistema('tizona')[nombre]

    # Buscar en usuario
    for n, ruta in listar_perfiles():
        if n == nombre and ruta is not None:
            try:
                return cargar_perfil(ruta)
            except Exception as e:
                logger.error(f"Error cargando perfil de usuario {nombre}: {e}")
                return None
    return None


def eliminar_perfil(nombre: str) -> bool:
    """
    Elimina un perfil de usuario (no se pueden eliminar los de sistema).

    Args:
        nombre: Nombre del perfil a eliminar.

    Returns:
        True si se eliminó correctamente, False en caso contrario.

    Raises:
        PermissionError: Si se intenta eliminar un perfil de sistema.
    """
    if nombre in obtener_perfiles_sistema('tizona'):
        raise PermissionError("No se pueden eliminar perfiles del sistema.")

    ruta = os.path.join(PERFILES_USUARIO['tizona'], f"{nombre}.json")
    if os.path.exists(ruta):
        try:
            os.remove(ruta)
            logger.info(f"Perfil eliminado: {nombre}")
            return True
        except OSError as e:
            logger.error(f"No se pudo eliminar {nombre}: {e}")
            return False
    return False


def seleccionar_guardar_perfil() -> str:
    """
    Abre un diálogo para seleccionar dónde guardar un perfil de usuario.

    Returns:
        Ruta seleccionada, o cadena vacía si se cancela.
    """
    ruta, _ = QFileDialog.getSaveFileName(
        iface.mainWindow() if iface else None,
        "Guardar Perfil de Tizona",
        os.path.join(PERFILES_USUARIO['tizona'], "Mi_Configuracion.json"),
        "Archivos JSON (*.json)"
    )
    return ruta or ""


def seleccionar_cargar_perfil() -> str:
    """
    Abre un diálogo para seleccionar un archivo de perfil desde el sistema de archivos.

    Returns:
        Ruta seleccionada, o cadena vacía si se cancela.
    """
    ruta, _ = QFileDialog.getOpenFileName(
        iface.mainWindow() if iface else None,
        "Importar Perfil de Tizona",
        PERFILES_USUARIO['tizona'],
        "Archivos JSON (*.json)"
    )
    return ruta or ""