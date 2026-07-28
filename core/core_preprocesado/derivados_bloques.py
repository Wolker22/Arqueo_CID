# -*- coding: utf-8 -*-
"""
Procesamiento de derivados por bloques con solape y fusión suave (Arqueo-CID)
=============================================================================

Divide el MDT en ventanas solapadas para calcular derivados locales,
acumulando los resultados con pesos decrecientes en los bordes.
Corrige problemas de:
- Ghosting (artefactos en las uniones entre bloques).
- Bordes globales (efectos de borde en los límites de la tesela).
- Colisiones de caché GPU (limpieza de gradientes entre bloques).

Solo se aplica a derivados que dependen exclusivamente de una vecindad local.
Los derivados de ámbito global (flujo, TWI, MRVBF, Geomorphon) se procesan
directamente sin división en bloques.

Si la tesela es menor que el tamaño de bloque configurado, o el número de
bloques resultante es 1, se omite la división y se devuelve un diccionario
vacío para que el coordinador procese esos derivados directamente.
"""

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional

import numpy as np
import rasterio
from rasterio.windows import Window

from ...utils.logging import get_logger
from .salidas import perfil_derivado

# Importar constantes desde la configuración central
from ...config import (
    DERIVADOS_COMPATIBLES_BLOQUES,
    SOLAPE_PORCENTAJE,
    BLEND_WIDTH_DEFAULT,
    RADIO_RIDGE_VALLEY_ESTIMADO,
    TAMANO_BLOQUE_MIN,
    TAMANO_BLOQUE_MAX,
    TAMANO_BLOQUE_ALINEACION,
    BYTES_POR_PIXEL_ESTIMADO,
    FRACCION_VRAM_USAR,
    APLICAR_FILTRO_MEDIANA_BLOQUES,
    VENTANA_ESCRITURA_FINAL,
)

logger = get_logger('Tizona.derivados_bloques')

# Lock para evitar que múltiples hilos accedan simultáneamente a la GPU,
# lo que podría provocar errores de memoria en CUDA.
gpu_lock = threading.Lock()


def _make_blend_weight(h: int, w: int, blend_width: Optional[int] = None) -> np.ndarray:
    """
    Crea una máscara de pesos 2D que decae linealmente desde el centro
    hacia los bordes. Se utiliza para fusionar suavemente las zonas de
    solape entre bloques adyacentes.

    Args:
        h: Altura del bloque (píxeles).
        w: Anchura del bloque (píxeles).
        blend_width: Ancho en píxeles de la zona de decaimiento.
                     Si es None, usa BLEND_WIDTH_DEFAULT.

    Returns:
        Array de pesos con valores entre 0.001 y 1.0.
    """
    if blend_width is None:
        blend_width = BLEND_WIDTH_DEFAULT

    max_possible = min(h, w) // 2
    blend_width = min(blend_width, max_possible)
    if blend_width < 1:
        return np.ones((h, w), dtype=np.float32)

    weight = np.ones((h, w), dtype=np.float32)
    ramp = np.linspace(0, 1, blend_width, dtype=np.float32)

    # Aplicar rampas a los cuatro bordes
    weight[:blend_width, :] *= ramp[:, None]
    weight[-blend_width:, :] *= ramp[::-1, None]
    weight[:, :blend_width] *= ramp[None, :]
    weight[:, -blend_width:] *= ramp[None, ::-1]

    return np.clip(weight, 0.001, 1.0)


