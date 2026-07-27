"""
Visor de teselas PNOA LiDAR para Arqueo Cid.
============================================

Gestiona la carga de mapas base y mallas shapefile de coberturas LiDAR del PNOA,
fusiona los archivos necesarios y los añade como una capa vectorial
con estilo y mapTips personalizados. Centra la vista y maneja la interacción con el usuario.
"""

import os
from typing import Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFillSymbol,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtWidgets import QMessageBox

# Importaciones relativas según tu estructura central
from ..config import (
    CAMPOS_MAPTIP,
    CRS_FUSION_TESELAS,
    DIR_MALLAS_BASE,
    ESTILO_TESELAS,
    MAPTIP_HTML_TEMPLATE,
    NOMBRE_CAPA_TESELAS,
    NOMBRE_MAPA_BASE,
    NOMBRE_PLUGIN,
    URL_ORTOFOTO_PNOA,
)

# Importaciones asumidas de otros módulos
from ..ui.dialogos import DialogoCobertura
from ..utils.logging import get_logger

# Inicializamos el logger una sola vez para todo el archivo
logger = get_logger(NOMBRE_PLUGIN)


# ============================================================================
# FUNCIONES DE GESTIÓN DE MALLAS
# ============================================================================

def buscar_shapefiles(directorio: str) -> list[str]:
    """
    Busca recursivamente todos los archivos .shp en un directorio,
    excluyendo aquellos que contengan '_4326' en el nombre (proyección geográfica).

    Args:
        directorio: Ruta al directorio raíz.

    Returns:
        Lista de rutas absolutas de los shapefiles encontrados.
    """
    shp_encontrados = []

    for raiz, _, archivos in os.walk(directorio):
        for archivo in archivos:
            if archivo.lower().endswith(".shp"):
                ruta_completa = os.path.join(raiz, archivo)
                shp_encontrados.append(ruta_completa)
    return shp_encontrados


def fusionar_shapefiles(lista_rutas: list[str], nombre_capa: str) -> Optional[QgsVectorLayer]:
    """
    Fusiona varios shapefiles en una sola capa de memoria usando el algoritmo
    nativo de QGIS 'mergevectorlayers'.

    Args:
        lista_rutas: Lista de rutas a los shapefiles.
        nombre_capa: Nombre de la capa resultante.

    Returns:
        Capa fusionada, o None si no se pudo.
    """
    if not lista_rutas:
        return None

    try:
        import processing

        resultado = processing.run(
            "native:mergevectorlayers",
            {
                "LAYERS": lista_rutas,
                "CRS": QgsCoordinateReferenceSystem(CRS_FUSION_TESELAS),
                "OUTPUT": "memory:",
            },
        )
        capa = resultado["OUTPUT"]
        capa.setName(nombre_capa)
        return capa
    except Exception as e:
        logger.exception(f"Error al fusionar shapefiles: {e}")
        return None

def estilizar_shapefiles(capa: QgsVectorLayer) -> None:
    """Aplica estilo visual y configura el MapTip (tooltip) para la capa."""

    # 1. Aplicar estilo visual
    simbolo = QgsFillSymbol.createSimple(ESTILO_TESELAS)
    capa.renderer().setSymbol(simbolo)
    capa.setLabelsEnabled(False)

    # 2. Configurar MapTip (tooltip informativo)
    campos = [field.name() for field in capa.fields()]

    # Buscamos en nuestra única lista el primer campo que exista en la capa.
    campo_etiqueta = next(
        (columna for columna in CAMPOS_MAPTIP if columna in campos),
        campos[0] if campos else ""
    )

    # Inyectamos el nombre de la columna en la plantilla
    html_maptip = MAPTIP_HTML_TEMPLATE.format(campo_etiqueta)
    capa.setMapTipTemplate(html_maptip)

