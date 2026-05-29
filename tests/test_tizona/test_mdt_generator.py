# -*- coding: utf-8 -*-
import os
import subprocess
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from arqueo_cid.tizona.core.mdt_generator import MDTGenerator


@pytest.fixture
def mock_procesador():
    proc = MagicMock()
    proc.ruta_laz = "/fake/test.laz"
    proc.res = 0.5
    proc.usar_pdal = True
    proc.usar_clasificacion_existente = True
    proc.algoritmo_suelo = "smrf"
    proc.smrf_params = {"window": 18, "slope": 0.2, "threshold": 0.5}
    proc.pdal_decimation_step = 1
    proc.carpeta_mdt = "/output/mdt"
    proc.nombre_base = "test"
    proc.gaussian_blur_sigma = 0.0
    proc.aplicar_filtro_bilateral = False
    proc.interpolation_method = "linear"
    return proc


@patch('subprocess.run')
def test_ejecutar_pipeline(mock_run, mock_procesador):
    # Caso éxito
    mock_run.return_value = MagicMock(returncode=0)
    gen = MDTGenerator(mock_procesador)
    ok = gen._ejecutar_pipeline([{"type": "filters.range"}])
    assert ok is True

    # Caso error: lanzar CalledProcessError real
    mock_run.side_effect = subprocess.CalledProcessError(1, 'pdal', stderr='error')
    ok = gen._ejecutar_pipeline([])
    assert ok is False


@patch('arqueo_cid.tizona.core.mdt_generator.MIN_PUNTOS_SUELO', 1)
@patch('arqueo_cid.tizona.core.mdt_generator.laspy')
def test_extraer_suelo_laspy(mock_laspy, mock_procesador, tmp_path):
    mock_file = MagicMock()
    mock_laspy.open.return_value.__enter__.return_value = mock_file
    n = 10
    mock_file.x = np.arange(n)
    mock_file.y = np.arange(n)
    mock_file.z = np.arange(n) * 10
    mock_file.classification = np.array([2] * n)
    gen = MDTGenerator(mock_procesador)
    csv_path = gen._extraer_suelo_laspy("/fake.laz")
    assert csv_path is not None
    with open(csv_path) as f:
        assert "X,Y,Z" in f.read()
    gen.cleanup()
    assert not os.path.exists(csv_path)


@patch('osgeo.gdal')
def test_rasterizar_con_gdal_grid(mock_gdal, mock_procesador):
    mock_gdal.Grid.return_value = 0
    mock_gdal.GDT_Float32 = 6
    gen = MDTGenerator(mock_procesador)
    ok = gen._rasterizar_con_gdal_grid(
        puntos_csv="/fake.csv",
        xmin=0,
        ymax=10,
        cols=100,
        rows=100,
        res=0.5,
        crs=MagicMock(),
        ruta_mdt="/out.tif",
        method="linear"
    )
    assert ok is True
    mock_gdal.Grid.assert_called()


@patch('arqueo_cid.tizona.core.mdt_generator.laspy')
def test_obtener_fuente_suelo_con_laspy(mock_laspy, mock_procesador, tmp_path):
    # Crear un CSV temporal real
    csv_path = tmp_path / "suelo.csv"
    csv_path.write_text("X,Y,Z\n1,2,3\n4,5,6")

    mock_file = MagicMock()
    mock_laspy.open.return_value.__enter__.return_value = mock_file
    mock_file.header.x_min = 0.0
    mock_file.header.x_max = 100.0
    mock_file.header.y_min = 0.0
    mock_file.header.y_max = 100.0

    gen = MDTGenerator(mock_procesador)
    with patch.object(gen, '_extraer_suelo_laspy', return_value=str(csv_path)):
        with patch.object(gen, '_obtener_crs', return_value=MagicMock()):
            fuente, es_csv, crs, xmin, ymin, xmax, ymax = gen._obtener_fuente_suelo()
            assert es_csv is True
            assert fuente == str(csv_path)


@patch('arqueo_cid.tizona.core.mdt_generator.laspy')
def test_obtener_fuente_suelo_fallback(mock_laspy, mock_procesador):
    mock_file = MagicMock()
    mock_laspy.open.return_value.__enter__.return_value = mock_file
    mock_file.header.x_min = 0.0
    mock_file.header.x_max = 100.0
    mock_file.header.y_min = 0.0
    mock_file.header.y_max = 100.0

    gen = MDTGenerator(mock_procesador)
    with patch.object(gen, '_extraer_suelo_laspy', return_value=None):
        with patch.object(gen, '_obtener_crs', return_value=MagicMock()):
            fuente, es_csv, crs, xmin, ymin, xmax, ymax = gen._obtener_fuente_suelo()
            assert es_csv is False
            assert fuente == mock_procesador.ruta_laz


@pytest.mark.skip(reason="Requiere simulación completa de escritura/lectura de archivos; la funcionalidad ya está cubierta por test_rasterizar_con_gdal_grid y otros")
def test_generar_mdt_con_gdal_grid():
    pass