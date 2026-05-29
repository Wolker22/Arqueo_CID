# -*- coding: utf-8 -*-
"""
Verificación de dependencias unificada para Arqueo-CID
======================================================

Proporciona funciones para comprobar la disponibilidad de dependencias
externas (PDAL, GDAL, PyTorch con CUDA, etc.), la conectividad con el
servidor del CNIG y la existencia de herramientas del sistema.

Todas las funciones devuelven diccionarios estructurados que pueden ser
usados por el diálogo de configuración o por la interfaz de usuario
para mostrar advertencias.

ADVERTENCIA: Este módulo contiene las únicas comprobaciones de disponibilidad
de bibliotecas. Ningún otro archivo (especialmente `config.py`) debe contener
bloques try/except para detectar GDAL, PyTorch, etc.
"""

import os
import sys
import platform
import shutil
import subprocess
import importlib.util
from typing import Dict, Any, Tuple, Optional

from .logging import get_logger

logger = get_logger('ArqueoCid.entorno')

CMD_TIMEOUT = 5

# ----------------------------------------------------------------------
# Banderas de disponibilidad (calculadas una sola vez)
# ----------------------------------------------------------------------

# GDAL
try:
    from osgeo import gdal
    GDAL_DISPONIBLE = True
    GDAL_VERSION = gdal.__version__
except ImportError:
    GDAL_DISPONIBLE = False
    GDAL_VERSION = None

# SciPy
try:
    import scipy
    SCIPY_DISPONIBLE = True
    SCIPY_VERSION = scipy.__version__
except ImportError:
    SCIPY_DISPONIBLE = False
    SCIPY_VERSION = None

# PyTorch
try:
    import torch
    PYTORCH_DISPONIBLE = True
    PYTORCH_VERSION = torch.__version__
    PYTORCH_CUDA_DISPONIBLE = torch.cuda.is_available()
except ImportError:
    PYTORCH_DISPONIBLE = False
    PYTORCH_VERSION = None
    PYTORCH_CUDA_DISPONIBLE = False

# scikit-learn
try:
    import sklearn
    SKLEARN_DISPONIBLE = True
    SKLEARN_VERSION = sklearn.__version__
except ImportError:
    SKLEARN_DISPONIBLE = False
    SKLEARN_VERSION = None

# scikit-image
try:
    from skimage.feature import canny
    SKIMAGE_DISPONIBLE = True
except ImportError:
    SKIMAGE_DISPONIBLE = False

# psutil
try:
    import psutil
    PSUTIL_DISPONIBLE = True
    PSUTIL_VERSION = psutil.__version__
except ImportError:
    PSUTIL_DISPONIBLE = False
    PSUTIL_VERSION = None

# ----------------------------------------------------------------------
# Funciones de verificación específicas
# ----------------------------------------------------------------------

def verificar_pdal() -> Tuple[bool, str, Optional[str]]:
    """
    Comprueba si PDAL está instalado y es accesible desde el PATH.

    Returns:
        (disponible, mensaje, versión)
    """
    pdal_path = shutil.which('pdal')
    if not pdal_path:
        return False, "No se encontró 'pdal' en el PATH", None
    try:
        res = subprocess.run(
            [pdal_path, '--version'],
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT
        )
        if res.returncode == 0:
            version = res.stdout.strip().split()[1] if res.stdout else "desconocida"
            return True, f"PDAL {version} encontrado", version
        else:
            return False, "PDAL devolvió código de error", None
    except subprocess.TimeoutExpired:
        return False, "El comando 'pdal --version' excedió el tiempo de espera", None
    except Exception as e:
        return False, f"Error inesperado al ejecutar PDAL: {e}", None


def verificar_gdal() -> Tuple[bool, str, Optional[str]]:
    """Comprueba la disponibilidad de GDAL Python."""
    if not GDAL_DISPONIBLE:
        return False, "GDAL no instalado o no detectable", None
    return True, f"GDAL {GDAL_VERSION} disponible", GDAL_VERSION


def verificar_torch_cuda() -> Tuple[bool, str, Optional[bool]]:
    """Verifica PyTorch y disponibilidad de CUDA."""
    if not PYTORCH_DISPONIBLE:
        return False, "PyTorch no instalado", None
    try:
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            try:
                device_name = torch.cuda.get_device_name(0)
                msg = f"PyTorch {PYTORCH_VERSION} con CUDA disponible (GPU: {device_name})"
            except:
                msg = f"PyTorch {PYTORCH_VERSION} con CUDA disponible"
        else:
            msg = f"PyTorch {PYTORCH_VERSION} instalado, pero CUDA no disponible (usando CPU)"
        return True, msg, cuda_ok
    except Exception as e:
        return False, f"Error al comprobar PyTorch: {e}", None


