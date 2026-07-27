import json
import urllib.parse
import urllib.request

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from ..config import (
    BUSCADOR_ZOOM_SCALE,
    CRS_BUSCADOR_WGS84,
    NOMBRE_PLUGIN,
    NOMINATIM_BASE_URL,
)

# Importamos el diálogo desde la carpeta UI
from ..gui.dialogo_buscador import DialogoBuscador
from ..utils.logging import get_logger

logger = get_logger('ArqueoCid.buscador')


def buscar_lugar_y_centrar(iface: QgisInterface) -> None:
    """
    Muestra el diálogo, consulta Nominatim y centra el mapa.

    Args:
        iface: Interfaz de QGIS.
    """
    dialogo = DialogoBuscador(iface.mainWindow())
    if dialogo.exec_() != QDialog.Accepted:
        return

    lugar = dialogo.lugar()

    # 1. Petición a la API
    try:
        # Usamos f-string para insertar el lugar directamente en el texto
        iface.messageBar().pushMessage(NOMBRE_PLUGIN, f"Buscando {lugar}...", level=0)

        params = {"q": f"{lugar}, Spain", "format": "json", "limit": 1}
        url = f"{NOMINATIM_BASE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': NOMBRE_PLUGIN})

        with urllib.request.urlopen(req, timeout=5) as respuesta:
            datos = json.loads(respuesta.read().decode('utf-8'))

        if not datos:
            # Reemplazado el .format() por un f-string
            QMessageBox.warning(iface.mainWindow(), "Sin resultados", f"No se encontró el lugar: {lugar}")
            return

        lat = float(datos[0]['lat'])
        lon = float(datos[0]['lon'])

    except Exception as e:
        logger.exception(f"Error en búsqueda de '{lugar}': {e}")
        # Mensaje de error escrito directamente en el código
        QMessageBox.critical(iface.mainWindow(), "Error de red", "No se pudo conectar con el servicio de búsqueda.")
        return

    # 2. Transformar coordenadas al CRS del proyecto
    crs_wgs84 = QgsCoordinateReferenceSystem(CRS_BUSCADOR_WGS84)
    crs_proyecto = QgsProject.instance().crs()
    transform = QgsCoordinateTransform(crs_wgs84, crs_proyecto, QgsProject.instance())
    punto_destino = transform.transform(QgsPointXY(lon, lat))

    # 3. Centrar el mapa
    lienzo = iface.mapCanvas()
    lienzo.setCenter(punto_destino)
    lienzo.zoomScale(BUSCADOR_ZOOM_SCALE)
    lienzo.refresh()

    # Mensaje final también convertido a f-string
    iface.messageBar().pushMessage(NOMBRE_PLUGIN, f"Vista centrada en {lugar}", level=0, duration=5)