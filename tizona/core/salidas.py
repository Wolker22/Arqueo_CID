# -*- coding: utf-8 -*-
"""
Módulo de salida de Tizona: exportación de productos y metadatos (Arqueo-CID)
==============================================================================

Centraliza toda la escritura geoespacial y de imágenes del plugin:
- GeoTIFFs de derivados y MDT con perfil optimizado (LERC_ZSTD, tiled).
- Imágenes PNG de cada derivado (opcional, con normalización configurable).
- Stack multibanda para IA (GeoTIFF multicapa, normalización winsorizada).
- Metadatos JSON por tesela (parámetros, estadísticas, calidad del MDT).
- Manifiesto IA (ia_manifest.json) para seguimiento de teselas procesadas.
"""

import os
import json
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
import rasterio
from rasterio.profiles import Profile

from ...utils.logging import get_logger
from ...config import (
    # Parámetros de exportación general
    TIFF_COMPRESSION,
    TIFF_PREDICTOR,
    TIFF_TILED,
    TIFF_BLOCK_SIZE,
    TIFF_NUM_THREADS,
    APLICAR_FILTRO_MEDIANA_DERIVADOS,
    FILTRO_MEDIANA_TAMANO,
    DERIVADOS_FILTRO_MEDIANA,
    EXPORTAR_PNG_MAX_WORKERS,
    EXPORTAR_STACK_NODATA,
    EXPORTAR_STACK_COMPRESSION,
    EXPORTAR_STACK_PREDICTOR,
    CALIDAD_MDT_SLOPE_THRESHOLD,
)

logger = get_logger("core.procesador.salida")


# ----------------------------------------------------------------------
# Función auxiliar para obtener el bounding box de manera segura
# ----------------------------------------------------------------------
def _obtener_bbox(procesador):
    """
    Obtiene el bounding box de la tesela procesada.
    Intenta varias fuentes en orden:
    1. Atributo _bbox (si existe, como método o propiedad)
    2. A partir del MDT (transform y shape)
    3. Desde la capa LiDAR original (si tiene método bbox)
    """
    # Si tiene _bbox como método y se puede llamar
    if hasattr(procesador, '_bbox') and callable(procesador._bbox):
        try:
            return procesador._bbox()
        except:
            pass
    # Si tiene _bbox como atributo
    if hasattr(procesador, '_bbox'):
        return procesador._bbox
    # Si tiene mdt_array y transform
    if hasattr(procesador, 'mdt_array') and procesador.mdt_array is not None and hasattr(procesador, 'transform'):
        h, w = procesador.mdt_array.shape
        left = procesador.transform[2]
        top = procesador.transform[5]
        right = left + w * procesador.transform[0]
        bottom = top + h * procesador.transform[4]
        return [left, bottom, right, top]  # orden común: minx, miny, maxx, maxy
    # Si tiene ruta_laz, intentar con PDAL (opcional, más pesado)
    if hasattr(procesador, 'ruta_laz') and procesador.ruta_laz and os.path.exists(procesador.ruta_laz):
        try:
            import pdal
            pipeline = pdal.Pipeline([
                procesador.ruta_laz,
                {
                    "type": "filters.info"
                }
            ])
            pipeline.execute()
            metadata = pipeline.metadata
            bbox = metadata.get("metadata", {}).get("bounds", {}).get("boundary", {}).get("coordinates", [])
            if bbox:
                # Formato: [minx, miny, maxx, maxy]
                xs = [c[0] for c in bbox[0]]
                ys = [c[1] for c in bbox[0]]
                return [min(xs), min(ys), max(xs), max(ys)]
        except:
            pass
    # Si nada funciona, devolver None
    return None


# ----------------------------------------------------------------------
# Perfil común para GeoTIFF de derivados y MDT
# ----------------------------------------------------------------------
def perfil_derivado(
    crs,
    transform,
    height: int,
    width: int,
    dtype_final,
    nodata=None,
) -> Profile:
    """
    Construye un perfil de rasterio optimizado para archivos GeoTIFF.
    Usa compresión LERC_ZSTD, tiled y predictor 3 para máximo rendimiento.
    Los parámetros se toman desde config.py.
    """
    perfil = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": dtype_final,
        "crs": crs,
        "transform": transform,
        "compress": TIFF_COMPRESSION,
        "predictor": TIFF_PREDICTOR,
        "num_threads": TIFF_NUM_THREADS,
        "tiled": TIFF_TILED,
        "blockxsize": TIFF_BLOCK_SIZE,
        "blockysize": TIFF_BLOCK_SIZE,
    }
    if nodata is not None:
        perfil["nodata"] = nodata
    return perfil


