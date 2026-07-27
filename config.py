"""
Configuración global del plugin Arqueo-CID v1.0
================================================

Unifica todos los parámetros, rutas y constantes para los submódulos Tizona
(preprocesado LiDAR) y Colada (postprocesado con IA). Todas las rutas son
absolutas y se calculan dinámicamente respecto al directorio de QGIS.

Este archivo NO contiene código de comprobación de dependencias.
Dichas comprobaciones residen en `utils/entorno.py`.
"""

import multiprocessing
import os
from typing import Any, Union

from qgis.core import QgsApplication

# ============================================================================
# 0. CONSTANTES DE ENTORNO Y LOGGING
# ============================================================================

LOG_DIR = os.path.join(QgsApplication.qgisSettingsDirPath(), 'logs', 'arqueocid')
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_LEVEL = 'INFO'
LOG_FORMATO = '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
LOG_FORMATO_FECHA = '%Y-%m-%d %H:%M:%S'
ROOT_LOGGER_NAME = "ArqueoCid"
NOMBRE_PLUGIN = "Arqueo Cid"
NOMBRE_PREPROCESAR = "TIZONA"
NOMBRE_POSTPROCESAR = "COLADA"

# Configuración de logging por módulo
# Cada entrada define: archivo de log, nivel de consola y nivel para el panel de QGIS
LOGGING_MODULE_CONFIG: dict[str, dict[str, Any]] = {
    'Tizona': {
        'log_file': 'tizona.log',
        'console_level': 30,
        'qgis_level': 20,
    },
    'Colada': {
        'log_file': 'colada.log',
        'console_level': 30,
        'qgis_level': 20,
    },
    'ArqueoCid': {
        'log_file': 'arqueocid.log',
        'console_level': 20,
        'qgis_level': 20,
    },
}

# ============================================================================
# 1. IDENTIFICACIÓN DEL PLUGIN
# ============================================================================

VERSION_PLUGIN = "1.0.0"
NOMBRE_CAMPO_TESELA = "FICHERO"

# ============================================================================
# 2. COLORES CORPORATIVOS (Paleta UCO - Universidad de Córdoba)
# ============================================================================
# Colores extraídos del logotipo oficial (Azul añil, Rojo granate, Amarillo)

# -- Fondos, Textos y Bordes --
COLOR_FONDO = "#FFFFFF"         # Fondo general de las ventanas
COLOR_TEXTO = "#333333"         # Texto estándar (leíble)
COLOR_BORDE = "#CCCCCC"         # Bordes de QLineEdit y separadores

# -- Acción Principal (Aceptar, Buscar, Títulos) --
COLOR_PRIMARIO = "#2C265C"      # Azul UCO
COLOR_PRIMARIO_HOVER = "#1A1638" # Azul UCO más oscuro (para cuando pasas el ratón)

# -- Acción Secundaria / Negativa (Cancelar, Borrar) --
COLOR_SECUNDARIO = "#A61B2B"    # Rojo UCO
COLOR_SECUNDARIO_HOVER = "#7A141F" # Rojo UCO más oscuro (para cuando pasas el ratón)

# -- Detalles y Avisos (Opcional) --
COLOR_ACENTO = "#F2A900"        # Amarillo UCO (útil para resaltar elementos o advertencias)

# ============================================================================
# 3. RECURSOS DEL SISTEMA (CPU, MEMORIA)
# ============================================================================

CPU_CORES = multiprocessing.cpu_count()
MAX_PROCESOS_SIMULTANEOS = max(1, CPU_CORES // 2)
MAX_HILOS_TOTALES = min(CPU_CORES, 8)
MIN_MEMORIA_LIBRE_MB = 1024

MAX_GPU_WORKERS = 2
CPU_WORKERS = 1
MAX_CACHE_SIZE = 5
MAX_SAMPLE_PIXELS = 200_000
NUM_WORKERS_DATALOADER = 0

# ============================================================================
# 4. DESCARGA DE DATOS DEL CNIG
# ============================================================================

CNIG_HOST = "centrodedescargas.cnig.es"
URL_HOME = f"https://{CNIG_HOST}/CentroDescargas/home"
URL_BUSQUEDA = f"https://{CNIG_HOST}/CentroDescargas/resultados-busqueda"
URL_ARCHIVOS_SERIE = f"https://{CNIG_HOST}/CentroDescargas/archivosTotalesSerie"
URL_INIT_DESCARGA = f"https://{CNIG_HOST}/CentroDescargas/initDescargaDir"
URL_DESCARGA = f"https://{CNIG_HOST}/CentroDescargas/descargaDir"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Origin": f"https://{CNIG_HOST}",
    "Referer": URL_HOME
}
MAX_INTENTOS_DESCARGA = 8
TIMEOUT_REQUESTS = 30
TIMEOUT_DESCARGA = 120
DESCARGAS_SIMULTANEAS = 4
CHUNK_SIZE_DESCARGA = 1024 * 1024
MIN_FILE_SIZE_BYTES = 512
RETRY_TOTAL = 3
RETRY_BACKOFF_FACTOR = 0.5
RETRY_STATUS_FORCELIST = [500, 502, 503, 504]
POOL_CONNECTIONS = 10
POOL_MAXSIZE = 10

COBERTURA_A_URL_PRODUCTO: dict[Union[int, str], str] = {
    1: 'lidar-primera-cobertura',
    2: 'lidar-segunda-cobertura',
    3: 'lidar-tercera-cobertura',
    'todas': 'lidar-segunda-cobertura'
}
CNIG_MENCIONES_POR_PRODUCTO = {
    'lidar-primera-cobertura': 'LiDAR 1ª Cobertura',
    'lidar-segunda-cobertura': 'LiDAR 2ª Cobertura',
    'lidar-tercera-cobertura': 'LiDAR 3ª Cobertura'
}
CNIG_TEXTO_LICENCIA = (
    "El <b>uso de la información de los productos y servicios de datos geográficos</b> definidos en la "
    "<a class=\"link\" href=\"https://www.boe.es/boe/dias/2015/12/26/pdfs/BOE-A-2015-14129.pdf\" target=\"_blank\"> "
    "Orden FOM/2807/2015</a>, así como sus <b>derivados</b>, conlleva la aceptación por el usuario de las "
    "condiciones generales de dicha orden..."
)

# ============================================================================
# 5. TIZONA – PARÁMETROS DE PROCESAMIENTO LiDAR
# ============================================================================

RESOLUCION_MDT = 0.5
Z_FACTOR_HILLSHADE = 1.5
RADIO_OPENNESS = 10.0
RADIO_LRM = 20.0
RADIO_TPI_MULTIESCALA = [5, 15, 30]
HILLSHADE_MULTIDIR = True
ANGULOS_MULTIDIR = [315, 45, 135, 225]

DERIVADOS_POR_DEFECTO = [
    'hillshade', 'slope', 'curvature', 'curvature_vert', 'curvature_horiz',
    'lrm', 'openness_pos', 'openness_neg', 'openness_aniso', 'sky_view_factor',
    'tpi', 'ridge_valley', 'mrvbf', 'aspect_sin', 'aspect_cos'
]

DERIVADOS_DESCRIPCIONES: dict[str, str] = {
    'hillshade': 'Sombreado del relieve clásico/multidireccional.',
    'slope': 'Pendiente en grados.',
    'aspect_sin': 'Seno de la orientación (componente N‑S).',
    'aspect_cos': 'Coseno de la orientación (componente E‑W).',
    'curvature': 'Curvatura general (Laplaciana).',
    'curvature_vert': 'Curvatura vertical (perfil).',
    'curvature_horiz': 'Curvatura horizontal (planta).',
    'tpi': 'Índice de Posición Topográfica (multiescala).',
    'lrm': 'Modelo de Relieve Local (elimina tendencia regional).',
    'ridge_valley': 'Detección de crestas/valles (Hessiano multiescala).',
    'openness_pos': 'Apertura positiva (dominancia de picos).',
    'openness_neg': 'Apertura negativa (dominancia de fosos).',
    'openness_aniso': 'Apertura anisotrópica (Experimental).',
    'sky_view_factor': 'Factor de visión del cielo (basado en pendiente).',
    'mrvbf': 'Índice multiescala de planitud de fondos de valle (MRVBF).'
}

