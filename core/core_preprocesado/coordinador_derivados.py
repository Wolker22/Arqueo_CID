# -*- coding: utf-8 -*-
"""
Coordinador de cálculo de derivados morfométricos (Arqueo-CID)
==============================================================

Centraliza la decisión de qué derivados se procesan en bloques (con solape y fusión)
y cuáles se calculan directamente sobre el MDT completo. Utiliza las funciones de
salida unificadas para guardar los resultados en GeoTIFF.

El procesamiento por bloques solo se aplica si el usuario ha activado la opción
correspondiente y el derivado pertenece a la lista de compatibles (derivados que
dependen exclusivamente de una vecindad local). El resto se procesan de una sola vez
para preservar la coherencia global (ej. hidrología, clasificación).

Incluye logs detallados con la duración de cada derivado para facilitar
la identificación de cuellos de botella.
"""

import os
import time
from typing import Dict, List, Optional, Callable

import numpy as np

# Importaciones del plugin
from ...utils.logging import get_logger
from .derivados_bloques import procesar_derivados_en_bloques
from .salidas import guardar_derivado_geotiff

# Importar constantes desde la configuración central
from ...config import (
    DERIVADOS_COMPATIBLES_BLOQUES,
    MRVBF_SLOPE_THRESHOLD_DEFAULT,
    APLICAR_FILTRO_MEDIANA_DERIVADOS,
)

logger = get_logger('Tizona.coordinador_derivados')