# ----------------------------------------------------------------------
# Guardado de derivados GeoTIFF
# ----------------------------------------------------------------------
def guardar_derivado_geotiff(
    array,
    ruta: str,
    crs,
    transform,
    aplicar_filtro_mediana: bool = False,
    tipo_derivado: str = "",
):
    """
    Guarda un array como GeoTIFF con el perfil optimizado.
    Opcionalmente aplica un filtro de mediana 3x3 a ciertos derivados
    para reducir ruido de alta frecuencia.
    """
    if (
        aplicar_filtro_mediana
        and APLICAR_FILTRO_MEDIANA_DERIVADOS
        and tipo_derivado in DERIVADOS_FILTRO_MEDIANA
    ):
        try:
            from scipy.ndimage import median_filter

            array = median_filter(array, size=FILTRO_MEDIANA_TAMANO, mode="nearest")
        except ImportError:
            pass

    if array.dtype == np.uint8:
        dtype_final = np.uint8
        nodata = None
    else:
        dtype_final = np.float32
        nodata = EXPORTAR_STACK_NODATA

    perfil = perfil_derivado(
        crs, transform, array.shape[0], array.shape[1], dtype_final, nodata
    )
    with rasterio.open(ruta, "w", **perfil) as dst:
        dst.write(array, 1)


# ----------------------------------------------------------------------
# Exportación de imágenes PNG
# ----------------------------------------------------------------------
def exportar_imagenes(
    procesador,
    rutas_derivados: Dict[str, str],
    carpeta_imagenes: str,
    nombre_base: str,
    normalizar: bool = True,
    perc_low: float = 2.0,
    perc_high: float = 98.0,
    progress_callback=None,
):
    """
    Genera imágenes PNG de 8 bits para cada derivado, de forma paralela.

    Args:
        procesador: Instancia de ProcesadorLiDAR (para verificar cancelación).
        rutas_derivados: Diccionario {nombre_derivado: ruta_geotiff}.
        carpeta_imagenes: Carpeta de destino para los PNG.
        nombre_base: Nombre base de la tesela.
        normalizar: Si True, aplica normalización de contraste.
        perc_low, perc_high: Percentiles para la normalización.
        progress_callback: Función para reportar progreso.
    """
    total = len(rutas_derivados)
    completadas = 0

    def exportar_una(deriv, ruta):
        """Función interna que exporta un único PNG."""
        if procesador._is_canceled():
            return deriv, False
        try:
            with rasterio.open(ruta) as src:
                arr_masked = src.read(1, masked=True)
                arr = np.where(
                    arr_masked.mask, np.nan, arr_masked.data.astype(np.float32)
                )
            if np.all(np.isnan(arr)):
                img = Image.fromarray(np.zeros((src.height, src.width), dtype=np.uint8))
            else:
                if normalizar:
                    vmin, vmax = np.nanpercentile(arr, [perc_low, perc_high])
                else:
                    vmin, vmax = np.nanmin(arr), np.nanmax(arr)
                if vmax > vmin:
                    arr_clip = np.clip(arr, vmin, vmax)
                    arr_norm = (arr_clip - vmin) / (vmax - vmin) * 255.0
                    arr_norm = np.nan_to_num(
                        arr_norm, nan=0.0, posinf=255.0, neginf=0.0
                    )
                    arr_norm = arr_norm.astype(np.uint8)
                else:
                    arr_norm = np.zeros_like(arr, dtype=np.uint8)
                img = Image.fromarray(arr_norm)
            ruta_png = os.path.join(carpeta_imagenes, f"{nombre_base}_{deriv}.png")
            img.save(ruta_png, optimize=True)
            return deriv, True
        except Exception as e:
            logger.error(f"Error exportando {deriv} a PNG: {e}")
            return deriv, False

    with ThreadPoolExecutor(max_workers=EXPORTAR_PNG_MAX_WORKERS) as executor:
        futures = {
            executor.submit(exportar_una, d, r): d for d, r in rutas_derivados.items()
        }
        for future in as_completed(futures):
            if procesador._is_canceled():
                executor.shutdown(wait=False, cancel_futures=True)
                raise InterruptedError("Cancelado")
            deriv, ok = future.result()
            completadas += 1
            pct = int(completadas / total * 100) if total else 0
            if progress_callback:
                progress_callback("imagenes", pct, f"Exportando {deriv}.png")