def calcular_ventana_local(bloque_z: np.ndarray, deriv: str, procesador: 'ProcesadorLiDAR') -> np.ndarray:
    """
    Calcula un único derivado sobre la ventana `bloque_z`.
    Garantiza que la forma de salida coincida con la de entrada,
    reintentando tras limpiar la caché de gradientes si es necesario.

    Args:
        bloque_z: Submatriz del MDT (con padding).
        deriv: Nombre del derivado a calcular.
        procesador: Instancia de ProcesadorLiDAR.

    Returns:
        Array con el resultado del derivado.

    Raises:
        RuntimeError: Si tras el reintento las dimensiones no coinciden.
        ValueError: Si el backend devuelve None.
    """
    if procesador.usar_gpu:
        with gpu_lock:
            resultado = procesador._calcular_derivado(deriv, bloque_z)
    else:
        resultado = procesador._calcular_derivado(deriv, bloque_z)

    if resultado is None:
        raise ValueError(f"Backend devolvió None para '{deriv}'")

    # Verificar que las dimensiones coincidan
    if resultado.shape != bloque_z.shape:
        logger.warning(
            f"Forma incorrecta {resultado.shape} vs {bloque_z.shape} en {deriv}. "
            "Reintentando tras limpiar caché."
        )
        if hasattr(procesador, "backend"):
            procesador.backend.release_gradients()
        # Recalcular con el mismo modo (GPU/CPU)
        if procesador.usar_gpu:
            with gpu_lock:
                resultado = procesador._calcular_derivado(deriv, bloque_z)
        else:
            resultado = procesador._calcular_derivado(deriv, bloque_z)
        if resultado.shape != bloque_z.shape:
            raise RuntimeError(
                f"No se pudo obtener la forma esperada {bloque_z.shape} "
                f"para {deriv} (se obtuvo {resultado.shape})"
            )
    return resultado


