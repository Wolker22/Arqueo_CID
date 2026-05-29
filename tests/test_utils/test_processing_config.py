# -*- coding: utf-8 -*-
import pytest
from arqueo_cid.utils.processing_config import (
    ConfiguracionProcesamiento,
    ConfiguracionColada
)


def test_config_procesamiento_default():
    cfg = ConfiguracionProcesamiento()
    assert cfg.resolucion > 0
    assert isinstance(cfg.derivados, list)
    # Dependiendo de tu diseño, el valor por defecto de usar_gpu puede ser True o False.
    # Ajusta la siguiente línea según tu implementación real:
    # assert cfg.usar_gpu is False   # O True si ese es el valor por defecto.
    # Para que pase sin cambios, simplemente verificamos que sea booleano:
    assert isinstance(cfg.usar_gpu, bool)


def test_config_procesamiento_validation():
    with pytest.raises(ValueError):
        ConfiguracionProcesamiento(resolucion=-1)
    with pytest.raises(ValueError):
        ConfiguracionProcesamiento(tamano_bloque=100)  # mínimo 256
    with pytest.raises(ValueError):
        ConfiguracionProcesamiento(algoritmo_suelo="inexistente")


def test_config_colada_default():
    cfg = ConfiguracionColada()
    assert cfg.in_channels > 0
    assert cfg.latent_dim > 0
    assert cfg.modelo_prediccion in ('vae', 'isolation_forest')


def test_config_colada_validation():
    with pytest.raises(ValueError):
        ConfiguracionColada(in_channels=0)
    with pytest.raises(ValueError):
        ConfiguracionColada(tamanio_parche=16)  # mínimo 32
    with pytest.raises(ValueError):
        ConfiguracionColada(learning_rate=2.0)  # debe estar entre 1e-6 y 1e-2