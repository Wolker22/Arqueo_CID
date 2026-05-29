# -*- coding: utf-8 -*-
import os
import shutil
import pytest
from unittest.mock import MagicMock, patch

from arqueo_cid.tizona.core.auxiliar import (
    rmtree_robusto,
    verificar_espacio_disco,
    obtener_memoria_disponible_mb,
    crear_estructura_salida,
    procesar_tesela_worker
)
from arqueo_cid.config import CARPETA_MDT, CARPETA_DERIVADOS, CARPETA_IMAGENES, CARPETA_STACKS


def test_rmtree_robusto(temp_dir):
    sub = os.path.join(temp_dir, "sub")
    os.makedirs(sub)
    with open(os.path.join(sub, "f.txt"), "w") as f:
        f.write("a")
    rmtree_robusto(sub)
    assert not os.path.exists(sub)
    rmtree_robusto(os.path.join(temp_dir, "noexiste"))  # no error


def test_verificar_espacio_disco(temp_dir):
    ok, msg = verificar_espacio_disco([temp_dir], margen_mb=1)
    assert ok is True

    # Simular que la ruta es inválida porque no se puede crear el directorio
    with patch('os.makedirs', side_effect=OSError("Permiso denegado")):
        ok, msg = verificar_espacio_disco(["/ruta/invalida"], margen_mb=1)
        assert ok is False


def test_obtener_memoria_disponible_mb():
    # Caso sin psutil
    with patch.dict('sys.modules', {'psutil': None}):
        mem = obtener_memoria_disponible_mb()
        assert mem == float('inf')

    # Caso con psutil simulado
    mock_psutil = MagicMock()
    mock_psutil.virtual_memory.return_value.available = 8 * 1024**3  # 8 GB
    with patch.dict('sys.modules', {'psutil': mock_psutil}):
        mem = obtener_memoria_disponible_mb()
        assert mem == 8 * 1024  # 8192 MB


def test_crear_estructura_salida(temp_dir):
    carpetas = crear_estructura_salida(temp_dir)
    # Usar las constantes reales de config
    assert os.path.exists(os.path.join(temp_dir, CARPETA_MDT))
    assert os.path.exists(os.path.join(temp_dir, CARPETA_DERIVADOS))
    assert os.path.exists(os.path.join(temp_dir, CARPETA_IMAGENES))
    assert os.path.exists(os.path.join(temp_dir, CARPETA_STACKS))
    assert carpetas['base'] == temp_dir


@patch('arqueo_cid.tizona.core.auxiliar.ProcesadorLiDAR')
def test_procesar_tesela_worker(mock_proc_class, temp_dir):
    mock_proc = MagicMock()
    mock_proc.ejecutar_pipeline_completo.return_value = None
    mock_proc_class.return_value = mock_proc
    ok, msg, dur = procesar_tesela_worker("/fake.laz", "test", temp_dir, {"resolucion": 0.5})
    assert ok is True
    assert msg == "test"
    assert dur >= 0

    mock_proc.ejecutar_pipeline_completo.side_effect = Exception("error simulado")
    ok, msg, dur = procesar_tesela_worker("/fake.laz", "test", temp_dir, {})
    assert ok is False
    assert "error simulado" in msg