DERIVADOS_CATEGORIAS: dict[str, list[str]] = {
    "Básicos y Relieve": ['hillshade', 'slope'],
    "Curvaturas": ['curvature', 'curvature_vert', 'curvature_horiz'],
    "Posición Topográfica": ['tpi', 'lrm', 'ridge_valley'],
    "Visibilidad y Aperturas": ['openness_pos', 'openness_neg', 'openness_aniso', 'sky_view_factor'],
    "Hidrología": ['mrvbf'],
    "Orientación (IA)": ['aspect_sin', 'aspect_cos']
}

DERIVADOS_COMPATIBLES_BLOQUES = [
    'hillshade', 'slope', 'aspect_sin', 'aspect_cos',
    'curvature', 'curvature_vert', 'curvature_horiz',
    'tpi', 'lrm', 'ridge_valley',
    'openness_pos', 'openness_neg', 'openness_aniso',
    'sky_view_factor'
]

SIGMA_CURVATURE_DEFAULT = 2.0
RIDGE_VALLEY_RADIOS_DEFAULT = [10.0, 20.0, 30.0]
MRVBF_SCALES_DEFAULT = [5.0, 10.0, 20.0, 40.0]
MRVBF_SLOPE_THRESHOLD_DEFAULT = 5.0

ALGORITMO_FILTRADO_SUELO = 'smrf'
USAR_CLASIFICACION_EXISTENTE = True
SMRF_WINDOW = 18
SMRF_SLOPE = 0.15
SMRF_THRESHOLD = 0.5
SMRF_SCALAR_DEFAULT = 1.2

SMRF_DEFAULT_WINDOW = SMRF_WINDOW
SMRF_DEFAULT_SLOPE = SMRF_SLOPE
SMRF_DEFAULT_THRESHOLD = SMRF_THRESHOLD
SMRF_DEFAULT_SCALAR = SMRF_SCALAR_DEFAULT

INTERPOLATION_METHOD = 'linear'
USAR_PDAL = True
PDAL_TIMEOUT = 1800
PDAL_DECIMATION_STEP = 2
PDAL_OUTPUT_TYPE = 'idw'
PDAL_SOLAPE_VOXEL = 0.1
PDAL_VERSION_TIMEOUT = 5
GDAL_GRID_METHOD = INTERPOLATION_METHOD
GDAL_GRID_RADIUS1_FACTOR = 4.0
GDAL_GRID_RADIUS2_FACTOR = 10.0
GDAL_GRID_SMOOTHING = 0.2
GDAL_GRID_COMPRESSION_OPTS = ['COMPRESS=LERC_ZSTD', 'PREDICTOR=3', 'TILED=YES', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256']
PDAL_RASTER_OUTPUT_TYPE = 'idw'
PDAL_GDAL_DRIVER = 'GTiff'
PDAL_GDAL_DATA_TYPE = 'float32'
PDAL_GDAL_OPTS = 'COMPRESS=LERC_ZSTD,PREDICTOR=3,NUM_THREADS=ALL_CPUS,TILED=YES,BLOCKXSIZE=256,BLOCKYSIZE=256'

RBF_MAX_POINTS = 20000
RBF_KERNEL = 'thin_plate_spline'
RBF_BLOCK_SIZE = 50000
IDW_K_NEIGHBORS = 16
IDW_DISTANCE_UPPER_BOUND = 50.0
IDW_SIGMA_FACTOR = 5.0
MIN_PUNTOS_SUELO = 1000
BILATERAL_SIGMA_COLOR = 0.1
BILATERAL_SIGMA_SPATIAL = 1.5

GAUSSIAN_BLUR_SIGMA = 1.0
PADDING_REFLECT_PX = 60

USAR_PROCESAMIENTO_BLOQUES = True
TAMANO_BLOQUE = 2048
MEMORIA_MAX_MB = 4096
MAX_HILOS_PROCESAMIENTO = 4
USAR_GPU = True
SOLAPE_PORCENTAJE = 0.4
BLEND_WIDTH_DEFAULT = 20
RADIO_RIDGE_VALLEY_ESTIMADO = 30.0
TAMANO_BLOQUE_MIN = 256
TAMANO_BLOQUE_MAX = 4096
TAMANO_BLOQUE_ALINEACION = 128
BYTES_POR_PIXEL_ESTIMADO = 5 * 4
FRACCION_VRAM_USAR = 0.8
FRACCION_BLOQUE_UNICO = 1.0
VENTANA_ESCRITURA_FINAL = 512
APLICAR_FILTRO_MEDIANA_BLOQUES = True

GENERAR_IMAGENES_PNG = True
NORMALIZAR_IMAGENES = True
PNG_PERC_LOW = 2.0
PNG_PERC_HIGH = 98.0
EXPORTAR_STACK_MULTIBANDA = True
NORMALIZAR_STACK = True
STACK_PERC_LOW = 1.0
STACK_PERC_HIGH = 99.0
INCLUIR_MASCARA_STACK = False
GENERAR_METADATOS_JSON = True
GENERAR_MANIFIESTO_IA = True
TIFF_COMPRESSION = "LERC_ZSTD"
TIFF_PREDICTOR = 3
TIFF_TILED = True
TIFF_BLOCK_SIZE = 256
TIFF_NUM_THREADS = "ALL_CPUS"
APLICAR_FILTRO_MEDIANA_DERIVADOS = True
FILTRO_MEDIANA_TAMANO = 3
DERIVADOS_FILTRO_MEDIANA = ("tpi", "lrm", "curvature", "curvature_vert", "curvature_horiz", "openness_pos", "openness_neg", "openness_aniso", "mrvbf", "ridge_valley")
EXPORTAR_PNG_MAX_WORKERS = 4
EXPORTAR_STACK_NODATA = -9999.0
EXPORTAR_STACK_COMPRESSION = "LERC_ZSTD"
EXPORTAR_STACK_PREDICTOR = 3
CALIDAD_MDT_SLOPE_THRESHOLD = 5.0

MAX_VRAM_FRACTION = 0.6
RIDGE_VALLEY_SIGMAS_DEFAULT = [10.0, 20.0, 30.0]
SKY_VIEW_FACTOR_METHOD = 'slope'

CACHE_SUELO_DIR = os.path.join(QgsApplication.qgisSettingsDirPath(), 'cache', 'tizona_suelo')

ETAPA_SUELO = "suelo"
ETAPA_MDT = "mdt"
ETAPA_DERIVADOS = "derivados"
ETAPA_EXPORTACION = "exportación"

# ============================================================================
# 6. COLADA – PARÁMETROS DE POSTPROCESADO (IA)
# ============================================================================

TAMANO_PARCHE = 256
SOLAPAMIENTO = 128
SIGMA_GAUSSIANO = 1.5
UMBRAL_PERCENTIL = 98
TAMANIO_LOTE = 16

VAE_IN_CHANNELS = 10
VAE_LATENT_DIM = 64
VAE_FEATURES = 32

EPOCAS = 200
BATCH_SIZE = 16
LEARNING_RATE = 1e-4
K_TRIM = 0.02
KL_WEIGHT = 0.001
VAL_SPLIT = 0.2
PATIENCE = 5
SEED = 42
PATHS_PER_EPOCH = 5000

VENTANA_ADAPTATIVA = 250
ASPECT_RATIO_MAX = 5.0
CIRCULARITY_MIN = 0.6
MODELO_PREDICCION = 'vae'

FILTRO_GAUSSIAN_SIGMA_DEFAULT = 1.0
FILTRO_MEDIAN_SIZE_DEFAULT = 3
FILTRO_CANNY_SIGMA_DEFAULT = 1.0
FILTRO_CANNY_LOW_DEFAULT = 0.1
FILTRO_CANNY_HIGH_DEFAULT = 0.2

ISOLATION_FOREST_N_ESTIMATORS = 100
ISOLATION_FOREST_CONTAMINATION = 0.05
ISOLATION_FOREST_MAX_SAMPLES = 50000
MIN_AREA_ANOMALIA_M2 = 4.0

SSIM_DATA_RANGE = 1.0
SSIM_SIZE_AVERAGE = True
CLIP_GRAD_NORM = 1.0
VALIDATION_PATCHES_FACTOR = 0.25
VALIDATION_PATCHES_MAX = 1000
PERCENTILES_LOW = 1.0
PERCENTILES_HIGH = 99.0
PERCENTILES_SAMPLES_PER_FILE = 20000

# ============================================================================
# 7. INTEGRACIÓN – CARPETAS Y PERFILES
# ============================================================================

CARPETA_MDT = "01_MDT"
CARPETA_DERIVADOS = "02_DERIVADOS"
CARPETA_IMAGENES = "03_PNG"
CARPETA_STACKS = "04_IA_STACKS"
CARPETA_IA_STACKS = CARPETA_STACKS

_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))

