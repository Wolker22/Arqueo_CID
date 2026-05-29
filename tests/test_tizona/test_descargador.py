# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
from arqueo_cid.tizona.core.descargador import (
    validar_archivo_descargado,
    archivo_coincide_tipo,
    filtrar_archivos_por_tipo,
    DescargadorCNIG
)


def test_validar_archivo_descargado(tmp_path):
    f = tmp_path / "test.laz"
    # Escribir al menos MIN_FILE_SIZE_BYTES (1024) bytes
    f.write_bytes(b'LASF' + b'\x00' * 2000)
    ok, msg = validar_archivo_descargado(str(f))
    assert ok is True
    f.write_bytes(b'XYZ')
    ok, msg = validar_archivo_descargado(str(f))
    assert ok is False


def test_archivo_coincide_tipo():
    assert archivo_coincide_tipo("PNOA_RGB.laz", "RGB") is True
    assert archivo_coincide_tipo("PNOA_IRC.laz", "RGB") is False
    assert archivo_coincide_tipo("PNOA_IRC.laz", "IRC") is True
    assert archivo_coincide_tipo("PNOA_COL.laz", "Ambos") is True


def test_filtrar_archivos_por_tipo():
    lista = ["a_RGB.laz", "b_IRC.laz", "c_COL.laz"]
    assert filtrar_archivos_por_tipo(lista, "RGB") == ["a_RGB.laz"]
    assert filtrar_archivos_por_tipo(lista, "IRC") == ["b_IRC.laz"]
    assert filtrar_archivos_por_tipo(lista, "Ambos") == lista


@patch('arqueo_cid.tizona.core.descargador.requests.Session')
def test_descargador_inicializacion(mock_session):
    desc = DescargadorCNIG(timeout=30)
    assert desc.timeout == 30
    desc._regenerar_sesion()
    assert desc.sesion is not None