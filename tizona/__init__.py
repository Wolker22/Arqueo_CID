# -*- coding: utf-8 -*-
"""
Tizona – Preprocesado LiDAR (parte de Arqueo Cid)
==================================================

Submódulo encargado de la descarga, filtrado de suelo, generación de MDT,
cálculo de derivados morfométricos y exportación de resultados (GeoTIFF, PNG,
stacks multibanda, metadatos). Es el componente de preprocesado de la plataforma.

Este submódulo no tiene classFactory propia; es cargado e instanciado
por el plugin paraguas ArqueoCidPlugin.

Exports:
    TizonaPlugin: Clase principal del módulo.
"""

from .main import TizonaPlugin

__all__ = ['TizonaPlugin']