def _sugerir_tamano_bloque(procesador: 'ProcesadorLiDAR', height: int, width: int) -> int:
    """
    Calcula un tamaño de bloque óptimo basado en la VRAM disponible.
    Si no hay GPU, devuelve el tamaño configurado por el usuario.
    Se respetan los límites TAMANO_BLOQUE_MIN y TAMANO_BLOQUE_MAX,
    y se alinea a TAMANO_BLOQUE_ALINEACION.

    Args:
        procesador: Instancia de ProcesadorLiDAR.
        height: Alto total del MDT.
        width: Ancho total del MDT.

    Returns:
        Tamaño de bloque en píxeles (lado).
    """
    if not procesador.usar_gpu:
        return min(procesador.tamano_bloque, height, width)

    import torch
    free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
    # Usar solo una fracción de la VRAM libre
    usable_mb = free_mb * FRACCION_VRAM_USAR
    # Estimación: bytes por píxel * número de bandas (1) * overhead
    max_pixels = usable_mb * 1024 * 1024 / BYTES_POR_PIXEL_ESTIMADO
    lado = int(np.sqrt(max_pixels))
    lado = max(TAMANO_BLOQUE_MIN, min(TAMANO_BLOQUE_MAX, lado, height, width))
    lado = (lado // TAMANO_BLOQUE_ALINEACION) * TAMANO_BLOQUE_ALINEACION
    if lado < TAMANO_BLOQUE_MIN:
        lado = TAMANO_BLOQUE_MIN
    logger.info(
        f"Tamaño de bloque adaptado a VRAM: {lado} px "
        f"(VRAM libre: {free_mb:.0f} MB, usable: {usable_mb:.0f} MB)"
    )
    return lado


def procesar_derivados_en_bloques(
    procesador: 'ProcesadorLiDAR',
    mdt_array: np.ndarray,
    derivados: List[str],
) -> Dict[str, str]:
    """
    Procesa los derivados seleccionados dividiendo el MDT en bloques
    con solape y fusión suave.

    Args:
        procesador: Instancia de ProcesadorLiDAR.
        mdt_array: Array 2D con el MDT completo.
        derivados: Lista de nombres de derivados a calcular.

    Returns:
        Diccionario {nombre_derivado: ruta_geotiff} para los derivados
        que se procesaron por bloques. Si no se realizó división (tesela
        pequeña o un solo bloque), devuelve un diccionario vacío para que
        el coordinador los calcule directamente.
    """
    rutas: Dict[str, str] = {}
    height, width = mdt_array.shape

    # 1. Tamaño de bloque adaptado a la VRAM o configuración
    tamano_bloque = _sugerir_tamano_bloque(procesador, height, width)

    # 2. Calcular el padding necesario según los radios máximos de los derivados
    radios = [0]
    if any(d in derivados for d in ["openness_pos", "openness_neg", "openness_aniso"]):
        radios.append(procesador.radio_openness)
    if any(d in derivados for d in ["lrm"]):
        radios.append(procesador.radio_lrm)
    if "tpi" in derivados:
        # radio_tpi puede ser escalar o lista
        tpi_radios = procesador.radio_tpi
        if isinstance(tpi_radios, (list, tuple)):
            radios.extend(tpi_radios)
        else:
            radios.append(tpi_radios)
    if "ridge_valley" in derivados:
        radios.append(RADIO_RIDGE_VALLEY_ESTIMADO)
    max_radio_m = max(radios)
    pad_px = int(np.ceil(max_radio_m / procesador.res)) + 10

    # 3. Solape: el mayor entre el padding y el porcentaje configurado del bloque
    overlap = max(pad_px + 1, int(SOLAPE_PORCENTAJE * tamano_bloque))
    step = tamano_bloque - overlap
    if step <= 0:
        step = 1

    # 4. Guard clause: tesela pequeña o bloque único
    bloques_y = list(range(0, height, step))
    bloques_x = list(range(0, width, step))
    if (tamano_bloque >= height and tamano_bloque >= width) or (
        len(bloques_y) <= 1 and len(bloques_x) <= 1
    ):
        logger.info(
            f"Tesela pequeña ({height}x{width}) o bloque único: "
            "se omite la división en bloques."
        )
        return {}

    # 5. Filtrar derivados compatibles (por si acaso se pasa algún no compatible)
    derivados_bloque = [d for d in derivados if d in DERIVADOS_COMPATIBLES_BLOQUES]
    if not derivados_bloque:
        logger.info("Ningún derivado compatible con bloques, se omite división.")
        return {}

    # 6. Directorio temporal para acumuladores (memmaps)
    temp_dir = tempfile.mkdtemp(dir=procesador.carpeta_derivados)
    memmaps: Dict[str, Dict[str, np.memmap]] = {}
    write_locks: Dict[str, threading.Lock] = {}

    # Crear archivos memmap para acumulación
    for deriv in derivados_bloque:
        ruta_salida = os.path.join(
            procesador.carpeta_derivados,
            f"{procesador.nombre_base}_{deriv}.tif",
        )
        rutas[deriv] = ruta_salida
        acc_path = os.path.join(temp_dir, f"{deriv}_acc.dat")
        w_path = os.path.join(temp_dir, f"{deriv}_w.dat")
        memmaps[deriv] = {
            "accum": np.memmap(
                acc_path, dtype="float32", mode="w+", shape=(height, width)
            ),
            "weights": np.memmap(
                w_path, dtype="float32", mode="w+", shape=(height, width)
            ),
        }
        write_locks[deriv] = threading.Lock()

    def procesar_bloque(y0: int, x0: int) -> bool:
        """
        Procesa un único bloque del MDT para todos los derivados.
        Retorna True si tuvo éxito, False si se canceló o falló críticamente.
        """
        if procesador._is_canceled():
            return False

        y1 = min(y0 + tamano_bloque, height)
        x1 = min(x0 + tamano_bloque, width)

        # Ventana extendida con padding
        y0_ext = y0 - pad_px
        y1_ext = y1 + pad_px
        x0_ext = x0 - pad_px
        x1_ext = x1 + pad_px

        # Recortar a límites reales
        real_y0 = max(0, y0_ext)
        real_y1 = min(height, y1_ext)
        real_x0 = max(0, x0_ext)
        real_x1 = min(width, x1_ext)

        sub_mdt_real = mdt_array[real_y0:real_y1, real_x0:real_x1]

        # Calcular padding artificial necesario
        pad_top = real_y0 - y0_ext
        pad_bottom = y1_ext - real_y1
        pad_left = real_x0 - x0_ext
        pad_right = x1_ext - real_x1

        bloque_z = np.pad(
            sub_mdt_real,
            ((pad_top, pad_bottom), (pad_left, pad_right)),
            mode="edge",
        )

        # Región central (la que corresponde al bloque original)
        bh, bw = y1 - y0, x1 - x0
        center_y = (bloque_z.shape[0] - bh) // 2
        center_x = (bloque_z.shape[1] - bw) // 2
        core_y0, core_y1 = center_y, center_y + bh
        core_x0, core_x1 = center_x, center_x + bw

        # Calcular cada derivado
        for deriv in derivados_bloque:
            try:
                # Limpiar caché de gradientes antes de este bloque
                if hasattr(procesador, "backend"):
                    procesador.backend.release_gradients()

                res_bloque = calcular_ventana_local(bloque_z, deriv, procesador)
                res_core = res_bloque[core_y0:core_y1, core_x0:core_x1]

                if res_core.shape != (bh, bw):
                    logger.error(
                        f"Forma inesperada {res_core.shape} en bloque ({y0},{x0}) "
                        f"para {deriv} (esperado {bh}x{bw})"
                    )
                    continue

                peso = _make_blend_weight(bh, bw)

                # Acumular ponderadamente (thread‑safe)
                with write_locks[deriv]:
                    valid = ~np.isnan(res_core)
                    if np.any(valid):
                        memmaps[deriv]["accum"][y0:y1, x0:x1][valid] += (
                            res_core * peso
                        )[valid]
                        memmaps[deriv]["weights"][y0:y1, x0:x1][valid] += peso[valid]

            except Exception as e:
                logger.error(f"Fallo en bloque ({y0},{x0}) para {deriv}: {e}")
        return True

    # Generar lista de coordenadas de bloques
    tareas = [(y, x) for y in range(0, height, step) for x in range(0, width, step)]
    procesador._report_progress(
        "derivados",
        5,
        f"Procesando {len(tareas)} bloques (solape {overlap} px)",
    )

    # Limitar número de hilos si se usa GPU para evitar agotar VRAM
    max_workers = getattr(procesador, "max_hilos_procesamiento", 4)
    if procesador.usar_gpu:
        max_workers = min(2, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(procesar_bloque, y, x) for y, x in tareas]
        completados = 0
        for future in as_completed(futures):
            if procesador._is_canceled():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            completados += 1
            if completados % max(1, len(tareas) // 10) == 0:
                pct = 10 + int((completados / len(tareas)) * 80)
                procesador._report_progress(
                    "derivados", pct, f"Bloques: {completados}/{len(tareas)}"
                )

    # Liberar caché general al finalizar todos los bloques
    if hasattr(procesador, "backend"):
        procesador.backend.release_gradients()

    # Fusión final y escritura a GeoTIFF por ventanas
    for deriv in derivados_bloque:
        procesador._report_progress("derivados", 92, f"Fusionando {deriv}...")
        accum = memmaps[deriv]["accum"]
        weights = memmaps[deriv]["weights"]

        if deriv == "hillshade":
            dtype_final = np.uint8
            nodata = None
        else:
            dtype_final = np.float32
            nodata = -9999.0

        perfil = perfil_derivado(
            procesador.crs,
            procesador.transform,
            height,
            width,
            dtype_final,
            nodata,
        )

        with rasterio.open(rutas[deriv], "w", **perfil) as dst:
            for y0 in range(0, height, VENTANA_ESCRITURA_FINAL):
                y1 = min(y0 + VENTANA_ESCRITURA_FINAL, height)
                # Leer los acumuladores en memoria para esta franja
                accum_chunk = np.array(accum[y0:y1, :])
                weights_chunk = np.array(weights[y0:y1, :])
                mask = weights_chunk > 0
                final_chunk = np.full(accum_chunk.shape, np.nan, dtype=np.float32)
                final_chunk[mask] = accum_chunk[mask] / weights_chunk[mask]

                # Post‑procesado específico
                if deriv == "hillshade":
                    final_chunk = np.clip(final_chunk, 0, 255).astype(np.uint8)
                elif (
                    APLICAR_FILTRO_MEDIANA_BLOQUES
                    and deriv
                    in (
                        "openness_pos",
                        "openness_neg",
                        "tpi",
                        "lrm",
                        "curvature",
                        "curvature_vert",
                        "curvature_horiz",
                        "ridge_valley",
                    )
                ):
                    try:
                        from scipy.ndimage import median_filter

                        final_chunk = median_filter(final_chunk, size=3, mode="nearest")
                    except ImportError:
                        pass

                # Escribir la franja en el GeoTIFF
                window = Window(0, y0, width, y1 - y0)
                dst.write(final_chunk, 1, window=window)

        # Liberar recursos y eliminar archivos temporales
        del memmaps[deriv]["accum"]
        del memmaps[deriv]["weights"]
        try:
            os.remove(os.path.join(temp_dir, f"{deriv}_acc.dat"))
            os.remove(os.path.join(temp_dir, f"{deriv}_w.dat"))
        except OSError:
            pass

    # Limpiar directorio temporal
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    return rutas