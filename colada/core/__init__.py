# -*- coding: utf-8 -*-
"""
Núcleo de inferencia de COLADA
===============================

Contiene los componentes fundamentales para el entrenamiento y predicción:
- vae: Autoencoder Variacional convolucional.
- entrenador: funciones de entrenamiento del VAE.
- predictor: inferencia con VAE e Isolation Forest.
- filtros_imagen: filtros clásicos (Sobel, Laplace, Gaussiano, Mediana, Canny).
- tizona_integration: utilidades para localizar stacks generados por Tizona.
"""

from .vae import AutoencoderVariacional
from .entrenador import entrenar_vae, calcular_percentiles_globales, TerrainPatchDataset
from .predictor import (
    cargar_modelo_vae,
    leer_stack_multibanda,
    extraer_parches_generator,
    inferir_y_reconstruir,
    suavizar_y_umbralizar,
    guardar_raster,
    vectorizar_anomalias,
    predecir_anomalia_isolation_forest,
)
from .filtros_imagen import aplicar_filtro, sobel, laplace, gaussian, median_filter, canny
from .tizona_integration import buscar_carpeta_tizona, recolectar_stacks, recolectar_stacks_por_tesela

__all__ = [
    'AutoencoderVariacional',
    'entrenar_vae',
    'calcular_percentiles_globales',
    'TerrainPatchDataset',
    'cargar_modelo_vae',
    'leer_stack_multibanda',
    'extraer_parches_generator',
    'inferir_y_reconstruir',
    'suavizar_y_umbralizar',
    'guardar_raster',
    'vectorizar_anomalias',
    'predecir_anomalia_isolation_forest',
    'aplicar_filtro',
    'sobel',
    'laplace',
    'gaussian',
    'median_filter',
    'canny',
    'buscar_carpeta_tizona',
    'recolectar_stacks',
    'recolectar_stacks_por_tesela',
]