# ----------------------------------------------------------------------
# Stack multibanda para IA
# ----------------------------------------------------------------------
def exportar_stack_multibanda(
    rutas_derivados: Dict[str, str],
    carpeta_destino: str,
    nombre_base: str,
    bandas: List[str] = None,
    normalizar: bool = False,
    perc_low: float = 1.0,
    perc_high: float = 99.0,
    incluir_mascara: bool = False,
    progress_callback=None,
) -> Tuple[str, Dict]:
    """
    Genera un archivo GeoTIFF multicapa (stack) con todas las bandas de derivados.

    Args:
        rutas_derivados: Diccionario {nombre: ruta_geotiff}.
        carpeta_destino: Carpeta donde se guardará el stack.
        nombre_base: Nombre base de la tesela.
        bandas: Lista de nombres de derivados a incluir (None = todos).
        normalizar: Si True, aplica winsorización P01-P99 a cada banda.
        perc_low, perc_high: Percentiles para la normalización.
        incluir_mascara: Si True, añade una banda binaria de píxeles válidos.
        progress_callback: Función para reportar progreso.

    Returns:
        (ruta_stack, percentiles_por_banda)
    """
    if bandas is None:
        bandas = list(rutas_derivados.keys())

    # Leer perfil de la primera banda
    with rasterio.open(rutas_derivados[bandas[0]]) as src:
        perfil = src.profile
        altura, ancho = src.shape

    total_bandas = len(bandas) + (1 if incluir_mascara else 0)
    perfil.update(
        count=total_bandas,
        dtype=np.float32,
        compress=EXPORTAR_STACK_COMPRESSION,
        predictor=EXPORTAR_STACK_PREDICTOR,
        nodata=EXPORTAR_STACK_NODATA,
    )

    sufijo = "_MASK" if incluir_mascara else ""
    ruta_stack = os.path.join(
        carpeta_destino, f"{nombre_base}_STACK_{len(bandas)}B{sufijo}.tif"
    )

    percentiles_por_banda = {}
    mascara_valida = (
        np.ones((altura, ancho), dtype=np.float32) if incluir_mascara else None
    )

    with rasterio.open(ruta_stack, "w", **perfil) as dst:
        for idx, banda in enumerate(bandas, start=1):
            with rasterio.open(rutas_derivados[banda]) as src:
                arr_masked = src.read(1, masked=True)
                arr = np.where(
                    arr_masked.mask, np.nan, arr_masked.data.astype(np.float32)
                )

            arr_valid = arr[~np.isnan(arr)]
            if arr_valid.size > 0:
                p_low = float(np.percentile(arr_valid, perc_low))
                p_high = float(np.percentile(arr_valid, perc_high))
            else:
                p_low, p_high = 0.0, 1.0
            percentiles_por_banda[banda] = {"p_low": p_low, "p_high": p_high}

            if normalizar:
                if p_high > p_low:
                    arr_norm = np.clip(arr, p_low, p_high)
                    arr_norm = (arr_norm - p_low) / (p_high - p_low)
                    arr_norm = np.clip(arr_norm, 0.0, 1.0)
                else:
                    arr_norm = np.zeros_like(arr)
            else:
                arr_norm = arr.copy()

            arr_norm = np.where(
                np.isnan(arr_norm) | np.isinf(arr_norm), EXPORTAR_STACK_NODATA, arr_norm
            )
            dst.write(arr_norm, idx)

            if incluir_mascara and mascara_valida is not None:
                invalido = np.isnan(arr) | (arr_norm == EXPORTAR_STACK_NODATA)
                mascara_valida *= np.where(invalido, 0.0, 1.0)

            if progress_callback:
                progress_callback(
                    "stack", int(idx / len(bandas) * 100), f"Añadiendo banda {banda}"
                )

        if incluir_mascara and mascara_valida is not None:
            dst.write(mascara_valida, total_bandas)
            percentiles_por_banda["mask"] = {"p_low": 0.0, "p_high": 1.0}

    logger.info(f"Stack multibanda guardado en {ruta_stack}")
    return ruta_stack, percentiles_por_banda


