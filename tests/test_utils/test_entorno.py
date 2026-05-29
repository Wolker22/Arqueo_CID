# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock

from arqueo_cid.utils.entorno import (
    verificar_pdal,
    verificar_gdal,
    verificar_torch_cuda,
    verificar_scipy,
    verificar_conexion_cnig,
    verificar_todas_dependencias,
    es_entorno_valido
)


def test_verificar_pdal():
    disponible, msg, version = verificar_pdal()
    assert isinstance(disponible, bool)
    assert isinstance(msg, str)


def test_verificar_gdal():
    disponible, msg, version = verificar_gdal()
    assert isinstance(disponible, bool)


def test_verificar_torch_cuda():
    disponible, msg, cuda = verificar_torch_cuda()
    assert isinstance(disponible, bool)


def test_verificar_scipy():
    disponible, msg = verificar_scipy()
    assert isinstance(disponible, bool)


@patch('requests.head')
def test_verificar_conexion_cnig(mock_head):
    mock_head.return_value.status_code = 200
    ok, msg = verificar_conexion_cnig()
    assert ok is True
    mock_head.side_effect = Exception("Network error")
    ok, msg = verificar_conexion_cnig()
    assert ok is False


def test_verificar_todas_dependencias():
    info = verificar_todas_dependencias()
    assert 'sistema' in info
    assert 'dependencias' in info
    assert 'resumen' in info
    assert 'mensaje_global' in info


def test_es_entorno_valido():
    # Simular un entorno con todas las obligatorias
    info_fake = {
        'dependencias': {
            'gdal': {'obligatoria': True, 'disponible': True},
            'scipy': {'obligatoria': True, 'disponible': True}
        }
    }
    assert es_entorno_valido(info_fake) is True
    info_fake['dependencias']['gdal']['disponible'] = False
    assert es_entorno_valido(info_fake) is False