PERFILES_SISTEMA = {
    'tizona': os.path.join(_PLUGIN_ROOT, 'resources', 'perfiles', 'tizona'),
    'colada': os.path.join(_PLUGIN_ROOT, 'resources', 'perfiles', 'colada'),
}

PERFILES_USUARIO = {
    'tizona': os.path.join(os.path.expanduser("~"), 'tizona_perfiles'),
    'colada': os.path.join(os.path.expanduser("~"), 'colada_perfiles'),
}

# ============================================================================
# 8. BUSCADOR DE LUGARES (Nominatim)
# ============================================================================

BUSCADOR_TITULO = "Buscador Arqueo Cid"
BUSCADOR_MIN_WIDTH = 420
BUSCADOR_MIN_HEIGHT = 180
BUSCADOR_PLACEHOLDER = "Ej: Mérida, Atapuerca, Numancia..."
BUSCADOR_ZOOM_SCALE = 50000

NOMINATIM_USER_AGENT = "Plugin_ArqueoCid_QGIS"
NOMINATIM_TIMEOUT = 5
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"

MENSAJE_CAMPO_VACIO = "Escribe el nombre de un lugar."
MENSAJE_ERROR_RED = "Hubo un problema al conectar con el servidor de búsqueda. Comprueba tu conexión a internet."
MENSAJE_SIN_RESULTADOS = "No se encontró el lugar: {}"
MENSAJE_BUSCANDO = "Buscando '{}'..."
MENSAJE_LLEGADA = "¡Llegada a {}! Pasa el ratón sobre los cuadrados para ver su nombre."

# ============================================================================
# 9. VISOR DE TESELAS (mallas PNOA)
# ============================================================================

NOMBRE_CAPA_TESELAS = "Teselas PNOA LiDAR"
DIR_MALLAS_BASE = os.path.join(_PLUGIN_ROOT, 'resources', 'mallas')
ESTILO_TESELAS = {
    "color": "0,0,0,0",
    "outline_color": "0,0,0,100",
    "outline_width": "0.5",
    "outline_style": "solid",
}

# 1. UNIFICADO: Lista única de campos ordenada por prioridad (el primero manda)
CAMPOS_MAPTIP = ["FICHERO", "fichero", "HOJA", "hoja", "Name", "NAME"]

# 2. ESTILO EXTRAÍDO: Para que sea muy fácil cambiar colores, bordes o fuentes
ESTILO_MAPTIP_CONTENEDOR = (
    "background-color: rgba(40, 44, 52, 0.95);"
    "padding: 8px 12px;"
    "border-radius: 6px;"
    "font-family: 'Segoe UI', Arial, sans-serif;"
    "font-size: 13px;"
    "border: 1px solid #3e4451;"
    "box-shadow: 2px 2px 8px rgba(0, 0, 0, 0.3);"
    "display: flex;"
    "align-items: center;"
)

# 3. HTML LIMPIO: Usa el estilo de arriba y diferencia colores (f-string)
# Nota: Usamos {{}} para que Python lo deje como {} listo para usar con .format()
MAPTIP_HTML_TEMPLATE = f"""
<div style="{ESTILO_MAPTIP_CONTENEDOR}">
    <span style="font-size: 15px; margin-right: 6px;"></span>
    <strong style="color: #abb2bf; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;">Tesela:</strong>
    <span style="color: #98c379; margin-left: 6px; font-weight: 600; font-size: 14px;">[% "{{}}" %]</span>
</div>
"""
# ==============================================================================
# SISTEMAS DE COORDENADAS (CRS)
# ------------------------------------------------------------------------------
# ¿Por qué usamos dos distintos?
# 1. QGIS y PNOA (EPSG:25830): Nuestro mapa de España y las mallas trabajan en
#    METROS. Es necesario para que el mapa sea plano y no se deformen las distancias.
# 2. Internet / Nominatim (EPSG:4326): La API del buscador es global y siempre
#    devuelve las coordenadas GPS en GRADOS (Latitud/Longitud).
#
# El código del buscador usa ambas para "traducir" el punto (grados) de internet
# a la pantalla plana del proyecto (metros).
# ==============================================================================

# Usado para el mapa de QGIS, la ortofoto y la fusión de teselas (Mide en Metros)
CRS_FUSION_TESELAS = "EPSG:25830"

# Usado para interpretar los datos que llegan de la API del buscador (Mide en Grados)
CRS_BUSCADOR_WGS84 = "EPSG:4326"
# ============================================================================
# 10. DIÁLOGO DE COBERTURA PNOA
# ============================================================================

TITULO_DIALOGO_COBERTURA = "Selección de cobertura PNOA"
TAMANO_MIN_COBERTURA_ANCHO = 450
TAMANO_MIN_COBERTURA_ALTO = 250
OPCIONES_COBERTURA = {
    "1": "1ª cobertura (2009‑2015)",
    "2": "2ª cobertura (2015‑2022)",
    "3": "3ª cobertura (2022‑actualidad)",
    "todas": "Todas las coberturas"
}

COBERTURA_DEFAULT = 1

TEXTO_CABECERA_COBERTURA = "Seleccione la cobertura LiDAR"
TEXTO_BOTON_ACEPTAR = "Cargar malla"
TEXTO_BOTON_CANCELAR = "Cancelar"

# ============================================================================
# 11. ESTILOS COMUNES DE BOTÓN
# ============================================================================

_BOTON_PRINCIPAL_STYLE = (
    f"background-color: {COLADA_COLOR_PRIMARIO_OSC}; color: white; "
    f"border: 2px solid {COLADA_COLOR_PRIMARIO}; padding: 8px 16px; "
    "font-size: 13px; border-radius: 6px; font-weight: bold;"
)

_BOTON_SECUNDARIO_STYLE = (
    f"background-color: {COLADA_COLOR_PRIMARIO_OSC}; color: white; "
    f"border: 1px solid {COLADA_COLOR_PRIMARIO_OSC}; padding: 4px 10px; "
    "border-radius: 4px; font-weight: bold; font-size: 11px;"
)

_BOTON_NORMAL_STYLE = (
    f"background-color: {COLADA_COLOR_PRIMARIO}; color: white; "
    f"border: 1px solid {COLADA_COLOR_PRIMARIO_OSC}; padding: 4px 12px; "
    "border-radius: 4px; font-weight: bold; font-size: 11px;"
)

# ============================================================================
# 12. CONSTANTES DE INTERFAZ – TIZONA
# ============================================================================

TIZONA_DIALOG_WIDTH = 950
TIZONA_DIALOG_HEIGHT = 650

