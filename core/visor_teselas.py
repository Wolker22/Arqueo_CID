# -*- coding: utf-8 -*-
"""
Visor de teselas PNOA LiDAR para Arqueo Cid.
============================================

Gestiona la carga de las mallas shapefile de coberturas LiDAR del PNOA,
fusiona los archivos necesarios y los añade como una capa vectorial
con estilo y mapTips personalizados.
"""

import os
from typing import List, Optional

from qgis.core import (
    QgsVectorLayer,
    QgsFillSymbol,
    QgsProject,
    QgsCoordinateReferenceSystem,
)

from ..config import (
    NOMBRE_CAPA_TESELAS,
    DIR_MALLAS_BASE,
    ESTILO_TESELAS,
    MAPTIP_CAMPO_PREFERIDO,
    MAPTIP_CAMPOS_ALTERNOS,
    MAPTIP_HTML_TEMPLATE,
    CRS_FUSION_TESELAS,
)
from ..utils.logging import get_logger

logger = get_logger('ArqueoCid.visor_teselas')


def _buscar_shapefiles_recursivamente(directorio: str) -> List[str]:
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
            if archivo.lower().endswith('.shp'):
                ruta_completa = os.path.join(raiz, archivo)
                # Excluir versiones en EPSG:4326 para mantener solo UTM
                if '_4326' in archivo:
                    continue
                shp_encontrados.append(ruta_completa)
    return shp_encontrados


def _fusionar_shapefiles(lista_rutas: List[str], nombre_capa: str) -> Optional[QgsVectorLayer]:
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

    # Si solo hay un archivo, cargarlo directamente
    if len(lista_rutas) == 1:
        capa = QgsVectorLayer(lista_rutas[0], nombre_capa, "ogr")
        return capa if capa.isValid() else None

    # Múltiples archivos: usar processing para fusionarlos
    try:
        import processing
        resultado = processing.run(
            "native:mergevectorlayers",
            {
                'LAYERS': lista_rutas,
                'CRS': QgsCoordinateReferenceSystem(CRS_FUSION_TESELAS),
                'OUTPUT': 'memory:'
            }
        )
        capa = resultado['OUTPUT']
        capa.setName(nombre_capa)
        return capa
    except Exception as e:
        logger.error(f"Error al fusionar shapefiles: {e}")
        return None


def actualizar_capa_teselas(cobertura: str = 'todas') -> Optional[QgsVectorLayer]:
    """
    Carga o actualiza la capa de teselas para la cobertura indicada.
    Elimina la capa existente si ya está cargada.

    Args:
        cobertura: 'todas', '1', '2' o '3'.

    Returns:
        Capa vectorial añadida, o None si no se encontraron datos.
    """
    # Eliminar capa anterior si existe
    for capa in QgsProject.instance().mapLayers().values():
        if capa.name() == NOMBRE_CAPA_TESELAS:
            QgsProject.instance().removeMapLayer(capa.id())
            break

    # Determinar directorio de la cobertura
    ruta_cobertura = os.path.join(DIR_MALLAS_BASE, f"cobertura_{cobertura}")
    if not os.path.isdir(ruta_cobertura):
        logger.warning(f"Directorio de malla no encontrado: {ruta_cobertura}")
        return None

    shp_encontrados = _buscar_shapefiles_recursivamente(ruta_cobertura)
    if not shp_encontrados:
        logger.warning(f"No se encontraron shapefiles en {ruta_cobertura}")
        return None

    capa = _fusionar_shapefiles(shp_encontrados, NOMBRE_CAPA_TESELAS)
    if not capa or not capa.isValid():
        logger.error("No se pudo crear la capa fusionada de teselas")
        return None

    # Aplicar estilo visual
    simbolo = QgsFillSymbol.createSimple(ESTILO_TESELAS)
    capa.renderer().setSymbol(simbolo)
    capa.setLabelsEnabled(False)

    # Configurar MapTip (tooltip informativo)
    campos = [field.name() for field in capa.fields()]
    campo_etiqueta = MAPTIP_CAMPO_PREFERIDO
    if campo_etiqueta not in campos:
        for alt in MAPTIP_CAMPOS_ALTERNOS:
            if alt in campos:
                campo_etiqueta = alt
                break
        else:
            campo_etiqueta = campos[0] if campos else ""

    html_maptip = MAPTIP_HTML_TEMPLATE.format(campo_etiqueta)
    capa.setMapTipTemplate(html_maptip)

    # Añadir al proyecto
    QgsProject.instance().addMapLayer(capa)
    capa.triggerRepaint()
    logger.info(f"Capa de teselas cargada para cobertura {cobertura}")
    return capa