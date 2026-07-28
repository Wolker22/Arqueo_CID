# -*- coding: utf-8 -*-
"""
Módulo de filtros de imagen para COLADA (Arqueo-CID)
=====================================================

Proporciona funciones que aplican transformaciones a un array 2D (derivado),
devolviendo un nuevo array del mismo tamaño.

Filtros soportados: Sobel, Laplace, Gaussiano, Mediana, Canny.
"""

import numpy as np
from scipy import ndimage
from typing import Dict, Any

# Importar constantes desde la configuración central
from ...config import (
    FILTRO_GAUSSIAN_SIGMA_DEFAULT,
    FILTRO_MEDIAN_SIZE_DEFAULT,
    FILTRO_CANNY_SIGMA_DEFAULT,
    FILTRO_CANNY_LOW_DEFAULT,
    FILTRO_CANNY_HIGH_DEFAULT,
)
from ...utils.logging import get_logger

logger = get_logger('Colada.filtros_imagen')


def aplicar_filtro(arr: np.ndarray, tipo_filtro: str, params: Dict[str, Any]) -> np.ndarray:
    """
    Aplica el filtro especificado al array.

    Args:
        arr: Array 2D de entrada (float32 o float64). Se convertirá a float32 si es necesario.
        tipo_filtro: Nombre del filtro ('sobel', 'laplace', 'gaussian', 'median', 'canny').
        params: Diccionario con los parámetros del filtro (sigma, tamaño, etc.).

    Returns:
        Array 2D filtrado (float32).

    Raises:
        ValueError: Si el tipo de filtro no es reconocido.
    """
    # Asegurar que el array sea float32
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)

    tipo = tipo_filtro.lower()
    if tipo == "sobel":
        return sobel(arr)
    elif tipo == "laplace":
        return laplace(arr)
    elif tipo == "gaussian":
        sigma = params.get("sigma", FILTRO_GAUSSIAN_SIGMA_DEFAULT)
        return gaussian(arr, sigma)
    elif tipo == "median":
        size = params.get("size", FILTRO_MEDIAN_SIZE_DEFAULT)
        return median_filter(arr, size)
    elif tipo == "canny":
        sigma = params.get("sigma", FILTRO_CANNY_SIGMA_DEFAULT)
        low = params.get("low", FILTRO_CANNY_LOW_DEFAULT)
        high = params.get("high", FILTRO_CANNY_HIGH_DEFAULT)
        return canny(arr, sigma, low, high)
    else:
        raise ValueError(f"Filtro desconocido: {tipo_filtro}")


def sobel(arr: np.ndarray) -> np.ndarray:
    """
    Filtro Sobel: magnitud del gradiente.

    Args:
        arr: Array 2D.

    Returns:
        Magnitud del gradiente (float32).
    """
    dx = ndimage.sobel(arr, axis=0)
    dy = ndimage.sobel(arr, axis=1)
    return np.hypot(dx, dy).astype(np.float32)


def laplace(arr: np.ndarray) -> np.ndarray:
    """
    Filtro Laplaciano (segunda derivada).

    Args:
        arr: Array 2D.

    Returns:
        Laplaciana (float32).
    """
    return ndimage.laplace(arr).astype(np.float32)


def gaussian(arr: np.ndarray, sigma: float) -> np.ndarray:
    """
    Suavizado Gaussiano.

    Args:
        arr: Array 2D.
        sigma: Desviación estándar del kernel gaussiano.

    Returns:
        Array suavizado (float32).
    """
    return ndimage.gaussian_filter(arr, sigma=sigma).astype(np.float32)


def median_filter(arr: np.ndarray, size: int) -> np.ndarray:
    """
    Filtro de mediana (útil para eliminar ruido sal-pimienta).

    Args:
        arr: Array 2D.
        size: Tamaño del kernel (número impar). Si es par, se incrementa en 1.

    Returns:
        Array filtrado con mediana (float32).
    """
    # Asegurar que el tamaño sea impar
    if size % 2 == 0:
        size += 1
        logger.debug(f"Tamaño de filtro de mediana ajustado a {size} (impar)")
    return ndimage.median_filter(arr, size=size).astype(np.float32)


def canny(arr: np.ndarray, sigma: float, low: float, high: float) -> np.ndarray:
    """
    Detector de bordes Canny simplificado (basado en gradiente con histéresis).

    Este es un Canny simplificado (sin supresión de no-máximos completa)
    pero suficiente para destacar bordes en derivados morfométricos.

    Args:
        arr: Array 2D.
        sigma: Sigma para el suavizado Gaussiano previo.
        low: Umbral inferior (fracción del rango normalizado, 0-1).
        high: Umbral superior (fracción del rango normalizado, 0-1).

    Returns:
        Mapa de bordes: 1 = bordes débiles, 2 = bordes fuertes, 0 = fondo (float32).
    """
    # Suavizado gaussiano
    smoothed = ndimage.gaussian_filter(arr, sigma=sigma)

    # Magnitud del gradiente
    dx = ndimage.sobel(smoothed, axis=0)
    dy = ndimage.sobel(smoothed, axis=1)
    mag = np.hypot(dx, dy)

    # Normalizar a [0,1] si hay rango
    mag_min, mag_max = mag.min(), mag.max()
    if mag_max - mag_min > 1e-8:
        mag_norm = (mag - mag_min) / (mag_max - mag_min)
    else:
        mag_norm = np.zeros_like(mag)

    # Umbralización por histéresis (simplificada)
    edges = np.zeros_like(mag_norm, dtype=np.float32)
    edges[mag_norm >= low] = 1.0
    edges[mag_norm >= high] = 2.0
    return edges