MODOS_EJECUCION = ["Descargar y procesar", "Solo descarga", "Solo procesamiento"]
MODO_EJECUCION_DEFAULT = "Descargar y procesar"
COBERTURAS_ETIQUETAS = ["1ª cobertura", "2ª cobertura", "3ª cobertura"]
TIPO_PRODUCTO_OPCIONES_POR_COBERTURA = {0: ["COL", "CIR", "Ambos"], 1: ["RGB", "IRC", "Ambos"], 2: ["Todos"]}
TIPO_PRODUCTO_DEFAULT = "IRC"
LIMPIAR_DESCARGAS_DEFAULT = False
LIMPIAR_PROCESADOS_DEFAULT = False
ALGORITMO_SUELO_DEFAULT = "smrf"
USAR_GDAL_DEFAULT = False
USAR_GPU_DEFAULT = False
COMBO_POPUP_STYLE = """
    QComboBox QAbstractItemView {
        color: black;
        background: white;
        selection-background-color: #d0ece7;
        selection-color: black;
    }
    QComboBox QAbstractItemView::item:hover {
        background-color: #d0ece7;
        color: black;
    }
"""
MENSAJE_RUTA_DESCARGA_VACIA = "Debe seleccionar una carpeta para las descargas."
MENSAJE_RUTA_RESULTADOS_VACIA = "Debe seleccionar una carpeta para guardar los resultados."
MENSAJE_RESTABLECER_CONFIRMACION = "¿Desea restablecer todos los valores a sus valores por defecto?"

PROGRESO_DIALOG_WIDTH = 960
PROGRESO_DIALOG_HEIGHT = 680
PROGRESO_TITULO_DEFAULT = "Procesando..."
PROGRESO_TEXTO_CABECERA = "Progreso de la Operación"
PROGRESO_LABEL_DESCARGA = "Descarga de archivos LAZ"
PROGRESO_LABEL_PROCESAMIENTO = "Procesamiento global"
PROGRESO_GRUPO_TESELAS = "Estado por tesela"
PROGRESO_GRUPO_LOG = "Registro"
PROGRESO_COLUMNAS_TESELAS = ["Tesela", "Estado", "Progreso"]
PROGRESO_BOTON_COLADA_TEXTO = "Abrir en Colada"
PROGRESO_BOTON_COLADA_TOOLTIP = "Abre los resultados en Colada para inspección y filtros."
PROGRESO_BOTON_CANCELAR_TEXTO = "Cancelar"
PROGRESO_BOTON_CERRAR_TEXTO = "Cerrar"
PROGRESO_CANCELANDO_TEXTO = "Cancelando…"
PROGRESO_FORMATO_TIEMPO = "Tiempo total: {:.1f} min"
PROGRESO_LOG_COLORES = {"error": "#CC0000", "warning": "#CC6600", "info": COLOR_PRIMARIO_OSC}
PROGRESO_CHUNK_STYLE = f"QProgressBar::chunk {{ background-color: {COLOR_PRIMARIO}; }}"
PROGRESO_BAR_STYLE = f"QProgressBar {{ border: 1px solid {COLOR_BORDE}; }}"

TAB_DATOS_LABEL_MODO = "Modo de ejecución:"
TAB_DATOS_TOOLTIP_MODO = "Elige si quieres descargar, procesar archivos locales o ambas cosas.\nEl filtro por tipo de producto solo se aplica en modos de descarga."
TAB_DATOS_LABEL_CARPETA_LAZ = "Carpeta de LAZ:"
TAB_DATOS_TOOLTIP_CARPETA_LAZ = "Ruta donde se guardan los archivos LAZ descargados del CNIG.\nEn modo 'Solo procesamiento', aquí se buscan los archivos locales."
TAB_DATOS_LABEL_CARPETA_RESULTADOS = "Carpeta de Resultados:"
TAB_DATOS_TOOLTIP_CARPETA_RESULTADOS = "Ruta donde se guardarán todos los resultados: MDT, derivados, imágenes PNG y stacks IA."
TAB_DATOS_CHECK_LIMPIAR_DESCARGAS = "Limpiar directorio antes"
TAB_DATOS_CHECK_LIMPIAR_PROCESADOS = "Limpiar directorio antes"
TAB_DATOS_TOOLTIP_LIMPIAR = "Borra todo el contenido de la carpeta antes de empezar."
TAB_DATOS_LABEL_COBERTURA = "Cobertura:"
TAB_DATOS_TOOLTIP_COBERTURA = "Elige la cobertura LiDAR a procesar.\nDetermina el tipo de producto disponible para filtrar en la descarga."
TAB_DATOS_LABEL_TIPO_PRODUCTO = "Variante LiDAR:"
TAB_DATOS_TOOLTIP_TIPO_PRODUCTO = "Elige qué variante de LiDAR descargar.\nLos archivos siempre se guardan como .laz.\nSolo se aplica en modos de descarga."
TAB_DATOS_CHECK_PNG = "Generar imágenes PNG de cada derivado (8 bits)"
TAB_DATOS_TOOLTIP_PNG = "Crea una imagen PNG por cada derivado generado, útil para visualización rápida."
TAB_DATOS_CHECK_NORM_PNG = "Normalizar imágenes"
TAB_DATOS_TOOLTIP_NORM_PNG = "Aplica normalización de contraste a las imágenes PNG para mejorar la visualización."
TAB_DATOS_LABEL_PNG_BAJO = "Bajo:"
TAB_DATOS_LABEL_PNG_ALTO = "Alto:"
TAB_DATOS_TOOLTIP_PERCENTIL_BAJO = "Percentil inferior para normalizar las imágenes PNG."
TAB_DATOS_TOOLTIP_PERCENTIL_ALTO = "Percentil superior para normalizar las imágenes PNG."
TAB_DATOS_CHECK_STACK = "Generar Stack Multibanda (GeoTIFF multicapa)"
TAB_DATOS_TOOLTIP_STACK = "Crea un único archivo GeoTIFF con todos los derivados como bandas separadas."
TAB_DATOS_CHECK_NORM_STACK = "Normalizar stack"
TAB_DATOS_TOOLTIP_NORM_STACK = "Escala los valores del stack entre 0 y 1 usando los percentiles configurados."
TAB_DATOS_CHECK_MASCARA = "Incluir banda de máscara de píxeles válidos"
TAB_DATOS_TOOLTIP_MASCARA = "Añade una banda binaria al stack que indica qué píxeles contienen datos válidos."
TAB_DATOS_LABEL_STACK_BAJO = "Bajo:"
TAB_DATOS_LABEL_STACK_ALTO = "Alto:"
TAB_DATOS_TOOLTIP_PERCENTIL_STACK_BAJO = "Percentil inferior para normalizar el stack (winsorizado)."
TAB_DATOS_TOOLTIP_PERCENTIL_STACK_ALTO = "Percentil superior para normalizar el stack (winsorizado)."
TAB_DATOS_CHECK_JSON = "Generar metadatos JSON de la tesela"
TAB_DATOS_TOOLTIP_JSON = "Guarda un archivo JSON con los parámetros de procesamiento utilizados."
TAB_DATOS_CHECK_MANIFEST = "Actualizar manifiesto IA (ia_manifest.json)"
TAB_DATOS_TOOLTIP_MANIFEST = "Registra la tesela en el manifiesto de entrenamiento.\nSolo se activa si se genera el stack."

SIGMA_CURVATURE_RANGE = (0.5, 10.0)
SIGMA_CURVATURE_STEP = 0.5
RIDGE_VALLEY_RADIOS_SEPARATOR = ","
MRVBF_SCALES_SEPARATOR = ","
MRVBF_SLOPE_THRESHOLD_RANGE = (1.0, 15.0)
MRVBF_SLOPE_THRESHOLD_STEP = 0.5
RADIO_OPENNESS_RANGE = (1, 300)
RADIO_OPENNESS_STEP = 1
RADIO_LRM_RANGE = (5, 500)
RADIO_LRM_STEP = 1

