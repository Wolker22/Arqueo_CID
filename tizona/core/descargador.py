# -*- coding: utf-8 -*-
"""
Descargador de archivos LiDAR del CNIG (Arqueo-CID)
====================================================

Descarga archivos .laz del Centro de Descargas del CNIG, filtrando por
tipo de producto (RGB/IRC/Ambos) y adaptando la URL según la cobertura
seleccionada (1ª, 2ª, 3ª o todas).

Incluye reintentos automáticos, validación de integridad del archivo
y gestión robusta de sesiones HTTP.
"""

import os
import re
import time
import random
import socket
from typing import Optional, Tuple, List, Dict, Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Importar constantes desde la configuración central
from ...config import (
    URL_HOME,
    URL_BUSQUEDA,
    URL_ARCHIVOS_SERIE,
    URL_INIT_DESCARGA,
    URL_DESCARGA,
    HEADERS,
    MAX_INTENTOS_DESCARGA,
    TIMEOUT_REQUESTS,
    TIMEOUT_DESCARGA,
    COBERTURA_A_URL_PRODUCTO,
    CNIG_MENCIONES_POR_PRODUCTO,
    CNIG_TEXTO_LICENCIA,
    CHUNK_SIZE_DESCARGA,
    MIN_FILE_SIZE_BYTES,
    RETRY_TOTAL,
    RETRY_BACKOFF_FACTOR,
    RETRY_STATUS_FORCELIST,
    POOL_CONNECTIONS,
    POOL_MAXSIZE,
)
from ...utils.logging import get_logger

logger = get_logger('Tizona.descargador')


# ----------------------------------------------------------------------
# Validación de archivos descargados
# ----------------------------------------------------------------------

def validar_archivo_descargado(ruta: str) -> Tuple[bool, str]:
    """
    Comprueba que el archivo existe, tiene tamaño mínimo y cabecera LAS/LAZ.

    Args:
        ruta: Ruta absoluta del archivo descargado.

    Returns:
        (es_valido, mensaje) - True si es válido, False en caso contrario.
    """
    if not os.path.exists(ruta):
        return False, "Archivo no encontrado"
    size = os.path.getsize(ruta)
    if size < MIN_FILE_SIZE_BYTES:
        return False, f"Tamaño menor de {MIN_FILE_SIZE_BYTES} bytes"
    try:
        with open(ruta, 'rb') as f:
            cabecera = f.read(4)
            if cabecera in (b'LASF', b'LAS'):
                return True, "LAS/LAZ válido"
    except Exception as e:
        return False, f"Error de E/S: {e}"
    return False, f"Cabecera desconocida: {cabecera!r}"


def archivo_coincide_tipo(nombre: str, tipo_producto: str) -> bool:
    """
    Determina si el nombre del archivo se ajusta al filtro RGB/IRC/Ambos.

    Args:
        nombre: Nombre del archivo (ej. "PNOA_2015_RGB.laz").
        tipo_producto: 'RGB', 'IRC' o 'Ambos'.

    Returns:
        True si debe ser incluido, False en caso contrario.
    """
    nombre_upper = nombre.upper()
    if tipo_producto == "RGB":
        return 'RGB' in nombre_upper and 'IRC' not in nombre_upper and 'CIR' not in nombre_upper
    elif tipo_producto == "IRC":
        return ('IRC' in nombre_upper or 'CIR' in nombre_upper)
    elif tipo_producto == "Ambos":
        return True
    else:
        return True


def filtrar_archivos_por_tipo(lista_archivos: List[str], tipo_producto: str) -> List[str]:
    """
    Filtra una lista de nombres de archivo según el tipo de producto.

    Args:
        lista_archivos: Lista de nombres.
        tipo_producto: 'RGB', 'IRC' o 'Ambos'.

    Returns:
        Lista filtrada.
    """
    filtrados = [n for n in lista_archivos if archivo_coincide_tipo(n, tipo_producto)]
    if not filtrados and tipo_producto != "Ambos":
        logger.warning(f"No se encontraron archivos de tipo '{tipo_producto}' en la lista.")
    return filtrados


# ----------------------------------------------------------------------
# Descargador principal
# ----------------------------------------------------------------------

