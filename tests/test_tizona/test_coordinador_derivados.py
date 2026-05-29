# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from arqueo_cid.tizona.core.coordinador_derivados import CoordinadorDerivados


@pytest.fixture
def mock_procesador():
    proc = MagicMock()
    proc.config.derivados = ["hillshade", "slope", "curvature"]
    proc.usar_bloques = False
    proc.z_factor = 1.0
    proc.angulos_multidir = [315, 45]
    proc.hillshade_multidir = True
    proc.radio_tpi = [2.0]
    proc.radio_lrm = 2.0
    proc.radio_openness = 5.0
    proc.carpeta_derivados = "/output/derivados"
    proc.nombre_base = "test"
    proc.crs = MagicMock()
    proc.transform = MagicMock()
    proc._is_canceled.return_value = False
    proc._report_progress = MagicMock()
    return proc


@patch('arqueo_cid.tizona.core.coordinador_derivados.guardar_derivado_geotiff')
def test_calcular_derivados_directo(mock_guardar, mock_procesador):
    # Simular backend
    mock_backend = MagicMock()
    mock_backend.hillshade.return_value = np.random.rand(100, 100)
    mock_backend.slope.return_value = np.random.rand(100, 100)
    mock_backend.curvature.return_value = np.random.rand(100, 100)
    mock_procesador.backend = mock_backend

    coord = CoordinadorDerivados(mock_procesador)
    mdt = np.random.rand(100, 100)
    rutas = coord.calcular_derivados(mdt)
    assert len(rutas) == 3
    assert mock_guardar.call_count == 3


@patch('arqueo_cid.tizona.core.coordinador_derivados.procesar_derivados_en_bloques')
@patch('arqueo_cid.tizona.core.coordinador_derivados.guardar_derivado_geotiff')
def test_calcular_derivados_con_bloques(mock_guardar, mock_bloques, mock_procesador):
    # Configurar para usar bloques
    mock_procesador.usar_bloques = True
    mock_procesador.config.derivados = ["hillshade", "tpi"]  # ambos compatibles
    mock_bloques.return_value = {"hillshade": "/out/hillshade.tif", "tpi": "/out/tpi.tif"}

    coord = CoordinadorDerivados(mock_procesador)
    mdt = np.random.rand(100, 100)
    rutas = coord.calcular_derivados(mdt)
    assert rutas == mock_bloques.return_value
    mock_bloques.assert_called_once()
    mock_guardar.assert_not_called()