class CoordinadorDerivados:
    """
    Orquesta el cálculo de todos los derivados seleccionados en la configuración.

    Attributes:
        proc: Instancia de ProcesadorLiDAR con acceso a la configuración, backend,
              callbacks de progreso/cancelación y parámetros geométricos.
        backend: Motor de cálculo morfométrico (PytorchBackend o similar).
    """

    def __init__(self, procesador: 'ProcesadorLiDAR') -> None:
        """
        Args:
            procesador: Instancia de ProcesadorLiDAR.
        """
        self.proc = procesador
        self.backend = procesador.backend

        # Construir el mapeo de nombres de derivados a funciones del backend.
        # Se utiliza tanto para el cálculo directo como para las ventanas locales.
        self._metodos: Dict[str, Callable[[np.ndarray], Optional[np.ndarray]]] = {
            "hillshade": lambda z: self.backend.hillshade(
                z,
                self.proc.z_factor,
                self.proc.angulos_multidir,
                self.proc.hillshade_multidir,
            ),
            "slope": self.backend.slope,
            "aspect_sin": self.backend.aspect_sin,
            "aspect_cos": self.backend.aspect_cos,
            "curvature": self.backend.curvature,
            "curvature_vert": self.backend.curvature_vert,
            "curvature_horiz": self.backend.curvature_horiz,
            "tpi": lambda z: self.backend.tpi_multiescala(
                z, self.proc.radio_tpi  # puede ser escalar o lista
            ),
            "lrm": lambda z: self.backend.local_relief_model(
                z, self.proc.radio_lrm
            ),
            "ridge_valley": lambda z: self.backend.ridge_valley(
                z, getattr(self.proc, "ridge_valley_radios", None)
            ),
            "openness_pos": lambda z: self.backend.openness(
                z, self.proc.radio_openness, positive=True
            ),
            "openness_neg": lambda z: self.backend.openness(
                z, self.proc.radio_openness, positive=False
            ),
            "openness_aniso": lambda z: self.backend.openness_anisotropic(
                z, self.proc.radio_openness
            ),
            "sky_view_factor": self.backend.sky_view_factor,
            "mrvbf": lambda z: self.backend.mrvbf(
                z,
                scales=getattr(self.proc, "mrvbf_scales", None),
                slope_threshold=getattr(self.proc, "mrvbf_slope_threshold", MRVBF_SLOPE_THRESHOLD_DEFAULT),
            ),
        }

    def calcular_derivados(self, mdt_array: np.ndarray) -> Dict[str, str]:
        """
        Calcula todos los derivados activos en la configuración y devuelve
        un diccionario {nombre_derivado: ruta_geotiff}.

        Args:
            mdt_array: Array 2D con el MDT completo (en unidades del CRS, normalmente metros).

        Returns:
            Diccionario con las rutas absolutas de los GeoTIFF generados.

        Raises:
            InterruptedError: Si el usuario cancela el proceso.
        """
        if self.proc._is_canceled():
            raise InterruptedError("Cancelado por el usuario")

        self.proc._report_progress("derivados", 0, "Calculando derivados...")

        # Obtener la lista de derivados desde la configuración del procesador
        derivados_activos = self.proc.config.derivados

        # Separar según compatibilidad con el procesamiento por bloques
        derivados_bloques = [
            d for d in derivados_activos if d in DERIVADOS_COMPATIBLES_BLOQUES
        ]
        derivados_directos = [
            d for d in derivados_activos if d not in DERIVADOS_COMPATIBLES_BLOQUES
        ]

        rutas: Dict[str, str] = {}

        # --- Procesamiento por bloques (solo si está activado y hay derivados compatibles) ---
        if self.proc.usar_bloques and derivados_bloques:
            logger.info(
                f"Procesando {len(derivados_bloques)} derivados por bloques: "
                f"{', '.join(derivados_bloques)}"
            )
            inicio_bloques = time.time()
            rutas_bloques = procesar_derivados_en_bloques(
                self.proc, mdt_array, derivados_bloques
            )
            duracion_bloques = time.time() - inicio_bloques
            logger.info(f"Derivados por bloques completados en {duracion_bloques:.1f}s")
            rutas.update(rutas_bloques)
        else:
            # Si no se usan bloques, todos los derivados se calculan directamente
            derivados_directos.extend(derivados_bloques)

        # --- Procesamiento directo (uno a uno, con logs detallados) ---
        total_directos = len(derivados_directos)
        for i, deriv in enumerate(derivados_directos):
            if self.proc._is_canceled():
                raise InterruptedError("Cancelado por el usuario")

            # Ruta de salida (minúsculas, extensión .tif)
            ruta = os.path.join(
                self.proc.carpeta_derivados,
                f"{self.proc.nombre_base}_{deriv}.tif",
            )

            # Si ya existe, se omite el cálculo (útil para reanudar procesos)
            if os.path.exists(ruta):
                logger.info(f"Derivado '{deriv}' ya existe en disco, se omite su cálculo.")
                rutas[deriv] = ruta
                continue

            # Reportar progreso y registrar inicio en el log
            porcentaje = int(i / total_directos * 100) if total_directos else 0
            self.proc._report_progress(
                "derivados", porcentaje, f"Calculando {deriv}..."
            )
            logger.info(f"[{i+1}/{total_directos}] Iniciando cálculo de '{deriv}'...")
            inicio_deriv = time.time()

            try:
                # Obtener la función correspondiente del mapeo
                if deriv not in self._metodos:
                    logger.warning(f"Derivado '{deriv}' no reconocido, se omite.")
                    continue

                arr = self._metodos[deriv](mdt_array)
                duracion = time.time() - inicio_deriv

                if arr is not None:
                    # Guardar usando la función centralizada de salidas
                    guardar_derivado_geotiff(
                        arr,
                        ruta,
                        crs=self.proc.crs,
                        transform=self.proc.transform,
                        aplicar_filtro_mediana=APLICAR_FILTRO_MEDIANA_DERIVADOS,
                        tipo_derivado=deriv,
                    )
                    rutas[deriv] = ruta
                    logger.info(f"Derivado '{deriv}' completado en {duracion:.1f}s")
                else:
                    logger.warning(f"Derivado '{deriv}' devolvió None tras {duracion:.1f}s")
            except Exception as e:
                duracion = time.time() - inicio_deriv
                logger.error(f"Error calculando '{deriv}' tras {duracion:.1f}s: {e}")

        self.proc._report_progress("derivados", 100, "Derivados completados")
        return rutas