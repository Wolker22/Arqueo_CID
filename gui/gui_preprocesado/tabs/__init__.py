# -*- coding: utf-8 -*-
"""
Pestañas de la interfaz de configuración de Tizona.

Exporta las cinco pestañas:
- DatosTab: configuración de rutas, modos, exportación.
- ProcesamientoTab: filtrado de suelo, parámetros del MDT.
- DerivadosTab: selección de derivados y parámetros geométricos.
- RendimientoTab: paralelismo, memoria, GPU, PDAL, GeoTIFF.
- PerfilesTab: gestión de perfiles de configuración.
"""

from .datosTab import TabDatos as DatosTab
from .procesamientoTab import TabProcesamiento as ProcesamientoTab
from .derivadosTab import TabDerivados as DerivadosTab
from .rendimientoTab import TabRendimiento as RendimientoTab
from .perfilesTab import TabPerfiles as PerfilesTab

__all__ = [
    'DatosTab',
    'ProcesamientoTab',
    'DerivadosTab',
    'RendimientoTab',
    'PerfilesTab',
]