TOOLTIP_RADIO_OPENNESS = "Radio de búsqueda (metros) para Openness y SVF."
TOOLTIP_RADIO_LRM = "Radio de búsqueda (metros) para LRM."
TOOLTIP_RADIO_TPI = "Radios en metros para el TPI multiescala, separados por comas."
TOOLTIP_ANGULOS_MULTI = "Ángulos de iluminación (grados) para el hillshade multidireccional."
TOOLTIP_SIGMA_CURVATURE = "Sigma del suavizado gaussiano previo (en píxeles)."
TOOLTIP_RIDGE_VALLEY_RADIOS = "Radios (metros) para el filtro Hessiano multiescala."
TOOLTIP_MRVBF_SCALES = "Radios (metros) para las escalas de análisis del MRVBF."
TOOLTIP_MRVBF_SLOPE_THRESHOLD = "Pendiente máxima (grados) para considerar planitud."
LABEL_RADIO_OPENNESS = "Radio Openness / SVF (m):"
LABEL_RADIO_LRM = "Radio LRM (m):"
LABEL_RADIO_TPI = "Radios TPI Multiescala (m):"
LABEL_ANGULOS_MULTI = "Ángulos Hillshade (°):"
LABEL_SIGMA_CURVATURE = "Sigma suavizado:"
LABEL_RIDGE_VALLEY_RADIOS = "Radios (m):"
LABEL_MRVBF_SCALES = "Escalas (m):"
LABEL_MRVBF_SLOPE_THRESHOLD = "Umbral pendiente (°):"
GROUP_TITLE_PARAMETROS = "Parámetros Geométricos Globales"
GROUP_TITLE_DERIVADOS = "Derivados Disponibles"
GROUP_TITLE_ESPECIFICOS = "Parámetros Específicos de Derivados"
BUTTON_SELECCIONAR_TODOS = "Seleccionar Todos"
BUTTON_DESELECCIONAR_TODOS = "Deseleccionar Todos"

FILTRO_SUELO_OPCIONES = ["SMRF (Recomendado - Simple Morphological Filter)", "CSF (Cloth Simulation Filter)", "Ninguno (usar nube cruda)"]
FILTRO_SUELO_VALORES = ["smrf", "csf", "none"]
CHECK_USAR_CLASIFICACION_TEXTO = "Aislar estrictamente Clase 2 (Terreno PNOA) antes de filtrar"
CHECK_USAR_CLASIFICACION_TOOLTIP = "Fundamental para IA. Evita que la vegetación contamine el modelo.\nSolo tiene efecto si el archivo LAZ ya tiene clasificación de suelo."
CHECK_SMRF_AVANZADO_TEXTO = "Configurar parámetros avanzados del filtro"
CHECK_SMRF_AVANZADO_TOOLTIP = "Muestra los parámetros finos del filtro SMRF/CSF (ventana, pendiente, umbral)."
LABEL_ALGORITMO = "Filtro Morfológico Adicional:"
LABEL_VENTANA = "Ventana máxima (px):"
LABEL_PENDIENTE = "Pendiente de terreno:"
LABEL_UMBRAL = "Umbral de corte (m):"
LABEL_RESOLUCION = "Resolución de salida (m/px):"
LABEL_Z_FACTOR = "Factor Z (Exageración vertical):"
LABEL_MULTIDIR = "Generar Hillshade Multidireccional por defecto"
LABEL_GAUSSIAN_SIGMA = "Suavizado Gaussiano previo (Sigma):"
LABEL_PADDING = "Padding reflectante (px):"
TOOLTIP_SMRF_WINDOW = "Tamaño máximo de la ventana de análisis (en píxeles)."
TOOLTIP_SMRF_SLOPE = "Pendiente máxima esperada del terreno."
TOOLTIP_SMRF_THRESHOLD = "Umbral de diferencia de elevación (metros)."
TOOLTIP_RESOLUCION = "Tamaño de píxel del MDT resultante en metros."
TOOLTIP_Z_FACTOR = "Multiplicador vertical para el hillshade."
TOOLTIP_MULTIDIR = "Combina iluminación desde varios ángulos."
TOOLTIP_GAUSSIAN_SIGMA = "Suaviza ligeramente el MDT antes de calcular derivados."
TOOLTIP_PADDING = "Añade un borde por reflexión antes de aplicar filtros."
SMRF_WINDOW_RANGE = (10, 100)
SMRF_WINDOW_STEP = 1
SMRF_SLOPE_RANGE = (0.05, 0.5)
SMRF_SLOPE_STEP = 0.05
SMRF_THRESHOLD_RANGE = (0.1, 2.0)
SMRF_THRESHOLD_STEP = 0.1
RESOLUCION_MDT_RANGE = (0.10, 5.0)
RESOLUCION_MDT_STEP = 0.25
Z_FACTOR_RANGE = (0.5, 5.0)
Z_FACTOR_STEP = 0.1
GAUSSIAN_SIGMA_RANGE = (0, 5.0)
GAUSSIAN_SIGMA_STEP = 0.5
PADDING_REFLECT_RANGE = (0, 200)
PADDING_REFLECT_STEP = 10
GROUP_FILTRADO_TITLE = "Filtrado de Suelo (Eliminación de Vegetación)"
GROUP_MDT_TITLE = "Parámetros del Modelo Digital del Terreno"
GROUP_SUAVIZADO_TITLE = "Anti-Artefactos y Bordes"

RENDIMIENTO_GRUPO_RED = "Operaciones de Red (Descarga CNIG)"
RENDIMIENTO_GRUPO_HARDWARE = "Motores de Aceleración Hardware"
RENDIMIENTO_GRUPO_MEMORIA = "Gestión de Memoria y CPU"
RENDIMIENTO_LABEL_DESC_SIM = "Descargas simultáneas:"
RENDIMIENTO_LABEL_TIMEOUT = "Timeout HTTP (s):"
RENDIMIENTO_LABEL_USAR_GPU = "Usar GPU (PyTorch CUDA FP16)"
RENDIMIENTO_LABEL_GPU_NO_DISP = "GPU no disponible"
RENDIMIENTO_LABEL_USAR_GDAL = "Usar GDAL nativo (Hillshade, Slope, Aspect)"
RENDIMIENTO_LABEL_GDAL_NO_DISP = "GDAL no instalado"
RENDIMIENTO_LABEL_USAR_PDAL = "Forzar generador PDAL para MDT"
RENDIMIENTO_LABEL_PDAL_DECIM = "Diezmado PDAL:"
RENDIMIENTO_LABEL_PDAL_OUT = "Interpolación PDAL:"
RENDIMIENTO_LABEL_PROC_PARALELO = "Procesar teselas concurrentemente"
RENDIMIENTO_LABEL_HILOS_TESELAS = "Hilos para teselas:"
RENDIMIENTO_LABEL_USAR_BLOQUES = "Procesar derivados en bloques (memmap)"
RENDIMIENTO_LABEL_TAM_BLOQUE = "Tamaño del bloque (px):"
RENDIMIENTO_LABEL_LIMITE_CACHE = "Límite caché (MB):"
RENDIMIENTO_LABEL_PAUSAR_RAM = "Pausar si RAM baja de (MB):"
RENDIMIENTO_LABEL_HILOS_INTERNOS = "Hilos internos (por tesela):"
RENDIMIENTO_TOOLTIP_DESC_SIM = "Número de descargas simultáneas."
RENDIMIENTO_TOOLTIP_TIMEOUT = "Tiempo máximo de espera (segundos) para cada archivo."
RENDIMIENTO_TOOLTIP_USAR_GPU = "Acelera el cálculo de derivados mediante la GPU."
RENDIMIENTO_TOOLTIP_USAR_GDAL = "Utiliza los algoritmos rápidos de GDAL."
RENDIMIENTO_TOOLTIP_USAR_PDAL = "Utiliza PDAL en lugar de GDAL para interpolar el MDT."
RENDIMIENTO_TOOLTIP_PDAL_DECIM = "Factor de diezmado de la nube de puntos."
RENDIMIENTO_TOOLTIP_PDAL_OUT = "Método de interpolación para generar el MDT."
RENDIMIENTO_TOOLTIP_PROC_PARALELO = "Permite que varias teselas se procesen a la vez."
RENDIMIENTO_TOOLTIP_HILOS_TESELAS = "Número máximo de teselas procesándose en paralelo."
RENDIMIENTO_TOOLTIP_USAR_BLOQUES = "Divide el MDT en bloques para no agotar la memoria."
RENDIMIENTO_TOOLTIP_TAM_BLOQUE = "Tamaño del bloque en píxeles."
RENDIMIENTO_TOOLTIP_LIMITE_CACHE = "Caché máxima de memoria RAM (MB) para procesamiento."
RENDIMIENTO_TOOLTIP_PAUSAR_RAM = "Si la memoria libre cae por debajo de este valor, se pausan nuevas tareas."
RENDIMIENTO_TOOLTIP_HILOS_INTERNOS = "Número de hilos internos que usa cada tesela."
RENDIMIENTO_DESC_SIM_RANGE = (1, 8)
RENDIMIENTO_DESC_SIM_STEP = 1
RENDIMIENTO_TIMEOUT_RANGE = (30, 600)
RENDIMIENTO_TIMEOUT_STEP = 10
RENDIMIENTO_PDAL_STEP_RANGE = (1, 10)
RENDIMIENTO_PDAL_STEP_STEP = 1
RENDIMIENTO_PROC_PARALELO_RANGE_MIN = 1
RENDIMIENTO_BLOQUE_RANGE = (256, 8192)
RENDIMIENTO_BLOQUE_STEP = 512
RENDIMIENTO_MEM_RANGE = (512, 32768)
RENDIMIENTO_MEM_STEP = 1024
RENDIMIENTO_MIN_MEM_RANGE = (256, 8192)
RENDIMIENTO_MIN_MEM_STEP = 512
RENDIMIENTO_HILOS_INTERNOS_RANGE_MIN = 1
RENDIMIENTO_HILOS_INTERNOS_DEFAULT = 4
RENDIMIENTO_PDAL_OUT_OPCIONES = ["idw", "mean", "min", "max"]
RENDIMIENTO_PROC_PARALELO_DEFAULT = True
RENDIMIENTO_GPU_BLOQUE_MAX_SUGERIDO = 2048
RENDIMIENTO_HILOS_INTERNOS_MAX = CPU_CORES

