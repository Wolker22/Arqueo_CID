# -*- coding: utf-8 -*-
"""
Pestaña de Rendimiento de COLADA
---------------------------------

Permite ajustar los recursos de hardware dedicados al postprocesado:
- Número de procesos GPU (máximo de workers concurrentes).
- Número de hilos de CPU para tareas paralelizables.
- Número de trabajadores del DataLoader (para carga de datos en entrenamiento).

La interfaz sigue la paleta coral de COLADA y la estructura visual
unificada. Incluye scroll interno para adaptarse a ventanas pequeñas.
Todos los textos, rangos y tooltips se centralizan en config.py.
"""

from typing import Optional

from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QScrollArea,
    QFrame,
)

from ....config import (
    MAX_GPU_WORKERS,
    CPU_WORKERS,
    NUM_WORKERS_DATALOADER,
    COLADA_COLOR_PRIMARIO_OSC,
    COLADA_COLOR_SUPERFICIE,
    COLADA_COLOR_BORDE,
    COLADA_COLOR_FONDO,
    RENDIMIENTO_GPU_RANGE,
    RENDIMIENTO_CPU_RANGE,
    RENDIMIENTO_GPU_TOOLTIP,
    RENDIMIENTO_CPU_TOOLTIP,
    RENDIMIENTO_GROUP_TITLE,
)
from ....utils.logging import get_logger

logger = get_logger('Colada.gui.rendimiento')


class TabRendimiento(QWidget):
    """
    Pestaña de configuración de rendimiento para Colada.

    Attributes:
        spin_gpu: Control para número de procesos GPU.
        spin_cpu: Control para número de hilos CPU.
        spin_dataloader: Control para número de trabajadores del DataLoader.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self._aplicar_hoja_estilos()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Construye la interfaz con scroll y grupo de hardware."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Grupo de hardware
        grupo_hw = QGroupBox(RENDIMIENTO_GROUP_TITLE)
        form_hw = QFormLayout(grupo_hw)
        form_hw.setSpacing(6)

        # Procesos GPU
        self.spin_gpu = QSpinBox()
        self.spin_gpu.setRange(*RENDIMIENTO_GPU_RANGE)
        self.spin_gpu.setValue(MAX_GPU_WORKERS)
        self.spin_gpu.setToolTip(RENDIMIENTO_GPU_TOOLTIP)
        form_hw.addRow("Procesos GPU:", self.spin_gpu)

        # Hilos CPU
        self.spin_cpu = QSpinBox()
        self.spin_cpu.setRange(*RENDIMIENTO_CPU_RANGE)
        self.spin_cpu.setValue(CPU_WORKERS)
        self.spin_cpu.setToolTip(RENDIMIENTO_CPU_TOOLTIP)
        form_hw.addRow("Hilos CPU:", self.spin_cpu)

        # Trabajadores del DataLoader
        self.spin_dataloader = QSpinBox()
        self.spin_dataloader.setRange(0, 8)
        self.spin_dataloader.setValue(NUM_WORKERS_DATALOADER)
        self.spin_dataloader.setToolTip(
            "Número de procesos para cargar datos (0 = sin multiprocesamiento, más estable en Windows)."
        )
        form_hw.addRow("Hilos DataLoader:", self.spin_dataloader)

        layout.addWidget(grupo_hw)
        layout.addStretch()

        scroll.setWidget(w)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Métodos públicos para obtener/aplicar parámetros
    # ------------------------------------------------------------------

    def obtener_parametros(self) -> dict:
        """
        Devuelve un diccionario con los parámetros actuales de rendimiento.

        Returns:
            Diccionario con claves: 'max_gpu_workers', 'cpu_workers', 'num_workers_dataloader'
        """
        return {
            'max_gpu_workers': self.spin_gpu.value(),
            'cpu_workers': self.spin_cpu.value(),
            'num_workers_dataloader': self.spin_dataloader.value(),
        }

    def aplicar_parametros(self, params: dict) -> None:
        """
        Aplica parámetros de rendimiento desde un diccionario (ej. perfil).

        Args:
            params: Diccionario con las claves correspondientes.
        """
        if 'max_gpu_workers' in params:
            self.spin_gpu.setValue(params['max_gpu_workers'])
        if 'cpu_workers' in params:
            self.spin_cpu.setValue(params['cpu_workers'])
        if 'num_workers_dataloader' in params:
            self.spin_dataloader.setValue(params['num_workers_dataloader'])

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------

    def _aplicar_hoja_estilos(self) -> None:
        """Aplica la hoja de estilos definida en config."""
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {COLADA_COLOR_BORDE};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                background-color: {COLADA_COLOR_SUPERFICIE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {COLADA_COLOR_PRIMARIO_OSC};
            }}
            QLabel {{
                font-size: 12px;
            }}
            QScrollArea {{
                border: none;
            }}
        """)