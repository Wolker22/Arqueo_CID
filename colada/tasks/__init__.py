# -*- coding: utf-8 -*-
"""
Tareas asíncronas de COLADA
============================

Proporciona tareas en segundo plano para entrenamiento y predicción,
que se ejecutan sin bloquear la interfaz de QGIS.
"""

from .pipeline_entrenamiento import TareaEntrenamiento, lanzar_entrenamiento
from .pipeline_prediccion import TareaPrediccion

__all__ = [
    'TareaEntrenamiento',
    'lanzar_entrenamiento',
    'TareaPrediccion',
]