PERFILES_TITULO_PRINCIPAL = "Centro de Control de Perfiles"
PERFILES_DESCRIPCION = "Guarde su configuración actual en un archivo JSON reutilizable o cargue perfiles predefinidos para adaptar el flujo de trabajo."
PERFILES_GROUP_TITLE = "Perfiles Guardados"
PERFILES_BTN_CARGAR = "Aplicar Perfil Seleccionado"
PERFILES_BTN_GUARDAR = "Guardar Configuración Actual..."
PERFILES_BTN_ELIMINAR = "Eliminar Perfil"
PERFILES_BTN_IMPORTAR = "Importar perfil JSON externo..."
PERFILES_TOOLTIP_LISTA = "Perfiles disponibles.\nLos perfiles en azul y negrita son del sistema (solo lectura).\nEl resto son perfiles de usuario."
PERFILES_TOOLTIP_CARGAR = "Carga la configuración del perfil resaltado en el diálogo."
PERFILES_TOOLTIP_GUARDAR = "Guarda los ajustes actuales como un nuevo perfil de usuario."
PERFILES_TOOLTIP_ELIMINAR = "Elimina el perfil de usuario seleccionado (no se pueden borrar los del sistema)."
PERFILES_TOOLTIP_IMPORTAR = "Carga un perfil desde un archivo JSON en cualquier ubicación."
PERFILES_MSG_SELECCION_REQUERIDA = "Selección requerida"
PERFILES_MSG_SELECCIONE_PERFIL = "Seleccione un perfil de la lista."
PERFILES_MSG_EXITO = "Éxito"
PERFILES_MSG_CONFIG_CARGADA = "Configuración '{}' cargada."
PERFILES_MSG_ERROR_LECTURA = "Error de Lectura"
PERFILES_MSG_PERFIL_INVALIDO = "El archivo del perfil es inválido:\n{}"
PERFILES_MSG_IMPORTACION_EXITO = "Importación Completa"
PERFILES_MSG_PERFIL_APLICADO = "Perfil '{}' aplicado."
PERFILES_MSG_ERROR_IMPORTACION = "Error"
PERFILES_MSG_FALLO_JSON = "Fallo al abrir el JSON:\n{}"
PERFILES_MSG_ATENCION = "Atención"
PERFILES_MSG_SIN_CALLBACK = "No se puede obtener la configuración actual."
PERFILES_MSG_GUARDADO = "Guardado"
PERFILES_MSG_PERFIL_REGISTRADO = "El perfil '{}' ha quedado registrado."
PERFILES_MSG_ERROR_GUARDADO = "Error"
PERFILES_MSG_NO_GUARDADO = "No se pudo guardar:\n{}"
PERFILES_MSG_SELECCION_ELIMINAR = "Debe seleccionar un perfil para eliminarlo."
PERFILES_MSG_ACCION_DENEGADA = "Acción denegada"
PERFILES_MSG_NO_ELIMINAR_SISTEMA = "Los perfiles estándar del sistema no pueden ser eliminados."
PERFILES_MSG_BORRAR = "Borrar"
PERFILES_MSG_CONFIRMAR_BORRAR = "¿Borrar permanentemente el perfil '{}'?"
PERFILES_MSG_ERROR_ELIMINAR = "Error"
PERFILES_MSG_ELIMINAR_FALLO = "No se pudo eliminar el perfil."
PERFILES_MSG_NO_ELIMINAR = "El archivo está bloqueado o no se puede eliminar:\n{}"

PERFILES_BOTON_PRINCIPAL_STYLE = _BOTON_PRINCIPAL_STYLE
PERFILES_BOTON_SECUNDARIO_STYLE = _BOTON_SECUNDARIO_STYLE
PERFILES_BOTON_NORMAL_STYLE = _BOTON_NORMAL_STYLE

ESPACIO_LIBRE_MINIMO_MB = 2048
TAMANO_MINIMO_LAZ_BYTES = 1024
MEMORIA_PAUSA_SEGUNDOS = 5
ESPERA_ENTRE_COMPROBACIONES = 0.1

# ============================================================================
# 13. CONSTANTES DE INTERFAZ – COLADA
# ============================================================================

COLADA_DIALOG_TITLE = "COLADA – Postprocesado de LiDAR"
COLADA_DIALOG_WIDTH = 1200
COLADA_DIALOG_HEIGHT = 760
COLADA_DIALOG_MIN_WIDTH = 1024
COLADA_DIALOG_MIN_HEIGHT = 700
COLADA_HEADER_TITLE = "COLADA"
COLADA_HEADER_SUBTITLE = "Postprocesado de LiDAR"
COLADA_TAB_NAMES = ["1. Filtros", "2. Predicción", "3. Entrenamiento", "4. Rendimiento", "5. Perfiles"]
COLADA_TAB_NAMES_COMPACT = COLADA_TAB_NAMES
COLADA_BUTTON_CLOSE_TEXT = "Cerrar Panel"
COLADA_BUTTON_CLOSE_OBJECT_NAME = "btn_cerrar"
COLADA_MSG_NO_DATA_TITLE = "Sin datos"
COLADA_MSG_NO_DATA_TEXT = "No hay ningún resultado procesado para guardar."
COLADA_MSG_SAVE_ERROR_TITLE = "Error"
COLADA_MSG_SAVE_ERROR_TEXT = "No se pudo guardar el ráster:\n{}"
COLADA_MSG_NO_RESULT_TITLE = "Sin datos"
COLADA_MSG_NO_RESULT_TEXT = "Procesa una imagen antes de intentar enviarla al mapa."
COLADA_MAP_NORMALIZE_LOW_PERC = 2.0
COLADA_MAP_NORMALIZE_HIGH_PERC = 98.0

