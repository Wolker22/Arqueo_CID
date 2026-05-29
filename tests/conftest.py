# -*- coding: utf-8 -*-
import sys
import os
from unittest.mock import MagicMock, patch

# ----------------------------------------------------------------------
# 1. Parche completo de QGIS y PyQt
# ----------------------------------------------------------------------
qgis_mock = MagicMock()
qgis_mock.core = MagicMock()
pyqt_mock = MagicMock()
qgis_mock.PyQt = pyqt_mock
pyqt_mock.QtCore = MagicMock()
pyqt_mock.QtGui = MagicMock()
pyqt_mock.QtWidgets = MagicMock()
pyqt_mock.QtCore.Qt = MagicMock()
pyqt_mock.QtWidgets.QApplication = MagicMock()
pyqt_mock.QtWidgets.QMessageBox = MagicMock()
qgis_mock.utils = MagicMock()

sys.modules['qgis'] = qgis_mock
sys.modules['qgis.core'] = qgis_mock.core
sys.modules['qgis.PyQt'] = pyqt_mock
sys.modules['qgis.PyQt.QtCore'] = pyqt_mock.QtCore
sys.modules['qgis.PyQt.QtGui'] = pyqt_mock.QtGui
sys.modules['qgis.PyQt.QtWidgets'] = pyqt_mock.QtWidgets
sys.modules['qgis.utils'] = qgis_mock.utils

qgis_mock.core.Qgis = MagicMock()
qgis_mock.core.Qgis.Info = 0
qgis_mock.core.Qgis.Warning = 1
qgis_mock.core.Qgis.Critical = 2
qgis_mock.core.Qgis.Success = 3

qgis_mock.core.QgsProject = MagicMock()
qgis_mock.core.QgsApplication = MagicMock()
qgis_mock.core.QgsTask = MagicMock()

# ----------------------------------------------------------------------
# 2. Añadir la raíz del proyecto al path
# ----------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ----------------------------------------------------------------------
# 3. Fixtures comunes
# ----------------------------------------------------------------------
import pytest
import numpy as np
import tempfile
import shutil

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def sample_mdt():
    return np.random.rand(100, 100).astype(np.float32)

@pytest.fixture
def sample_stack():
    return np.random.rand(5, 64, 64).astype(np.float32)

@pytest.fixture(autouse=True)
def mock_heavy_dependencies():
    with patch.dict('sys.modules', {
        'torch': MagicMock(),
        'laspy': MagicMock(),
        'rasterio': MagicMock(),
        'osgeo': MagicMock(),
        'pdal': MagicMock(),
        'scipy': MagicMock(),
        'skimage': MagicMock(),
        'sklearn': MagicMock(),
        'psutil': MagicMock()
    }):
        with patch('arqueo_cid.config') as mock_cfg:
            mock_cfg.CARPETA_MDT = '01_MDT'
            mock_cfg.CARPETA_DERIVADOS = '02_DERIVADOS'
            mock_cfg.CARPETA_IMAGENES = '03_PNG'
            mock_cfg.CARPETA_STACKS = '04_IA_STACKS'
            mock_cfg.DERIVADOS_COMPATIBLES_BLOQUES = ['hillshade', 'slope', 'tpi', 'lrm']
            yield