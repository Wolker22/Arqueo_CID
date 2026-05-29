# -*- coding: utf-8 -*-
"""
Colada – Detección Arqueológica mediante LiDAR e Inteligencia Artificial
========================================================================

Submódulo de postprocesado del proyecto Arqueo Cid.

Proporciona:
- Entrenamiento de VAE (Autoencoder Variacional) para detección de anomalías.
- Predicción con VAE o Isolation Forest.
- Filtros clásicos de imagen (Sobel, Laplace, Gaussiano, Mediana, Canny).
- Integración con los stacks generados por Tizona.

Este submódulo no tiene classFactory propia; es cargado e instanciado
por el plugin paraguas ArqueoCidPlugin.
"""

from .main import ColadaPlugin

__all__ = ['ColadaPlugin']