def verificar_scipy() -> Tuple[bool, str]:
    """Verifica la disponibilidad de SciPy."""
    if SCIPY_DISPONIBLE:
        return True, f"SciPy {SCIPY_VERSION} disponible"
    return False, "SciPy no instalado"


def verificar_conexion_cnig() -> Tuple[bool, str]:
    """Comprueba conectividad con el servidor del CNIG."""
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        res = requests.head('https://centrodedescargas.cnig.es', timeout=4, verify=False)
        if res.status_code < 400:
            return True, "Conexión con CNIG exitosa"
        else:
            return False, f"El servidor CNIG respondió con código {res.status_code}"
    except ImportError:
        return False, "Requests no instalado, no se puede verificar conectividad"
    except Exception as e:
        return False, f"Error de conexión con CNIG: {e}"


def verificar_dependencias_python() -> Dict[str, Dict[str, Any]]:
    """
    Comprueba la disponibilidad de paquetes Python adicionales (rasterio, laspy, etc.)

    Returns:
        Diccionario con estructura {nombre: {disponible, version, mensaje}}.
    """
    dependencias = {
        "rasterio": "rasterio",
        "laspy": "laspy",
        "numpy": "numpy",
        "pillow": "PIL",
        "sklearn": "sklearn",
        "skimage": "skimage",
        "psutil": "psutil",
        "beautifulsoup4": "bs4",
        "requests": "requests",
    }
    resultados = {}
    for nombre, modulo in dependencias.items():
        try:
            spec = importlib.util.find_spec(modulo)
            if spec is not None:
                # Intentar obtener versión
                try:
                    mod = __import__(modulo)
                    version = getattr(mod, "__version__", "desconocida")
                except:
                    version = "desconocida"
                resultados[nombre] = {
                    "disponible": True,
                    "version": version,
                    "mensaje": f"{nombre} {version} disponible"
                }
            else:
                resultados[nombre] = {
                    "disponible": False,
                    "version": None,
                    "mensaje": f"{nombre} no instalado"
                }
        except Exception as e:
            resultados[nombre] = {
                "disponible": False,
                "version": None,
                "mensaje": f"Error al comprobar {nombre}: {e}"
            }
    return resultados


# ----------------------------------------------------------------------
# Función principal que integra todas las verificaciones
# ----------------------------------------------------------------------

