# -*- coding: utf-8 -*-
"""
Modelos de configuración procesable para Arqueo-CID
===================================================

Contiene dataclasses validadas para:
- Tizona: ConfiguracionProcesamiento (parámetros de preprocesado LiDAR)
- Colada: ConfiguracionColada (parámetros de entrenamiento e inferencia)

Las clases incluyen validación en __post_init__ y métodos para convertir a/desde dict.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# Importamos las constantes por defecto desde el archivo de configuración global
from ..config import (
    # Tizona
    RESOLUCION_MDT,
    Z_FACTOR_HILLSHADE,
    RADIO_OPENNESS,
    RADIO_LRM,
    RADIO_TPI_MULTIESCALA,
    HILLSHADE_MULTIDIR,
    ANGULOS_MULTIDIR,
    DERIVADOS_POR_DEFECTO,
    ALGORITMO_FILTRADO_SUELO,
    USAR_CLASIFICACION_EXISTENTE,
    SMRF_WINDOW,
    SMRF_SLOPE,
    SMRF_THRESHOLD,
    USAR_PROCESAMIENTO_BLOQUES,
    TAMANO_BLOQUE,
    MEMORIA_MAX_MB,
    MIN_MEMORIA_LIBRE_MB,
    MAX_HILOS_PROCESAMIENTO,
    USAR_GPU,
    USAR_PDAL,
    PDAL_DECIMATION_STEP,
    PDAL_OUTPUT_TYPE,
    PDAL_SOLAPE_VOXEL,
    GAUSSIAN_BLUR_SIGMA,
    PADDING_REFLECT_PX,
    INTERPOLATION_METHOD,
    GENERAR_IMAGENES_PNG,
    NORMALIZAR_IMAGENES,
    PNG_PERC_LOW,
    PNG_PERC_HIGH,
    EXPORTAR_STACK_MULTIBANDA,
    NORMALIZAR_STACK,
    STACK_PERC_LOW,
    STACK_PERC_HIGH,
    INCLUIR_MASCARA_STACK,
    GENERAR_METADATOS_JSON,
    GENERAR_MANIFIESTO_IA,
    # Colada
    VAE_IN_CHANNELS,
    VAE_LATENT_DIM,
    VAE_FEATURES,
    TAMANO_PARCHE,
    EPOCAS,
    BATCH_SIZE,
    LEARNING_RATE,
    K_TRIM,
    KL_WEIGHT,
    VAL_SPLIT,
    PATIENCE,
    SEED,
    PATHS_PER_EPOCH,
    MAX_CACHE_SIZE,
    MAX_GPU_WORKERS,
    CPU_WORKERS,
    SIGMA_GAUSSIANO,
    UMBRAL_PERCENTIL,
    SOLAPAMIENTO,
    TAMANIO_LOTE,
    VENTANA_ADAPTATIVA,
    ASPECT_RATIO_MAX,
    CIRCULARITY_MIN,
    MODELO_PREDICCION,
)


# ============================================================================
# Configuración de Tizona (preprocesado LiDAR)
# ============================================================================

@dataclass
class ConfiguracionProcesamiento:
    """
    Contenedor validado de parámetros de procesamiento y exportación para Tizona.

    Attributes:
        resolucion: Resolución del MDT en metros por píxel.
        z_factor: Factor de exageración vertical para hillshade.
        radio_openness: Radio (metros) para Openness y SVF.
        radio_lrm: Radio (metros) para LRM.
        radio_tpi_multiescala: Lista de radios (metros) para TPI multiescala.
        multidirectional: Si es True, hillshade multidireccional.
        angulos_multidir: Lista de ángulos de iluminación (grados) para hillshade multidir.
        derivados: Lista de nombres de derivados a generar.
        aplicar_filtro_mediana: Aplicar filtro mediana a derivados seleccionados.
        algoritmo_suelo: 'smrf', 'csf' o 'none'.
        usar_clasificacion_existente: Usar clase 2 del LAZ original.
        smrf_window: Tamaño de ventana SMRF (píxeles).
        smrf_slope: Pendiente esperada del terreno (adimensional).
        smrf_threshold: Umbral de elevación (metros).
        usar_bloques: Activar procesamiento por bloques.
        tamano_bloque: Tamaño del bloque en píxeles.
        memoria_max_mb: Memoria máxima para caché (MB).
        min_memoria_libre_mb: Memoria libre mínima para no pausar (MB).
        usar_gdal: Usar GDAL nativo para hillshade y slope.
        max_hilos_procesamiento: Hilos internos por tesela.
        usar_gpu: Usar GPU (PyTorch CUDA).
        usar_pdal: Usar PDAL para MDT.
        pdal_decimation_step: Factor de diezmado PDAL.
        pdal_output_type: Método de interpolación PDAL ('idw', 'mean', ...).
        pdal_solape_voxel: Tamaño de vóxel para solape (experimental).
        gaussian_blur_sigma: Sigma del suavizado gaussiano previo.
        padding_reflect_px: Padding reflectante en píxeles.
        interpolation_method: 'linear' o 'invdist' para GDAL Grid.
        sigma_curvature: Sigma para cálculo de curvaturas.
        ridge_valley_radios: Radios (metros) para ridge_valley.
        mrvbf_scales: Escalas (metros) para MRVBF.
        generar_imagenes_png: Generar PNG.
        normalizar_imagenes: Normalizar PNG.
        png_perc_low: Percentil bajo para normalización PNG.
        png_perc_high: Percentil alto para normalización PNG.
        exportar_stack: Generar stack multibanda.
        normalizar_stack: Normalizar stack.
        stack_perc_low: Percentil bajo para normalización stack.
        stack_perc_high: Percentil alto para normalización stack.
        incluir_mascara_stack: Incluir banda de máscara.
        generar_metadatos_json: Generar JSON de metadatos.
        generar_manifiesto_ia: Actualizar manifiesto IA.
    """

    # ── Procesamiento básico ──
    resolucion: float = RESOLUCION_MDT
    z_factor: float = Z_FACTOR_HILLSHADE
    radio_openness: float = RADIO_OPENNESS
    radio_lrm: float = RADIO_LRM
    radio_tpi_multiescala: List[float] = field(default_factory=lambda: list(RADIO_TPI_MULTIESCALA))
    multidirectional: bool = HILLSHADE_MULTIDIR
    angulos_multidir: List[float] = field(default_factory=lambda: list(ANGULOS_MULTIDIR))
    derivados: List[str] = field(default_factory=lambda: list(DERIVADOS_POR_DEFECTO))
    aplicar_filtro_mediana: bool = True
    algoritmo_suelo: str = ALGORITMO_FILTRADO_SUELO
    usar_clasificacion_existente: bool = USAR_CLASIFICACION_EXISTENTE

    # ── SMRF ──
    smrf_window: int = SMRF_WINDOW
    smrf_slope: float = SMRF_SLOPE
    smrf_threshold: float = SMRF_THRESHOLD

    # ── Bloques y memoria ──
    usar_bloques: bool = USAR_PROCESAMIENTO_BLOQUES
    tamano_bloque: int = TAMANO_BLOQUE
    memoria_max_mb: int = MEMORIA_MAX_MB
    min_memoria_libre_mb: int = MIN_MEMORIA_LIBRE_MB

    # ── Backends ──
    usar_gdal: bool = False
    max_hilos_procesamiento: int = MAX_HILOS_PROCESAMIENTO
    usar_gpu: bool = USAR_GPU
    usar_pdal: bool = USAR_PDAL
    pdal_decimation_step: int = PDAL_DECIMATION_STEP
    pdal_output_type: str = PDAL_OUTPUT_TYPE
    pdal_solape_voxel: float = PDAL_SOLAPE_VOXEL

    # ── Post‑procesado ──
    gaussian_blur_sigma: float = GAUSSIAN_BLUR_SIGMA
    padding_reflect_px: int = PADDING_REFLECT_PX
    interpolation_method: str = INTERPOLATION_METHOD

    # ── Parámetros específicos de derivados ──
    sigma_curvature: float = 2.0
    ridge_valley_radios: Optional[List[float]] = None
    mrvbf_scales: Optional[List[float]] = None

    # ── Exportación ──
    generar_imagenes_png: bool = GENERAR_IMAGENES_PNG
    normalizar_imagenes: bool = NORMALIZAR_IMAGENES
    png_perc_low: float = PNG_PERC_LOW
    png_perc_high: float = PNG_PERC_HIGH
    exportar_stack: bool = EXPORTAR_STACK_MULTIBANDA
    normalizar_stack: bool = NORMALIZAR_STACK
    stack_perc_low: float = STACK_PERC_LOW
    stack_perc_high: float = STACK_PERC_HIGH
    incluir_mascara_stack: bool = INCLUIR_MASCARA_STACK
    generar_metadatos_json: bool = GENERAR_METADATOS_JSON
    generar_manifiesto_ia: bool = GENERAR_MANIFIESTO_IA

    def __post_init__(self) -> None:
        """Valida los parámetros después de la inicialización automática."""
        if self.resolucion <= 0:
            raise ValueError("La resolución debe ser > 0")
        if self.tamano_bloque < 256:
            raise ValueError("El tamaño de bloque debe ser >= 256 píxeles")
        if self.algoritmo_suelo not in ('smrf', 'csf', 'none'):
            raise ValueError(f"Algoritmo de suelo no válido: {self.algoritmo_suelo}")
        if not all(r > 0 for r in self.radio_tpi_multiescala):
            raise ValueError("Todos los radios TPI deben ser positivos")
        if not all(0 <= a < 360 for a in self.angulos_multidir):
            raise ValueError("Los ángulos multidireccionales deben estar en [0, 360)")
        if self.smrf_window < 1:
            raise ValueError("smrf_window debe ser >= 1")
        if not 0 < self.smrf_slope <= 1:
            raise ValueError("smrf_slope debe estar en (0, 1]")
        if not 0 < self.smrf_threshold <= 5:
            raise ValueError("smrf_threshold debe estar en (0, 5]")
        if self.memoria_max_mb < 512:
            raise ValueError("memoria_max_mb debe ser >= 512 MB")
        if self.pdal_decimation_step < 1 or self.pdal_decimation_step > 10:
            raise ValueError("pdal_decimation_step debe estar en [1, 10]")
        if self.pdal_output_type not in ('idw', 'mean', 'min', 'max'):
            raise ValueError(f"pdal_output_type no válido: {self.pdal_output_type}")
        if self.padding_reflect_px < 0 or self.padding_reflect_px > 500:
            raise ValueError("padding_reflect_px debe estar en [0, 500]")
        if self.gaussian_blur_sigma < 0 or self.gaussian_blur_sigma > 10:
            raise ValueError("gaussian_blur_sigma debe estar en [0, 10]")
        if self.interpolation_method not in ('linear', 'invdist'):
            raise ValueError("interpolation_method debe ser 'linear' o 'invdist'")
        if self.mrvbf_scales is not None and not all(s > 0 for s in self.mrvbf_scales):
            raise ValueError("Todas las escalas MRVBF deben ser positivas")

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a un diccionario (para guardar perfiles)."""
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfiguracionProcesamiento':
        """
        Crea una instancia a partir de un diccionario, ignorando claves extra.

        Args:
            data: Diccionario con parámetros.

        Returns:
            Instancia de ConfiguracionProcesamiento.
        """
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


