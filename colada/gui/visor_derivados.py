# -*- coding: utf-8 -*-
"""
Visor de imágenes derivadas de COLADA.
---------------------------------------
Muestra imágenes ráster 2D con soporte de colormap tipo temperatura.
"""

import numpy as np
from typing import Optional

from qgis.PyQt.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from qgis.PyQt.QtCore import Qt, QRectF, pyqtSignal
from qgis.PyQt.QtGui import QPixmap, QImage, QWheelEvent, QPainter

from ...config import (
    COLADA_COLOR_FONDO,
    COLADA_COLOR_BORDE,
    VISOR_PLACEHOLDER_TEXT,
    VISOR_PLACEHOLDER_FONT_SIZE,
    VISOR_ZOOM_FACTOR,
    VISOR_NORMALIZE_LOW_PERC,
    VISOR_NORMALIZE_HIGH_PERC,
)
from ...utils.logging import get_logger

logger = get_logger('Colada.gui.visor')


class VisorDerivados(QGraphicsView):
    """
    Visor de imágenes raster con zoom, arrastre y colormap personalizado.
    """

    def __init__(self, parent: Optional['QWidget'] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._zoom_factor: float = VISOR_ZOOM_FACTOR

        self.setMinimumSize(200, 200)
        self.setStyleSheet(f"""
            QGraphicsView {{
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 4px;
                background-color: {COLADA_COLOR_FONDO};
            }}
        """)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(self.renderHints() | QPainter.SmoothPixmapTransform)

        # Crear placeholder inicial
        self._crear_placeholder()

    # ------------------------------------------------------------------
    # Métodos privados para gestión del placeholder
    # ------------------------------------------------------------------

    def _crear_placeholder(self) -> None:
        """Crea el elemento de texto de placeholder y lo añade a la escena."""
        self._placeholder = self._scene.addText(VISOR_PLACEHOLDER_TEXT)
        self._placeholder.setDefaultTextColor(Qt.gray)
        font = self._placeholder.font()
        font.setPointSize(VISOR_PLACEHOLDER_FONT_SIZE)
        self._placeholder.setFont(font)
        self._placeholder.setVisible(True)
        # Ajustar la escena para que se vea el placeholder
        self._scene.setSceneRect(QRectF(0, 0, 400, 300))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def _limpiar_escena(self) -> None:
        """Limpia la escena y elimina la referencia al pixmap item."""
        self._scene.clear()
        self._pixmap_item = None

    # ------------------------------------------------------------------
    # Métodos de normalización y colormap
    # ------------------------------------------------------------------

    @staticmethod
    def _aplicar_colormap(img_uint8: np.ndarray) -> QImage:
        """
        Aplica un colormap térmico (azul -> cian -> verde -> amarillo -> rojo).

        Args:
            img_uint8: Array 2D de uint8 (valores 0-255).

        Returns:
            QImage en formato RGB888.
        """
        alto, ancho = img_uint8.shape
        rgb = np.zeros((alto, ancho, 3), dtype=np.uint8)
        control = [
            (0, (0, 0, 255)),
            (64, (0, 255, 255)),
            (128, (0, 255, 0)),
            (192, (255, 255, 0)),
            (255, (255, 0, 0))
        ]
        lookup = np.zeros((256, 3), dtype=np.uint8)
        for v in range(256):
            for i in range(len(control) - 1):
                v0, c0 = control[i]
                v1, c1 = control[i + 1]
                if v0 <= v <= v1:
                    if v1 == v0:
                        t = 0.0
                    else:
                        t = (v - v0) / (v1 - v0)
                    r = int(c0[0] + t * (c1[0] - c0[0]))
                    g = int(c0[1] + t * (c1[1] - c0[1]))
                    b = int(c0[2] + t * (c1[2] - c0[2]))
                    lookup[v] = [r, g, b]
                    break
        flat = img_uint8.ravel()
        rgb_flat = lookup[flat]
        rgb[:, :, 0] = rgb_flat[:, 0].reshape(alto, ancho)
        rgb[:, :, 1] = rgb_flat[:, 1].reshape(alto, ancho)
        rgb[:, :, 2] = rgb_flat[:, 2].reshape(alto, ancho)
        # Crear QImage con copia para evitar problemas de memoria
        qimagen = QImage(rgb.data, ancho, alto, ancho * 3, QImage.Format_RGB888)
        return qimagen.copy()

    def _normalizar_banda(self, banda: np.ndarray) -> np.ndarray:
        """
        Normaliza una banda (2D) a uint8 usando percentiles configurables.

        Args:
            banda: Array 2D de float32.

        Returns:
            Array 2D de uint8.
        """
        mascara_finitos = np.isfinite(banda)
        if not np.any(mascara_finitos):
            logger.warning("La banda no contiene valores finitos.")
            return np.zeros(banda.shape, dtype=np.uint8)
        valores_finitos = banda[mascara_finitos]
        low = np.percentile(valores_finitos, VISOR_NORMALIZE_LOW_PERC)
        high = np.percentile(valores_finitos, VISOR_NORMALIZE_HIGH_PERC)
        if high <= low:
            low = np.min(valores_finitos)
            high = np.max(valores_finitos)
        if high <= low:
            logger.warning(f"Rango nulo (low={low}, high={high})")
            return np.zeros(banda.shape, dtype=np.uint8)
        img_clipped = np.clip(banda, low, high)
        img_norm = ((img_clipped - low) / (high - low) * 255).astype(np.uint8)
        img_norm = np.nan_to_num(img_norm, nan=0)
        return img_norm

    # ------------------------------------------------------------------
    # Método principal de visualización
    # ------------------------------------------------------------------

    def mostrar_imagen(self, matriz_imagen: Optional[np.ndarray], colormap: bool = False) -> None:
        """
        Muestra una imagen en el visor.

        Args:
            matriz_imagen: Array de la imagen (2D o 3D). Si es None o vacío, muestra placeholder.
            colormap: Si es True, aplica colormap térmico a la imagen.
        """
        # Limpiar la escena actual (borra todo, incluido el placeholder)
        self._limpiar_escena()

        if matriz_imagen is None or matriz_imagen.size == 0:
            logger.info("Imagen vacía o None, mostrando placeholder")
            self._crear_placeholder()
            return

        # RGB directo (3 canales, sin colormap)
        if matriz_imagen.ndim == 3 and matriz_imagen.shape[0] == 3 and not colormap:
            img_rgb = np.transpose(matriz_imagen, (1, 2, 0))
            if img_rgb.dtype != np.uint8:
                vmin, vmax = np.percentile(img_rgb, [2, 98])
                if vmax > vmin:
                    img_rgb = np.clip(img_rgb, vmin, vmax)
                    img_rgb = ((img_rgb - vmin) / (vmax - vmin) * 255).astype(np.uint8)
                else:
                    img_rgb = np.zeros_like(img_rgb, dtype=np.uint8)
            alto, ancho, _ = img_rgb.shape
            qimagen = QImage(img_rgb.data, ancho, alto, ancho * 3, QImage.Format_RGB888).copy()
            self._mostrar_qimage(qimagen)
            return

        # Banda única (2D) o extraer primera banda de un stack
        if matriz_imagen.ndim == 3:
            banda = matriz_imagen[0, :, :]
        else:
            banda = matriz_imagen

        img_uint8 = self._normalizar_banda(banda)
        logger.debug(f"Imagen normalizada a uint8, shape={img_uint8.shape}")

        if colormap:
            qimagen = self._aplicar_colormap(img_uint8)
        else:
            alto, ancho = img_uint8.shape
            qimagen = QImage(img_uint8.data, ancho, alto, ancho, QImage.Format_Grayscale8).copy()

        self._mostrar_qimage(qimagen)

    def _mostrar_qimage(self, qimagen: QImage) -> None:
        """
        Muestra una QImage en la escena, ajustando la vista.

        Args:
            qimagen: Imagen a mostrar.
        """
        pixmap = QPixmap.fromImage(qimagen)
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        logger.info("Imagen mostrada en el visor")

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Maneja la rueda del ratón para hacer zoom."""
        if not self._pixmap_item:
            return
        factor = self._zoom_factor if event.angleDelta().y() > 0 else 1.0 / self._zoom_factor
        self.scale(factor, factor)
        self.setFocus()