COLADA_PROGRESO_TITULO = "Progreso de Procesamiento"
COLADA_PROGRESO_ANCHO = 960
COLADA_PROGRESO_ALTO = 680
COLADA_PROGRESO_ANCHO_MIN = 800
COLADA_PROGRESO_ALTO_MIN = 600
COLADA_PROGRESO_CABECERA = "Progreso de la Operación"
COLADA_PROGRESO_LABEL_INICIAL = "Inicializando motores de procesamiento..."
COLADA_PROGRESO_BARRA_FORMATO = "%p% - Procesando..."
COLADA_PROGRESO_GRUPO_TABLA = "Desglose"
COLADA_PROGRESO_GRUPO_LOG = "Terminal de Registro"
COLADA_PROGRESO_TABLA_HEADERS = ["Unidad", "Estado", "Avance", "Métrica"]
COLADA_PROGRESO_BOTON_CANCELAR = "Abortar Operación"
COLADA_PROGRESO_BOTON_CERRAR = "Cerrar"
COLADA_PROGRESO_CANCELANDO_TEXTO = "Deteniendo..."
COLADA_LOG_COLOR_ERROR = "#CC0000"
COLADA_LOG_COLOR_WARNING = "#CC6600"
COLADA_LOG_COLOR_SUCCESS = "#2E7D32"
COLADA_LOG_COLOR_INFO = COLADA_COLOR_PRIMARIO_OSC
COLADA_PROGRESO_MINI_BARRA_STYLE = f"QProgressBar::chunk {{ background-color: {COLADA_COLOR_PRIMARIO}; }} QProgressBar {{ border: 1px solid {COLADA_COLOR_BORDE}; background: white; }}"
COLADA_PROGRESO_TIMESTAMP_FORMAT = "%H:%M:%S"
COLADA_PROGRESO_TIEMPO_TOTAL = "Tiempo total: {:.1f} min"

VISOR_PLACEHOLDER_TEXT = "Carga una imagen para visualizar"
VISOR_PLACEHOLDER_COLOR = "gray"
VISOR_PLACEHOLDER_FONT_SIZE = 12
VISOR_ZOOM_FACTOR = 1.15
VISOR_NORMALIZE_LOW_PERC = 2.0
VISOR_NORMALIZE_HIGH_PERC = 98.0

ENTRENAMIENTO_GROUP_ALGORITMO = "Algoritmo de Red"
ENTRENAMIENTO_GROUP_MODELO = "Parámetros del Modelo"
ENTRENAMIENTO_GROUP_OPTIMIZACION = "Optimización"
ENTRENAMIENTO_GROUP_DATASET = "Dataset GeoTIFF"
ENTRENAMIENTO_GROUP_SALIDA = "Modelo Entrenado"
ENTRENAMIENTO_LABEL_ESTRUCTURA = "Estructura:"
ENTRENAMIENTO_LABEL_BANDAS = "Bandas (in_channels):"
ENTRENAMIENTO_LABEL_PARCHE = "Tamaño de parche (px):"
ENTRENAMIENTO_LABEL_EPOCAS = "Épocas:"
ENTRENAMIENTO_LABEL_LEARNING_RATE = "Learning Rate:"
ENTRENAMIENTO_LABEL_BATCH_SIZE = "Batch Size:"
ENTRENAMIENTO_LABEL_GUARDAR_EN = "Guardar en:"
ENTRENAMIENTO_BUTTON_ANADIR = "Agregar Ráster"
ENTRENAMIENTO_BUTTON_LIMPIAR = "Limpiar Lista"
ENTRENAMIENTO_BUTTON_EXAMINAR = "Examinar..."
ENTRENAMIENTO_BUTTON_EJECUTAR = "Iniciar Entrenamiento"
ENTRENAMIENTO_MSG_SIN_DATOS_TITULO = "Sin datos"
ENTRENAMIENTO_MSG_SIN_DATOS_TEXTO = "Agrega al menos un archivo GeoTIFF al dataset."
ENTRENAMIENTO_MSG_ALGORITMO_NO_SOPORTADO = "Algoritmo no implementado"
ENTRENAMIENTO_MSG_SOLO_VAE = "Esta versión solo soporta VAE (SSIM Loss)."
ENTRENAMIENTO_MSG_RUTA_INVALIDA_TITULO = "Ruta inválida"
ENTRENAMIENTO_MSG_RUTA_INVALIDA_TEXTO = "Selecciona una ruta para guardar el modelo."
ENTRENAMIENTO_ALGORITMOS = ["VAE (SSIM Loss)", "VAE (Trimmed MSE)", "Isolation Forest Arqueológico"]
ENTRENAMIENTO_ALGORITMO_DEFAULT = 0
ENTRENAMIENTO_BANDAS_RANGE = (1, 20)
ENTRENAMIENTO_BANDAS_DEFAULT = VAE_IN_CHANNELS
ENTRENAMIENTO_PARCHE_RANGE = (32, 512)
ENTRENAMIENTO_PARCHE_DEFAULT = TAMANO_PARCHE
ENTRENAMIENTO_EPOCAS_RANGE = (1, 2000)
ENTRENAMIENTO_EPOCAS_DEFAULT = EPOCAS
ENTRENAMIENTO_LR_RANGE = (1e-6, 1e-1)
ENTRENAMIENTO_LR_DEFAULT = LEARNING_RATE
ENTRENAMIENTO_LR_DECIMALS = 6
ENTRENAMIENTO_BATCH_RANGE = (1, 512)
ENTRENAMIENTO_BATCH_DEFAULT = BATCH_SIZE
ENTRENAMIENTO_RUTA_MODELO_DEFAULT = os.path.join(os.path.expanduser("~"), "modelo_colada.pth")
ENTRENAMIENTO_BOTON_PRINCIPAL_STYLE = _BOTON_PRINCIPAL_STYLE
ENTRENAMIENTO_BOTON_SECUNDARIO_STYLE = _BOTON_SECUNDARIO_STYLE
ENTRENAMIENTO_PROGRESO_FORMATO = "Época {}/{} – train: {:.4f}  val: {:.4f}"
ENTRENAMIENTO_PROGRESO_COMPLETADO = "Entrenamiento completado"
ENTRENAMIENTO_PROGRESO_CANCELADO = "Cancelado"

ENTRENAMIENTO_MENSAJE_PREPARACION = "Preparación"
ENTRENAMIENTO_MENSAJE_EPOCA = "Época"
ENTRENAMIENTO_MENSAJE_PREPARACION_INICIANDO = "Iniciando"
ENTRENAMIENTO_MENSAJE_PREPARACION_COMPLETADO = "Completado"
ENTRENAMIENTO_MENSAJE_MODELO_GUARDADO = "Modelo guardado correctamente."
ENTRENAMIENTO_MENSAJE_CANCELADO = "Cancelado por el usuario."
ENTRENAMIENTO_MENSAJE_ERROR = "Error durante el entrenamiento."

ENTRENAMIENTO_PROGRESO_PREPARACION_MAX = 10
ENTRENAMIENTO_PROGRESO_ENTRENAMIENTO_INICIO = 10
ENTRENAMIENTO_PROGRESO_ENTRENAMIENTO_FIN = 100
ENTRENAMIENTO_FORMATO_MENSAJE_EPOCA = "Época {}/{} – Train: {:.4f}  Val: {:.4f}"
ENTRENAMIENTO_FORMATO_PROGRESO_GLOBAL = "Época {}/{}"