# ============================================================================
# Configuración de Colada (postprocesado IA)
# ============================================================================

@dataclass
class ConfiguracionColada:
    """
    Configuración para el entrenamiento e inferencia de Colada.

    Attributes:
        in_channels: Número de bandas de entrada.
        latent_dim: Dimensión del espacio latente.
        features: Número base de filtros convolucionales.
        tamanio_parche: Tamaño del parche en píxeles.
        epocas: Número de épocas de entrenamiento.
        batch_size: Tamaño del lote.
        learning_rate: Tasa de aprendizaje.
        k_trim: Fracción de píxeles a recortar en trimmed MSE.
        kl_weight: Peso del término KL en la pérdida.
        val_split: Fracción de datos para validación.
        patience: Épocas sin mejora para early stopping.
        seed: Semilla aleatoria.
        patches_per_epoch: Número de parches por época.
        max_cache_size: Número de archivos en caché LRU.
        num_workers_dataloader: Trabajadores para DataLoader.
        solapamiento: Solapamiento entre parches (píxeles).
        tamanio_lote: Tamaño de lote para inferencia.
        sigma_gaussiano: Sigma para suavizado de mapa de anomalías.
        umbral_percentil: Percentil para umbralizar anomalías.
        ventana_adaptativa: Tamaño de ventana para umbral adaptativo (0 = global).
        aspect_ratio_max: Relación de aspecto máxima para polígonos.
        circularity_min: Circularidad mínima para polígonos.
        modelo_prediccion: 'vae' o 'isolation_forest'.
        usar_gpu: Usar GPU para inferencia.
        max_gpu_workers: Número máximo de procesos GPU.
        cpu_workers: Número de hilos CPU.
        if_n_estimators: Número de árboles para Isolation Forest.
        if_contamination: Contaminación esperada.
        if_max_samples: Máximo de muestras por árbol.
    """

    # ── Parámetros del modelo VAE ──
    in_channels: int = VAE_IN_CHANNELS
    latent_dim: int = VAE_LATENT_DIM
    features: int = VAE_FEATURES
    tamanio_parche: int = TAMANO_PARCHE

    # ── Hiperparámetros de entrenamiento ──
    epocas: int = EPOCAS
    batch_size: int = BATCH_SIZE
    learning_rate: float = LEARNING_RATE
    k_trim: float = K_TRIM
    kl_weight: float = KL_WEIGHT
    val_split: float = VAL_SPLIT
    patience: int = PATIENCE
    seed: int = SEED
    patches_per_epoch: int = PATHS_PER_EPOCH
    max_cache_size: int = MAX_CACHE_SIZE
    num_workers_dataloader: int = 0

    # ── Inferencia y detección ──
    solapamiento: int = SOLAPAMIENTO
    tamanio_lote: int = TAMANIO_LOTE
    sigma_gaussiano: float = SIGMA_GAUSSIANO
    umbral_percentil: float = UMBRAL_PERCENTIL
    ventana_adaptativa: int = VENTANA_ADAPTATIVA
    aspect_ratio_max: float = ASPECT_RATIO_MAX
    circularity_min: float = CIRCULARITY_MIN
    modelo_prediccion: str = MODELO_PREDICCION

    # ── Hardware ──
    usar_gpu: bool = USAR_GPU
    max_gpu_workers: int = MAX_GPU_WORKERS
    cpu_workers: int = CPU_WORKERS

    # ── Parámetros de Isolation Forest (si se usa) ──
    if_n_estimators: int = 100
    if_contamination: float = 0.05
    if_max_samples: int = 50000

    def __post_init__(self) -> None:
        """Valida los parámetros."""
        if self.in_channels < 1:
            raise ValueError("in_channels debe ser >= 1")
        if self.latent_dim < 1:
            raise ValueError("latent_dim debe ser >= 1")
        if self.features < 4:
            raise ValueError("features debe ser >= 4")
        if self.tamanio_parche < 32:
            raise ValueError("tamanio_parche debe ser >= 32")
        if self.epocas < 1:
            raise ValueError("epocas debe ser >= 1")
        if self.batch_size < 1:
            raise ValueError("batch_size debe ser >= 1")
        if not 0 < self.learning_rate < 1:
            raise ValueError("learning_rate debe estar entre 0 y 1")
        if not 0 <= self.val_split < 1:
            raise ValueError("val_split debe estar en [0, 1)")
        if self.patience < 1:
            raise ValueError("patience debe ser >= 1")
        if self.solapamiento < 0 or self.solapamiento >= self.tamanio_parche:
            raise ValueError("solapamiento debe ser menor que tamanio_parche")
        if self.tamanio_lote < 1:
            raise ValueError("tamanio_lote debe ser >= 1")
        if not 0 < self.sigma_gaussiano <= 10:
            raise ValueError("sigma_gaussiano debe estar en (0, 10]")
        if not 0 < self.umbral_percentil <= 100:
            raise ValueError("umbral_percentil debe estar en (0, 100]")
        if self.max_gpu_workers < 1:
            raise ValueError("max_gpu_workers debe ser >= 1")
        if self.cpu_workers < 1:
            raise ValueError("cpu_workers debe ser >= 1")
        if self.modelo_prediccion not in ('vae', 'isolation_forest'):
            raise ValueError("modelo_prediccion debe ser 'vae' o 'isolation_forest'")

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario."""
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfiguracionColada':
        """Crea una instancia desde un diccionario."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)