class DescargadorCNIG:
    """
    Cliente de descarga para el CNIG. Maneja la negociación de sesión,
    extracción de códigos de serie/secuencial y la descarga en flujo.

    Attributes:
        timeout: Timeout en segundos para las peticiones HTTP.
        sesion: Sesión requests con reintentos y cabeceras.
    """

    def __init__(self, timeout: int = TIMEOUT_REQUESTS) -> None:
        """
        Inicializa el descargador y regenera la sesión.

        Args:
            timeout: Timeout en segundos para las peticiones.
        """
        self.timeout: int = timeout
        self.sesion: Optional[requests.Session] = None
        self._regenerar_sesion()

    def _regenerar_sesion(self) -> None:
        """Crea una nueva sesión requests con política de reintentos."""
        if self.sesion:
            self.sesion.close()
        self.sesion = requests.Session()
        retries = Retry(
            total=RETRY_TOTAL,
            backoff_factor=RETRY_BACKOFF_FACTOR,
            status_forcelist=RETRY_STATUS_FORCELIST,
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(
            max_retries=retries,
            pool_connections=POOL_CONNECTIONS,
            pool_maxsize=POOL_MAXSIZE,
        )
        self.sesion.mount("http://", adapter)
        self.sesion.mount("https://", adapter)
        self.sesion.headers.update(HEADERS)

    def _verificar_conectividad(self) -> bool:
        """Comprueba resolución DNS del dominio CNIG."""
        try:
            socket.gethostbyname("centrodedescargas.cnig.es")
            return True
        except socket.gaierror:
            return False

    def _inicializar_sesion(self) -> None:
        """Realiza una petición inicial a la home para establecer cookies."""
        if not self._verificar_conectividad():
            raise ConnectionError("No se puede resolver 'centrodedescargas.cnig.es'.")
        try:
            self.sesion.get(URL_HOME, timeout=self.timeout, verify=False)
            logger.debug("Sesión CNIG inicializada.")
        except requests.RequestException as e:
            raise ConnectionError(f"Fallo al contactar CNIG: {e}")

    def descargar_archivo(
        self,
        fichero_completo: str,
        ruta_destino: str,
        tipo_producto: str = "Ambos",
        cobertura: int = 2,
    ) -> Tuple[str, bool, str]:
        """
        Descarga un archivo LiDAR del CNIG. Siempre guarda con extensión .laz.

        Args:
            fichero_completo: Nombre completo del archivo (ej. "PNOA_2015_RGB.laz").
            ruta_destino: Directorio donde guardar.
            tipo_producto: 'RGB', 'IRC' o 'Ambos' (filtro).
            cobertura: 1, 2, 3 o 'todas' (por defecto 2).

        Returns:
            (ruta_guardado, éxito, mensaje)
        """
        nombre_original = fichero_completo.split("/")[-1]
        nombre_base = os.path.splitext(nombre_original)[0]

        # Filtrar por tipo de producto
        if not archivo_coincide_tipo(nombre_original, tipo_producto):
            msg = (
                f"El archivo '{nombre_original}' no coincide con el filtro "
                f"'{tipo_producto}'. Se omite."
            )
            logger.info(msg)
            return "", False, msg

        nombre_archivo_final = f"{nombre_base}.laz"
        ruta_guardado = os.path.join(ruta_destino, nombre_archivo_final)

        # Si ya existe y es válido, omitir descarga
        if os.path.exists(ruta_guardado):
            valido, msg = validar_archivo_descargado(ruta_guardado)
            if valido:
                logger.info(f"{nombre_archivo_final} ya existe y es válido.")
                return ruta_guardado, True, "Ya existía y es válido"
            else:
                logger.warning(f"Archivo existente inválido ({msg}). Se sobrescribirá.")

        # Normalizar nombre para búsqueda (guiones bajos a guiones)
        nombre_normalizado = nombre_original.replace("_", "-")

        # Determinar la URL del producto según la cobertura
        url_prod = COBERTURA_A_URL_PRODUCTO.get(cobertura, "lidar-segunda-cobertura")
        logger.debug(f"Usando URL de producto: {url_prod} (cobertura={cobertura})")

        for intento in range(1, MAX_INTENTOS_DESCARGA + 1):
            logger.info(
                f"Procesando {nombre_archivo_final} "
                f"(Intento {intento}/{MAX_INTENTOS_DESCARGA})"
            )
            try:
                if intento == 1 or not self.sesion.cookies:
                    self._regenerar_sesion()
                    self._inicializar_sesion()

                # Paso 1: Búsqueda de la serie
                payload_busqueda = {"keySearchCab": nombre_original, "lang": "ES"}
                res_busqueda = self.sesion.post(
                    URL_BUSQUEDA, data=payload_busqueda, timeout=self.timeout, verify=False
                )
                res_busqueda.raise_for_status()
                cod_serie = self._extraer_codigo_serie(res_busqueda.text)
                if not cod_serie:
                    logger.warning(
                        "No se encontró código de serie con el nombre original. "
                        "Probando con normalizado..."
                    )
                    payload_busqueda["keySearchCab"] = nombre_normalizado
                    res_busqueda = self.sesion.post(
                        URL_BUSQUEDA, data=payload_busqueda, timeout=self.timeout, verify=False
                    )
                    res_busqueda.raise_for_status()
                    cod_serie = self._extraer_codigo_serie(res_busqueda.text)

                if not cod_serie:
                    logger.error("No se encontró código de serie.")
                    continue

                # Paso 2: Extraer código secuencial
                payload_tabla = {
                    "numPagina": "1",
                    "codSerie": cod_serie,
                    "totalArchivos": "1",
                    "keySearch": nombre_original,
                    "lang": "ES",
                }
                self.sesion.headers.update({"Referer": URL_BUSQUEDA})
                res_tabla = self.sesion.post(
                    URL_ARCHIVOS_SERIE, data=payload_tabla, timeout=self.timeout, verify=False
                )
                res_tabla.raise_for_status()
                cod_sec = self._extraer_codigo_secuencial(res_tabla.text)

                if not cod_sec:
                    payload_tabla["keySearch"] = nombre_normalizado
                    res_tabla = self.sesion.post(
                        URL_ARCHIVOS_SERIE, data=payload_tabla, timeout=self.timeout, verify=False
                    )
                    res_tabla.raise_for_status()
                    cod_sec = self._extraer_codigo_secuencial(res_tabla.text)

                if not cod_sec:
                    logger.error("No se encontró código secuencial.")
                    continue

                # Paso 3: Intentar descarga con ambas variantes del nombre
                for nombre_prueba in (nombre_original, nombre_normalizado):
                    try:
                        logger.debug(f"Probando descarga con nombre='{nombre_prueba}'")
                        if self._intentar_descarga(
                            nombre_prueba, ruta_guardado, cod_serie, cod_sec, url_prod
                        ):
                            valido, msg = validar_archivo_descargado(ruta_guardado)
                            if valido:
                                logger.info("¡Descarga exitosa!")
                                return ruta_guardado, True, "Descargado correctamente"
                            else:
                                logger.warning(
                                    f"Archivo descargado pero no válido ({msg}). Eliminando."
                                )
                                if os.path.exists(ruta_guardado):
                                    os.remove(ruta_guardado)
                        time.sleep(random.uniform(0.5, 1.5))
                    except Exception as e:
                        logger.warning(f"Fallo en intento de descarga: {e}")
                        if os.path.exists(ruta_guardado):
                            os.remove(ruta_guardado)

                raise Exception("No se pudo descargar con ningún nombre.")

            except Exception as e:
                logger.warning(f"Error en intento {intento}: {e}")
                self._regenerar_sesion()
                if intento == MAX_INTENTOS_DESCARGA:
                    if os.path.exists(ruta_guardado):
                        os.remove(ruta_guardado)
                    return (
                        ruta_guardado,
                        False,
                        f"Error final tras {MAX_INTENTOS_DESCARGA} intentos: {e}",
                    )
                time.sleep(2**intento + random.uniform(0, 1))

        return ruta_guardado, False, "Finalizado sin éxito"

    def _intentar_descarga(
        self,
        fichero_completo: str,
        ruta_guardado: str,
        cod_serie: str,
        cod_sec: str,
        url_prod: str,
    ) -> bool:
        """
        Ejecuta la secuencia final de descarga: initDescargaDir + descargaDir.

        Args:
            fichero_completo: Nombre del archivo a descargar.
            ruta_guardado: Ruta donde guardar el archivo.
            cod_serie: Código de serie obtenido.
            cod_sec: Código secuencial obtenido.
            url_prod: URL del producto (cobertura).

        Returns:
            True si la descarga fue exitosa y el archivo es válido.

        Raises:
            Exception: Si el servidor devuelve HTML en lugar de binario o el archivo es inválido.
        """
        cab_ajax = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        }
        res_ajax = self.sesion.post(
            URL_INIT_DESCARGA,
            data={"secuencial": cod_sec},
            headers=cab_ajax,
            timeout=self.timeout,
            verify=False,
        )
        res_ajax.raise_for_status()

        # Texto de menciones según el producto
        ids_menciones = CNIG_MENCIONES_POR_PRODUCTO.get(
            url_prod, "LiDAR 2ª Cobertura"
        )

        payload_descarga = {
            "codSerie": cod_serie,
            "keySearchTotSer": fichero_completo,
            "secDescDirLA": cod_sec,
            "totalArchivos": "1",
            "urlProd": url_prod,
            "txtLic": CNIG_TEXTO_LICENCIA,
            "idsMenciones": ids_menciones,
        }
        cab_descarga = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        with self.sesion.post(
            URL_DESCARGA,
            data=payload_descarga,
            headers=cab_descarga,
            stream=True,
            timeout=TIMEOUT_DESCARGA,
            verify=False,
        ) as res_descarga:
            res_descarga.raise_for_status()
            content_type = res_descarga.headers.get("Content-Type", "")
            if "text/html" in content_type:
                logger.error(
                    "El servidor devolvió HTML en lugar de archivo binario. "
                    "Guardando respuesta como debug_descarga.html"
                )
                with open(ruta_guardado + ".debug.html", "w", encoding="utf-8") as f:
                    f.write(res_descarga.text[:2000])
                raise Exception("Respuesta HTML en lugar de binario")

            with open(ruta_guardado, "wb") as f:
                for chunk in res_descarga.iter_content(chunk_size=CHUNK_SIZE_DESCARGA):
                    if chunk:
                        f.write(chunk)

        valido, msg = validar_archivo_descargado(ruta_guardado)
        if not valido:
            logger.warning(f"Validación fallida tras descarga: {msg}")
            raise Exception(f"Archivo inválido ({msg})")
        return True

    @staticmethod
    def _extraer_codigo_serie(html: str) -> Optional[str]:
        """
        Extrae el código de serie (codSerie) del HTML de búsqueda.

        Args:
            html: Contenido HTML de la respuesta.

        Returns:
            Código de serie como cadena, o None si no se encuentra.
        """
        cod = None
        try:
            soup = BeautifulSoup(html, "html.parser")
            enlace = soup.find("a", id=re.compile(r"^linkArchivosSerie_"))
            if enlace and enlace.get("id"):
                match = re.search(r"linkArchivosSerie_([^_]+)", enlace["id"])
                if match:
                    cod = match.group(1)
            if not cod:
                for elem in soup.find_all(attrs={"onclick": True}):
                    onclick = elem.get("onclick")
                    match = re.search(r"codSerie[=:]\s*['\"]?(\d+)", onclick)
                    if match:
                        cod = match.group(1)
                        break
        except Exception as e:
            logger.debug(f"Error BS4 en codSerie: {e}")

        if not cod:
            for pattern in (
                r'id=["\']linkArchivosSerie_([^_]+)_',
                r'codSerie[=:]\s*["\']?(\d+)',
            ):
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    cod = match.group(1)
                    break
        return cod

    @staticmethod
    def _extraer_codigo_secuencial(html: str) -> Optional[str]:
        """
        Extrae el código secuencial (secDescDir) del HTML de tabla.

        Args:
            html: Contenido HTML de la respuesta.

        Returns:
            Código secuencial como cadena, o None si no se encuentra.
        """
        cod = None
        try:
            soup = BeautifulSoup(html, "html.parser")
            enlace = soup.find("a", id=re.compile(r"^linkDescDir_"))
            if enlace and enlace.get("id"):
                match = re.search(r"linkDescDir_(\d+)", enlace["id"])
                if match:
                    cod = match.group(1)
            if not cod:
                for elem in soup.find_all(attrs={"onclick": True}):
                    onclick = elem.get("onclick")
                    match = re.search(r"secDescDir[=:]\s*['\"]?(\d+)", onclick)
                    if match:
                        cod = match.group(1)
                        break
        except Exception as e:
            logger.debug(f"Error BS4 en codSec: {e}")

        if not cod:
            for pattern in (r'id=["\']linkDescDir_(\d+)["\']', r'secDescDir[=:]\s*["\']?(\d+)'):
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    cod = match.group(1)
                    break
        return cod