FILTROS_GROUP_DATOS = "1. Archivos de Trabajo"
FILTROS_GROUP_AJUSTES = "2. Ajustes del Filtro"
FILTROS_GROUP_ACCIONES = "3. Acciones"
FILTROS_LABEL_TESELA = "Tesela:"
FILTROS_LABEL_DERIVADO = "Derivado (.tif):"
FILTROS_LABEL_ALGORITMO = "Algoritmo:"
FILTROS_BUTTON_EXAMINAR = "Examinar..."
FILTROS_BUTTON_PROCESAR = "Ejecutar Filtro"
FILTROS_BUTTON_GUARDAR = "Guardar Tesela"
FILTROS_BUTTON_MAPA = "Plasmar en Mapa"
FILTROS_DIR_SELECCIONADO = "Ningún directorio seleccionado"
FILTROS_OPCIONES = ["Ninguno", "Sobel Horizontal", "Sobel Vertical", "Magnitud de Sobel", "Laplaciano", "Desenfoque Gaussiano", "Filtro de Mediana", "Algoritmo Canny"]
FILTROS_LABEL_SIGMA = "Sigma: {:.1f}"
FILTROS_LABEL_VENTANA = "Ventana Kernel: {}"
FILTROS_LABEL_CANNY_LOW = "Canny Bajo: {}"
FILTROS_LABEL_CANNY_HIGH = "Canny Alto: {}"
FILTROS_SIGMA_RANGE = (1, 100)
FILTROS_SIGMA_DEFAULT = 10
FILTROS_VENTANA_RANGE = (3, 15)
FILTROS_VENTANA_DEFAULT = 5
FILTROS_CANNY_RANGE = (0, 255)
FILTROS_CANNY_LOW_DEFAULT = 50
FILTROS_CANNY_HIGH_DEFAULT = 150
FILTROS_BOTON_NORMAL_STYLE = _BOTON_NORMAL_STYLE
FILTROS_BOTON_PRINCIPAL_STYLE = _BOTON_PRINCIPAL_STYLE
FILTROS_BOTON_SECUNDARIO_STYLE = _BOTON_SECUNDARIO_STYLE

PREDICCION_GROUP_ALGORITMO = "1. Algoritmo de Detección"
PREDICCION_GROUP_MODELO = "2. Modelo / Datos"
PREDICCION_GROUP_PARAMS = "3. Hiperparámetros de Inferencia"
PREDICCION_GROUP_SALIDA = "4. Salida"
PREDICCION_LABEL_METODO = "Método:"
PREDICCION_LABEL_PARCHE = "Parche (px):"
PREDICCION_LABEL_SOLAPE = "Solapamiento:"
PREDICCION_LABEL_BATCH = "Batch:"
PREDICCION_LABEL_SIGMA = "Sigma:"
PREDICCION_LABEL_UMBRAL = "Umbral (%):"
PREDICCION_LABEL_DIRECTORIO = "Ningún directorio seleccionado"
PREDICCION_LABEL_SIN_MODELO = "Sin modelo"
PREDICCION_LABEL_SIN_DATOS = "Sin datos de entrenamiento"
PREDICCION_BTN_EXAMINAR = "Examinar..."
PREDICCION_BTN_CARGAR_MODELO = "Cargar modelo (.pt)..."
PREDICCION_BTN_SELECCIONAR_ENTRENAMIENTO = "Seleccionar carpeta de entrenamiento..."
PREDICCION_BTN_EJECUTAR = "Iniciar Inferencia"
PREDICCION_BTN_GUARDAR = "Guardar Predicción"
PREDICCION_BTN_MAPA = "Plasmar en Mapa"
PREDICCION_ALGORITMOS = ["VAE (SSIM Loss)", "VAE (Trimmed MSE)", "Isolation Forest Arqueológico"]
PREDICCION_ALGORITMO_DEFAULT = 0
PREDICCION_PARCHE_RANGE = (32, 512)
PREDICCION_PARCHE_DEFAULT = TAMANO_PARCHE
PREDICCION_SOLAPE_RANGE = (0, 256)
PREDICCION_SOLAPE_DEFAULT = SOLAPAMIENTO
PREDICCION_LOTE_RANGE = (1, 128)
PREDICCION_LOTE_DEFAULT = TAMANIO_LOTE
PREDICCION_SIGMA_RANGE = (0.1, 10.0)
PREDICCION_SIGMA_DEFAULT = SIGMA_GAUSSIANO
PREDICCION_UMBRAL_RANGE = (50, 100)
PREDICCION_UMBRAL_DEFAULT = UMBRAL_PERCENTIL
PREDICCION_MSG_SIN_IMAGEN_TITULO = "Sin imagen"
PREDICCION_MSG_SIN_IMAGEN_TEXTO = "Primero carga una imagen desde la pestaña Filtros."
PREDICCION_MSG_SIN_ENTRENAMIENTO = "Falta la carpeta de entrenamiento."
PREDICCION_MSG_SIN_TIF_ENTRENAMIENTO = "No se encontraron .tif en la carpeta de entrenamiento."
PREDICCION_MSG_SIN_MODELO = "No se ha cargado un modelo VAE."
PREDICCION_MSG_INFERENCIA_COMPLETADA = "Inferencia completada"
PREDICCION_BOTON_PRINCIPAL_STYLE = _BOTON_PRINCIPAL_STYLE
PREDICCION_BOTON_SECUNDARIO_STYLE = _BOTON_SECUNDARIO_STYLE
PREDICCION_BOTON_NORMAL_STYLE = _BOTON_NORMAL_STYLE

PREDICCION_TAREA_NOMBRE = "COLADA - Predicción"
PREDICCION_MENSAJE_CANCELADA = "Predicción cancelada."
PREDICCION_MENSAJE_COMPLETADA = "Predicción completada: {} teselas."
PREDICCION_MENSAJE_FINALIZADA = "Predicción finalizada."
PREDICCION_MENSAJE_SIN_RESULTADOS = "Predicción sin resultados."
PREDICCION_MENSAJE_PROCESANDO = "Procesando"
PREDICCION_MENSAJE_COMPLETADO = "Completado"
PREDICCION_MENSAJE_ERROR = "Error"
PREDICCION_NOMBRE_CAPA_ANOMALIA = "{}_anomalia"
PREDICCION_NOMBRE_CAPA_CANDIDATOS = "{}_candidatos"
PREDICCION_ANOMALIA_OPACIDAD = 0.8
PREDICCION_COLORES_RAMPA = [(0, 0, 128), (0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 0, 0)]
PREDICCION_ETIQUETAS_RAMPA = ["Muy bajo", "Bajo", "Medio-bajo", "Medio", "Medio-alto", "Alto"]
PREDICCION_CANDIDATO_COLOR = "255,165,0,128"
PREDICCION_CANDIDATO_OUTLINE_COLOR = "255,0,0,255"
PREDICCION_CANDIDATO_OUTLINE_WIDTH = "0.8"
PREDICCION_MIN_AREA_M2_DEFAULT = MIN_AREA_ANOMALIA_M2
PREDICCION_IF_N_ESTIMATORS_DEFAULT = ISOLATION_FOREST_N_ESTIMATORS
PREDICCION_IF_CONTAMINATION_DEFAULT = ISOLATION_FOREST_CONTAMINATION
PREDICCION_IF_MAX_SAMPLES_DEFAULT = ISOLATION_FOREST_MAX_SAMPLES
PREDICCION_CALLBACK_INICIO = 2
PREDICCION_CALLBACK_RANGO = 80

RENDIMIENTO_GPU_RANGE = (1, 16)
RENDIMIENTO_CPU_RANGE = (1, 64)
RENDIMIENTO_GPU_TOOLTIP = "Cantidad de procesos que usarán la GPU simultáneamente."
RENDIMIENTO_CPU_TOOLTIP = "Número de hilos de CPU dedicados al procesamiento."
RENDIMIENTO_GROUP_TITLE = "Hardware"

# ============================================================================
# 14. SERVICIOS WEB (plugin paraguas)
# ============================================================================

URL_ORTOFOTO_PNOA = "https://www.ign.es/wms-inspire/pnoa-ma"
NOMBRE_MAPA_BASE = "Ortofoto PNOA"
ID_MAPA_BASE = "PNOA"
