# 🏺 Arqueo CID

**Plataforma de teledetección LiDAR para arqueología – Preprocesado (Tizona) y Postprocesado IA (Colada)**

![QGIS Plugin](https://img.shields.io/badge/QGIS-3.22%2B-brightgreen)
![Python](https://img.shields.io/badge/Python-3.9%20|%203.10%20|%203.11-blue)
![License](https://img.shields.io/badge/License-GPLv3-orange)
![Status](https://img.shields.io/badge/Status-Beta-yellow)

Arqueo CID es un **plugin para QGIS** que integra todo el flujo de trabajo para el análisis arqueológico mediante datos LiDAR del **PNOA (Plan Nacional de Ortofotografía Aérea)**.  
Consta de dos módulos principales:

- 🧭 **Tizona** – Descarga, filtrado de suelo, generación de MDT y cálculo de derivados morfométricos.
- 🤖 **Colada** – Detección de anomalías arqueológicas mediante Autoencoder Variacional (VAE) o Isolation Forest, más filtros clásicos de imagen.

---

## ✨ Características destacadas

- **Descarga automática** de archivos LAZ del CNIG (1ª, 2ª y 3ª cobertura), con filtro por tipo de producto (RGB/IRC/COL).
- **Filtrado de suelo** con SMRF, CSF o usando clasificación existente (clase 2).
- **Generación de MDT** con resolución configurable, suavizado gaussiano y relleno de huecos.
- **Cálculo de 15 derivados morfométricos** (pendiente, curvaturas, TPI, LRM, Openness, MRVBF, hillshade multidireccional…).
- **Procesamiento por bloques** con solape y fusión suave para grandes teselas.
- **Exportación a GeoTIFF (compresión LERC_ZSTD), PNG, stacks multibanda para IA** y metadatos JSON.
- **Entrenamiento de un VAE** sobre parches de terreno para aprender la morfología normal.
- **Predicción de anomalías** con el VAE entrenado o con Isolation Forest (aprendizaje sin etiquetas).
- **Filtros clásicos** (Sobel, Laplace, Gaussiano, Mediana, Canny) aplicables a cualquier derivado.
- **Interfaz intuitiva** con pestañas modales y no modales, barras de progreso, cancelación en segundo plano.
- **Soporte GPU** (PyTorch CUDA) y aceleración mediante GDAL (hillshade/slope).
- **Compatible con QGIS 3.22 a 3.99** y Python 3.9-3.11.

---

## 📦 Requisitos del sistema

- QGIS >= 3.22 (recomendado 3.28 o superior)
- Python 3.9, 3.10 o 3.11 (entorno de QGIS)
- **Dependencias Python** (se instalan automáticamente al instalar el plugin desde el repositorio oficial):
