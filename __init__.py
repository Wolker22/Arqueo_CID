# -*- coding: utf-8 -*-
"""
Arqueo Cid v1.0 – Plataforma de teledetección LiDAR para arqueología.

Integra dos módulos complementarios:
    - Tizona : preprocesado de datos LiDAR (descarga, filtrado, MDT, derivados).
    - Colada : postprocesado con inteligencia artificial (entrenamiento y predicción).

Este es el punto de entrada único para QGIS. Al cargarse, añade una
barra de herramientas con tres botones (Arqueo Cid, Tizona, Colada) y
gestiona el mapa base.
"""

from typing import Any


def classFactory(iface: Any) -> Any:
    """
    Punto de entrada estándar de QGIS.

    Args:
        iface: Interfaz de QGIS proporcionada por el framework.

    Returns:
        Instancia del plugin principal ArqueoCidPlugin.
    """
    from .main import ArqueoCidPlugin
    return ArqueoCidPlugin(iface)