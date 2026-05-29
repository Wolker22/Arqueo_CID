# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch


# Estos tests requieren mockear QgsTask de QGIS y la lógica asíncrona.
# Por ahora se omiten para mantener la suite estable.
@pytest.mark.skip(reason="Requiere mock complejo de QgsTask; se pospone para futura mejora")
def test_pipeline_solo_procesamiento():
    pass


@pytest.mark.skip(reason="Requiere mock complejo de QgsTask; se pospone para futura mejora")
def test_pipeline_solo_descarga():
    pass


@pytest.mark.skip(reason="Requiere mock complejo de QgsTask; se pospone para futura mejora")
def test_pipeline_cancelacion():
    pass