# ----------------------------------------------------------------------
# Generador de metadatos
# ----------------------------------------------------------------------
class GeneradorMetadatos:
    """Clase estática para la generación de metadatos JSON y manifiesto IA."""

    @staticmethod
    def calcular_estadisticas(arr):
        """Calcula estadísticas básicas de un array, ignorando NaN."""
        if arr is None or arr.size == 0:
            return {}
        arr_f = arr[~np.isnan(arr)]
        if arr_f.size == 0:
            return {}
        return {
            "min": float(np.min(arr_f)),
            "max": float(np.max(arr_f)),
            "mean": float(np.mean(arr_f)),
            "std": float(np.std(arr_f)),
            "p01": float(np.percentile(arr_f, 1)),
            "p99": float(np.percentile(arr_f, 99)),
        }

    @staticmethod
    def calcular_calidad_mdt(mdt_array, resolucion):
        """
        Estima la calidad del MDT a partir del porcentaje de NaN
        y la rugosidad residual en zonas de baja pendiente.
        El umbral de pendiente se toma desde config.
        """
        if mdt_array is None:
            return {}
        total = mdt_array.size
        nan_celdas = np.count_nonzero(np.isnan(mdt_array))
        porcentaje_nan = (nan_celdas / total) * 100.0 if total > 0 else 100.0
        dy, dx = np.gradient(mdt_array, resolucion, resolucion)
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        slope_deg = np.degrees(slope_rad)
        mask = (slope_deg < CALIDAD_MDT_SLOPE_THRESHOLD) & (~np.isnan(slope_deg))
        rugosidad = float(np.std(slope_deg[mask])) if np.any(mask) else 0.0
        return {
            "porcentaje_nan": round(porcentaje_nan, 2),
            "densidad_puntos_km2_estimada": 0.0,  # No se calcula actualmente
            "rugosidad_residual_std_slope_grados": round(rugosidad, 3),
        }

    @staticmethod
    def generar(
        procesador,
        rutas_derivados,
        tiempo_procesamiento,
        stack_ia_ruta=None,
        percentiles_ia=None,
        calidad_mdt=None,
        actualizar_manifiesto=True,
    ) -> str:
        """
        Genera un archivo JSON con los metadatos completos de la tesela procesada.
        """
        carpeta_salida = procesador.carpeta_salida
        nombre_base = procesador.nombre_base

        # Calcular MD5 del archivo LAZ original
        hash_md5 = hashlib.md5()
        try:
            with open(procesador.ruta_laz, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            md5_checksum = hash_md5.hexdigest()
        except Exception as e:
            logger.warning(f"No se pudo calcular MD5 del LAZ: {e}")
            md5_checksum = None

        if calidad_mdt is None and procesador.mdt_array is not None:
            calidad_mdt = GeneradorMetadatos.calcular_calidad_mdt(
                procesador.mdt_array, procesador.res
            )

        metadatos = {
            "tesela": nombre_base,
            "fecha_procesamiento": datetime.now().isoformat(),
            "tiempo_segundos": tiempo_procesamiento,
            "fuente": {
                "archivo_laz": os.path.basename(procesador.ruta_laz),
                "md5_checksum": md5_checksum,
            },
            "crs": procesador.crs.to_string() if procesador.crs else None,
            "resolucion_m": procesador.res,
            "dimensiones": {
                "filas": procesador.mdt_array.shape[0]
                if procesador.mdt_array is not None
                else None,
                "columnas": procesador.mdt_array.shape[1]
                if procesador.mdt_array is not None
                else None,
            },
            "bbox": _obtener_bbox(procesador),  # <--- CORREGIDO
            "parametros": {
                "z_factor": procesador.z_factor,
                "radio_openness": procesador.radio_openness,
                "radio_lrm": procesador.radio_lrm,
                "radio_tpi": procesador.radio_tpi,
                "multidirectional": procesador.hillshade_multidir,
                "angulos_multidir": procesador.angulos_multidir,
                "algoritmo_suelo": procesador.algoritmo_suelo,
                "derivados_generados": list(rutas_derivados.keys()),
                "aplicar_filtro_mediana": getattr(
                    procesador, "aplicar_filtro_mediana", True
                ),
                "sigma_curvature": getattr(procesador, "sigma_curvature", None),
                "ridge_valley_radios": getattr(procesador, "ridge_valley_radios", None),
                "mrvbf_scales": getattr(procesador, "mrvbf_scales", None),
                "interpolation_method": getattr(
                    procesador, "interpolation_method", None
                ),
                "normalizacion_png": {
                    "activada": getattr(procesador.config, "normalizar_imagenes", False),
                    "perc_low": getattr(procesador.config, "png_perc_low", None),
                    "perc_high": getattr(procesador.config, "png_perc_high", None),
                },
                "normalizacion_stack": {
                    "activada": getattr(procesador.config, "normalizar_stack", False),
                    "perc_low": getattr(procesador.config, "stack_perc_low", None),
                    "perc_high": getattr(procesador.config, "stack_perc_high", None),
                },
            },
            "derivados": {},
            "calidad_mdt": calidad_mdt,
            "version_perfil": "3.0",
        }

        if stack_ia_ruta:
            metadatos["stack_ia"] = {
                "ruta": os.path.relpath(stack_ia_ruta, carpeta_salida),
                "percentiles_por_banda": percentiles_ia,
            }
        else:
            metadatos["stack_ia"] = None

        for nombre, ruta in rutas_derivados.items():
            try:
                with rasterio.open(ruta) as src:
                    arr_masked = src.read(1, masked=True)
                    arr = np.where(
                        arr_masked.mask, np.nan, arr_masked.data.astype(np.float32)
                    )
                    stats = GeneradorMetadatos.calcular_estadisticas(arr)
                metadatos["derivados"][nombre] = {
                    "ruta_relativa": os.path.relpath(ruta, carpeta_salida),
                    "estadisticas": stats,
                }
            except Exception as e:
                logger.error(f"Error leyendo estadísticas de {nombre}: {e}")

        ruta_json = os.path.join(carpeta_salida, f"{nombre_base}_metadatos.json")
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(metadatos, f, indent=2, ensure_ascii=False)

        logger.info(f"Metadatos guardados en {ruta_json}")

        if stack_ia_ruta and actualizar_manifiesto:
            GeneradorMetadatos._actualizar_ia_manifest(
                procesador,
                rutas_derivados,
                stack_ia_ruta,
                percentiles_ia,
                calidad_mdt,
            )

        return ruta_json

    @staticmethod
    def _actualizar_ia_manifest(
        procesador, rutas_derivados, stack_ia_ruta, percentiles_ia, calidad_mdt
    ):
        """Actualiza (o crea) el archivo ia_manifest.json en la carpeta de stacks."""
        carpeta_ia = os.path.dirname(stack_ia_ruta)
        bandas_reales = [k for k in rutas_derivados.keys() if k != "stack_ia"]

        entrada = {
            "tesela": procesador.nombre_base,
            "stack_ia": os.path.basename(stack_ia_ruta),
            "metadatos_json": f"{procesador.nombre_base}_metadatos.json",
            "calidad_mdt": calidad_mdt,
            "bandas_stack": bandas_reales,
            "normalizacion": "sin_normalizar",  # se actualiza si se aplicó normalización
            "percentiles_por_banda": percentiles_ia,
            "resolucion_m": procesador.res,
            "crs": procesador.crs.to_string() if procesador.crs else None,
            "bbox": _obtener_bbox(procesador),  # <--- CORREGIDO
        }

        ruta_manifest = os.path.join(carpeta_ia, "ia_manifest.json")
        if os.path.exists(ruta_manifest):
            with open(ruta_manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"teselas": []}

        existentes = [
            i
            for i, t in enumerate(data["teselas"])
            if t.get("tesela") == procesador.nombre_base
        ]
        if existentes:
            data["teselas"][existentes[0]] = entrada
        else:
            data["teselas"].append(entrada)

        with open(ruta_manifest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Manifiesto IA actualizado en {ruta_manifest}")