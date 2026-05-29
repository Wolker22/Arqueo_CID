# -*- coding: utf-8 -*-
"""
Interfaz gráfica de Tizona.

Exporta los diálogos principales:
- DialogoConfiguracion: diálogo de configuración de procesamiento.
- DialogoProgreso: diálogo de progreso de descarga y procesamiento.
"""

from .dialogoConfiguracion import DialogoConfiguracion
from .dialogoProgreso import DialogoProgreso

__all__ = ['DialogoConfiguracion', 'DialogoProgreso']