def actualizar_cobertura(cobertura: str = "todas") -> Optional[QgsVectorLayer]:
    """
    Carga o actualiza la capa de teselas para la cobertura indicada.
    Elimina la capa existente si ya está cargada.

    Args:
        cobertura: 'todas', '1', '2' o '3'.

    Returns:
        Capa vectorial añadida, o None si no se encontraron datos.
    """
    proyecto = QgsProject.instance()

    # Eliminar TODAS las capas iterando
    capas_existentes = proyecto.mapLayers()
    for capa_id in capas_existentes:  # capa_id ya es el texto con el ID
        proyecto.removeMapLayer(capa_id)

    # Determinar directorio de la cobertura
    ruta_cobertura = os.path.join(DIR_MALLAS_BASE, f"cobertura_{cobertura}")
    if not os.path.isdir(ruta_cobertura):
        logger.warning(f"Directorio de malla no encontrado: {ruta_cobertura}")
        return None

    # Busca los SHP
    shp_encontrados = buscar_shapefiles(ruta_cobertura)

    # Determinar qué cargar según los archivos encontrados
    if not shp_encontrados:
        logger.warning(f"No se encontraron shapefiles en {ruta_cobertura}")
        return None
    elif len(shp_encontrados) == 1:
        capa = QgsVectorLayer(shp_encontrados[0], NOMBRE_CAPA_TESELAS, "ogr")
    else:
        capa = fusionar_shapefiles(shp_encontrados, NOMBRE_CAPA_TESELAS)

    # Validar la capa
    if not capa or not capa.isValid():
        logger.error("No se cargar la capa de la cobertura")
        return None

    # LLAMAMOS a la función de estilización pasándole la capa recién creada
    estilizar_shapefiles(capa)

    # Añadir al proyecto
    proyecto.addMapLayer(capa)
    capa.triggerRepaint()
    logger.info(f"Capa de teselas cargada para cobertura {cobertura}")

    return capa

# ============================================================================
# FUNCIONES DE VISTA Y MAPA BASE
# ============================================================================

def cargar_mapa_base() -> bool:
    """
    Añade la ortofoto del PNOA como capa WMS.
    Limpia el mapa actual primero.

    Returns:
        True si se cargó correctamente, False en caso contrario.
    """
    proyecto = QgsProject.instance()
    nombre_capa = NOMBRE_MAPA_BASE

    # URI del servicio WMS (formato simple y fiable)
    uri = (
        f"crs=EPSG:25830&format=image/jpeg"
        f"&layers=OI.OrthoimageCoverage&styles=default"
        f"&url={URL_ORTOFOTO_PNOA}"
    )
    capa = QgsRasterLayer(uri, nombre_capa, "wms")

    if capa.isValid():
        proyecto.addMapLayer(capa, False)
        root = proyecto.layerTreeRoot()
        root.insertLayer(-1, capa)
        logger.info("Mapa base PNOA cargado correctamente")
        return True
    else:
        logger.warning("No se pudo cargar la ortofoto PNOA.")
        return False


def centrar_vista_en_espana(iface) -> None:
    """Ajusta el lienzo de QGIS para mostrar la Península Ibérica y Baleares."""
    proyecto = QgsProject.instance()
    canvas = iface.mapCanvas()

    crs_utm30 = QgsCoordinateReferenceSystem("EPSG:25830")
    proyecto.setCrs(crs_utm30)

    # Coordenadas WGS84 para la Península Ibérica
    xmin, ymin = -9.5, 35.5
    xmax, ymax = 4.5, 44.0
    rect_wgs84 = QgsRectangle(xmin, ymin, xmax, ymax)

    crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(crs_wgs84, crs_utm30, proyecto)
    rect_proyecto = transform.transformBoundingBox(rect_wgs84)

    canvas.setExtent(rect_proyecto)
    canvas.refresh()
    logger.info("Vista centrada en la Península Ibérica")


def seleccionar_cobertura(iface) -> None:
    """Abre el diálogo de cobertura y carga mapa + malla si el usuario acepta."""

    dialogo = DialogoCobertura(iface.mainWindow())
    cobertura = dialogo.cobertura_seleccionada()

    if not cargar_mapa_base():
        QMessageBox.warning(
            iface.mainWindow(),
            "Mapa base no disponible",
            "Verifique su conexión a Internet o la disponibilidad del servicio WMS.",
        )
    else:
        centrar_vista_en_espana(iface)

    capa = actualizar_cobertura(cobertura)

    if capa is None:
        ruta_mallas = os.path.join('resources', 'mallas', f'cobertura_{cobertura}')
        QMessageBox.warning(
            iface.mainWindow(),
            "Malla no disponible",
            f"No se encontró la malla para la cobertura {cobertura}.\n"
            f"Asegúrese de que los shapefiles están en:\n{ruta_mallas}",
        )
    else:
        iface.messageBar().pushMessage(
            NOMBRE_PLUGIN,
            f"Malla de teselas cargada para cobertura {cobertura}.",
            level=0,
            duration=3,
        )
        logger.info(f"Cobertura seleccionada: {cobertura}")