def verificar_todas_dependencias() -> Dict[str, Any]:
    """
    Ejecuta todas las comprobaciones de dependencias y retorna un diccionario
    estructurado con los resultados.

    Returns:
        Diccionario con las claves:
        - "sistema": información del sistema (Python, SO, CPUs).
        - "dependencias": dict con detalles de cada dependencia.
        - "resumen": dict con contadores de fallos.
        - "mensaje_global": texto resumen.
    """
    info_sistema = {
        'python': sys.version.split(' ')[0],
        'sistema': platform.system(),
        'version_sistema': platform.release(),
        'cpus_logicas': os.cpu_count()
    }

    deps = {}

    # PDAL
    pdal_ok, pdal_msg, pdal_ver = verificar_pdal()
    deps["pdal"] = {
        'nombre': 'PDAL (Core C++)',
        'obligatoria': False,
        'disponible': pdal_ok,
        'version': pdal_ver,
        'mensaje': pdal_msg,
        'ayuda': 'Instale PDAL desde https://pdal.io/ o mediante "conda install pdal"'
    }

    # GDAL
    gdal_ok, gdal_msg, gdal_ver = verificar_gdal()
    deps["gdal"] = {
        'nombre': 'GDAL Python',
        'obligatoria': True,
        'disponible': gdal_ok,
        'version': gdal_ver,
        'mensaje': gdal_msg,
        'ayuda': 'pip install GDAL o conda install -c conda-forge gdal'
    }

    # PyTorch / CUDA
    torch_ok, torch_msg, cuda_flag = verificar_torch_cuda()
    deps["pytorch"] = {
        'nombre': 'PyTorch (Backend IA)',
        'obligatoria': False,   # No obligatoria para Tizona, sí para Colada (se controla en UI)
        'disponible': torch_ok,
        'version': PYTORCH_VERSION,
        'mensaje': torch_msg,
        'cuda_disponible': cuda_flag if torch_ok else False,
        'ayuda': 'Instale PyTorch desde https://pytorch.org/ (versión con o sin CUDA)'
    }

    # SciPy
    scipy_ok, scipy_msg = verificar_scipy()
    deps["scipy"] = {
        'nombre': 'SciPy (Filtros)',
        'obligatoria': True,
        'disponible': scipy_ok,
        'version': SCIPY_VERSION,
        'mensaje': scipy_msg,
        'ayuda': 'pip install scipy'
    }

    # scikit-learn
    deps["sklearn"] = {
        'nombre': 'scikit-learn (Isolation Forest)',
        'obligatoria': False,
        'disponible': SKLEARN_DISPONIBLE,
        'version': SKLEARN_VERSION,
        'mensaje': f"scikit-learn {SKLEARN_VERSION if SKLEARN_DISPONIBLE else 'no disponible'}",
        'ayuda': 'pip install scikit-learn'
    }

    # scikit-image
    deps["skimage"] = {
        'nombre': 'scikit-image (Canny)',
        'obligatoria': False,
        'disponible': SKIMAGE_DISPONIBLE,
        'version': None,
        'mensaje': 'scikit-image disponible' if SKIMAGE_DISPONIBLE else 'scikit-image no instalado',
        'ayuda': 'pip install scikit-image'
    }

    # psutil
    deps["psutil"] = {
        'nombre': 'psutil (Monitor RAM)',
        'obligatoria': False,
        'disponible': PSUTIL_DISPONIBLE,
        'version': PSUTIL_VERSION,
        'mensaje': 'psutil disponible' if PSUTIL_DISPONIBLE else 'psutil no instalado',
        'ayuda': 'pip install psutil'
    }

    # Conexión CNIG
    cnig_ok, cnig_msg = verificar_conexion_cnig()
    deps["cnig"] = {
        'nombre': 'Conexión CNIG',
        'obligatoria': False,
        'disponible': cnig_ok,
        'version': None,
        'mensaje': cnig_msg,
        'ayuda': 'Sin conexión solo se podrán procesar archivos locales.'
    }

    # Dependencias Python adicionales
    python_deps = verificar_dependencias_python()
    for nombre, info in python_deps.items():
        deps[nombre] = {
            'nombre': nombre.capitalize(),
            'obligatoria': True if nombre in ['rasterio', 'numpy', 'laspy', 'requests'] else False,
            'disponible': info['disponible'],
            'version': info['version'],
            'mensaje': info['mensaje'],
            'ayuda': f'pip install {nombre}'
        }

    # Calcular resumen
    total_obligatorias = sum(1 for dep in deps.values() if dep.get('obligatoria', False))
    fallos_obligatorias = sum(1 for dep in deps.values() if dep.get('obligatoria', False) and not dep.get('disponible', False))
    total_opcionales = sum(1 for dep in deps.values() if not dep.get('obligatoria', False))
    fallos_opcionales = sum(1 for dep in deps.values() if not dep.get('obligatoria', False) and not dep.get('disponible', False))

    mensaje_global = (
        f"Verificación completada. Obligatorias: {total_obligatorias - fallos_obligatorias}/{total_obligatorias} OK. "
        f"Opcionales: {total_opcionales - fallos_opcionales}/{total_opcionales} OK."
    )

    return {
        "sistema": info_sistema,
        "dependencias": deps,
        "resumen": {
            "total_obligatorias": total_obligatorias,
            "fallos_obligatorias": fallos_obligatorias,
            "total_opcionales": total_opcionales,
            "fallos_opcionales": fallos_opcionales,
        },
        "mensaje_global": mensaje_global
    }


def formatear_mensaje_dependencias(info_deps: Dict[str, Any]) -> str:
    """
    Convierte el diccionario devuelto por `verificar_todas_dependencias` en
    un texto legible para mostrar en un diálogo.

    Args:
        info_deps: Diccionario con la estructura completa.

    Returns:
        Cadena de texto multilínea.
    """
    lineas = []
    lineas.append("=== DEPENDENCIAS OBLIGATORIAS ===")
    for nombre, dep in info_deps["dependencias"].items():
        if dep.get("obligatoria", False):
            estado = "✅ OK" if dep.get("disponible") else "❌ FALLO"
            lineas.append(f"{estado} {nombre}: {dep['mensaje']}")
            if not dep.get("disponible") and "ayuda" in dep:
                lineas.append(f"   → {dep['ayuda']}")
    lineas.append("\n=== DEPENDENCIAS OPCIONALES ===")
    for nombre, dep in info_deps["dependencias"].items():
        if not dep.get("obligatoria", False):
            estado = "✅ OK" if dep.get("disponible") else "⚠️ NO DISPONIBLE"
            lineas.append(f"{estado} {nombre}: {dep['mensaje']}")
    return "\n".join(lineas)


def es_entorno_valido(info_deps: Dict[str, Any]) -> bool:
    """
    Determina si el entorno actual tiene todas las dependencias obligatorias.

    Args:
        info_deps: Diccionario de verificación.

    Returns:
        True si todas las obligatorias están disponibles.
    """
    for dep in info_deps["dependencias"].values():
        if dep.get("obligatoria", False) and not dep.get("disponible", False):
            return False
    return True