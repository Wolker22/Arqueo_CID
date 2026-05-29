# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from rasterio.transform import from_origin

from arqueo_cid.tizona.core.procesador_lidar import ProcesadorLiDAR
from arqueo_cid.utils.processing_config import ConfiguracionProcesamiento


@pytest.fixture
def mock_config():
    config = MagicMock(spec=ConfiguracionProcesamiento)
    config.resolucion = 0.5
    config.z_factor = 1.0
    config.radio_openness = 5.0
    config.radio_lrm = 2.0
    config.radio_tpi_multiescala = [2.0, 5.0]
    config.multidirectional = True
    config.angulos_multidir = [315, 45]
    config.algoritmo_suelo = "smrf"
    config.usar_gpu = False
    config.usar_pdal = True
    config.pdal_decimation_step = 2
    config.memoria_max_mb = 4096
    config.aplicar_filtro_mediana = False
    config.usar_clasificacion_existente = True
    config.gaussian_blur_sigma = 0.0
    config.interpolation_method = "linear"
    config.derivados = ["hillshade", "slope"]
    config.generar_imagenes_png = False
    config.normalizar_imagenes = True
    config.png_perc_low = 2.0
    config.png_perc_high = 98.0
    config.exportar_stack = False
    config.normalizar_stack = False
    config.stack_perc_low = 1.0
    config.stack_perc_high = 99.0
    config.incluir_mascara_stack = False
    config.generar_metadatos_json = True
    config.generar_manifiesto_ia = False
    return config


@patch('arqueo_cid.tizona.core.procesador_lidar.MDTGenerator')
@patch('arqueo_cid.tizona.core.procesador_lidar.PytorchBackend')
def test_procesador_init(mock_backend, mock_mdt_gen, mock_config):
    proc = ProcesadorLiDAR("/fake/test.laz", "/output", mock_config)
    assert proc.ruta_laz == "/fake/test.laz"
    assert proc.carpeta_salida == "/output"
    assert proc.config == mock_config
    assert proc.nombre_base == "test"
    mock_mdt_gen.assert_called_once_with(proc)
    mock_backend.assert_called_once_with(proc)


@patch('arqueo_cid.tizona.core.procesador_lidar.MDTGenerator')
@patch('arqueo_cid.tizona.core.procesador_lidar.PytorchBackend')
def test_generar_mdt(mock_backend, mock_mdt_gen, mock_config, tmp_path):
    mock_generator = MagicMock()
    mock_mdt_gen.return_value = mock_generator
    mock_generator.generar_mdt.return_value = (
        "/fake/mdt.tif",
        np.random.rand(100, 100),
        MagicMock(),
        MagicMock(),
    )
    proc = ProcesadorLiDAR("/fake/test.laz", str(tmp_path), mock_config)
    proc._generar_mdt()
    assert proc.mdt_array is not None
    assert proc.crs is not None
    assert proc.transform is not None
    mock_generator.generar_mdt.assert_called_once()


@patch('arqueo_cid.tizona.core.procesador_lidar.MDTGenerator')
@patch('arqueo_cid.tizona.core.procesador_lidar.PytorchBackend')
def test_calcular_derivados(mock_backend, mock_mdt_gen, mock_config, tmp_path):
    mock_backend_instance = MagicMock()
    mock_backend.return_value = mock_backend_instance
    mock_backend_instance.hillshade.return_value = np.random.rand(100, 100)
    mock_backend_instance.slope.return_value = np.random.rand(100, 100)

    proc = ProcesadorLiDAR("/fake/test.laz", str(tmp_path), mock_config)
    proc.mdt_array = np.random.rand(100, 100)
    proc._calcular_derivados()
    assert "hillshade" in proc.derivados_arrays
    assert "slope" in proc.derivados_arrays


@patch('arqueo_cid.tizona.core.procesador_lidar.exportar_imagenes')
@patch('arqueo_cid.tizona.core.procesador_lidar.exportar_stack_multibanda')
@patch('arqueo_cid.tizona.core.procesador_lidar.GeneradorMetadatos')
@patch('arqueo_cid.tizona.core.procesador_lidar.MDTGenerator')
@patch('arqueo_cid.tizona.core.procesador_lidar.PytorchBackend')
def test_exportar_resultados(
    mock_backend, mock_mdt_gen, mock_meta, mock_stack, mock_png, mock_config, tmp_path
):
    # Importar CRS real para evitar errores
    from rasterio.crs import CRS

    proc = ProcesadorLiDAR("/fake/test.laz", str(tmp_path), mock_config)
    proc.mdt_array = np.random.rand(100, 100)
    # Proporcionar un CRS válido (EPSG:25830)
    proc.crs = CRS.from_epsg(25830)
    # Transform real
    from rasterio.transform import from_origin
    proc.transform = from_origin(0, 0, 1, 1)
    proc.derivados_arrays = {"hillshade": np.random.rand(100, 100)}
    proc._exportar_resultados(10.0)
    mock_meta.generar.assert_called_once()
    mock_stack.assert_not_called()
    mock_png.assert_not_called()