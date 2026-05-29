# -*- coding: utf-8 -*-
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS
import pytest
from arqueo_cid.tizona.core.salidas import (
    perfil_derivado,
    guardar_derivado_geotiff,
    GeneradorMetadatos
)

def test_perfil_derivado():
    crs = CRS.from_epsg(25830)
    transform = from_origin(0, 100, 1, 1)
    perfil = perfil_derivado(crs, transform, 100, 200, np.float32, nodata=-9999)
    assert perfil['driver'] == 'GTiff'
    assert perfil['height'] == 100
    assert perfil['width'] == 200
    assert perfil['dtype'] == np.float32
    assert perfil['nodata'] == -9999

def test_guardar_derivado_geotiff(tmp_path):
    arr = np.random.rand(50,50).astype(np.float32)
    ruta = tmp_path / "test.tif"
    crs = CRS.from_epsg(25830)
    transform = from_origin(0, 50, 1, 1)
    guardar_derivado_geotiff(arr, str(ruta), crs, transform)
    assert ruta.exists()
    with rasterio.open(ruta) as src:
        data = src.read(1)
        assert data.shape == (50,50)

def test_calcular_estadisticas():
    arr = np.array([1,2,3,4,5, np.nan])
    stats = GeneradorMetadatos.calcular_estadisticas(arr)
    assert stats['min'] == 1.0
    assert stats['max'] == 5.0
    assert stats['mean'] == 3.0

def test_calcular_calidad_mdt():
    mdt = np.random.rand(100,100)
    mdt[10:20,10:20] = np.nan
    calidad = GeneradorMetadatos.calcular_calidad_mdt(mdt, resolucion=1.0)
    assert calidad['porcentaje_nan'] > 0
    assert 'rugosidad_residual_std_slope_grados' in calidad