# -*- coding: utf-8 -*-
"""
Configuración centralizada de logging para Arqueo-CID
=====================================================

Define únicamente tres loggers: 'ArqueoCid', 'Tizona' y 'Colada'.
Cualquier petición de logger a través de `get_logger()` se redirige
a uno de estos tres según un mapeo inteligente.

Salidas:
- Archivo rotativo por módulo (cada logger escribe en su propio archivo).
- Consola (stderr) con niveles configurables.
- Panel de mensajes de QGIS (QgsMessageLog) con niveles mapeados.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any

from qgis.core import QgsMessageLog, Qgis

from ..config import LOG_DIR, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_FORMATO, LOG_FORMATO_FECHA, LOGGING_MODULE_CONFIG

# ----------------------------------------------------------------------
# Configuración de los tres loggers principales
# ----------------------------------------------------------------------

_LOGGER_CONFIGS = {
    'ArqueoCid': {
        'log_file': 'arqueocid.log',
        'console_level': logging.INFO,
        'qgis_level': logging.INFO,
    },
    'Tizona': {
        'log_file': 'tizona.log',
        'console_level': logging.WARNING,
        'qgis_level': logging.INFO,
    },
    'Colada': {
        'log_file': 'colada.log',
        'console_level': logging.WARNING,
        'qgis_level': logging.INFO,
    },
}

_loggers: Dict[str, logging.Logger] = {}

LOG_PATH = Path(LOG_DIR).resolve()
LOG_PATH.mkdir(parents=True, exist_ok=True)

FORMATTER = logging.Formatter(LOG_FORMATO, datefmt=LOG_FORMATO_FECHA)


def _setup_logger(name: str) -> logging.Logger:
    """
    Configura un logger principal (ArqueoCid, Tizona o Colada).

    Args:
        name: Nombre exacto del logger (debe estar en _LOGGER_CONFIGS).

    Returns:
        Logger configurado.
    """
    config = _LOGGER_CONFIGS[name]
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # Nivel más bajo, los handlers filtran después

    # 1. Handler a archivo rotativo
    try:
        fh = logging.handlers.RotatingFileHandler(
            filename=LOG_PATH / config['log_file'],
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(FORMATTER)
        logger.addHandler(fh)
    except OSError as e:
        print(f"ArqueoCid: No se pudo crear archivo de log para {name}: {e}")

    # 2. Handler a consola
    ch = logging.StreamHandler()
    ch.setLevel(config['console_level'])
    ch.setFormatter(FORMATTER)
    logger.addHandler(ch)

    # 3. Handler al panel de mensajes de QGIS
    class QgsLogHandler(logging.Handler):
        _LEVEL_MAP = {
            logging.DEBUG: Qgis.Info,
            logging.INFO: Qgis.Info,
            logging.WARNING: Qgis.Warning,
            logging.ERROR: Qgis.Critical,
            logging.CRITICAL: Qgis.Critical,
        }

        def emit(self, record: logging.LogRecord) -> None:
            try:
                msg = self.format(record)
                level = self._LEVEL_MAP.get(record.levelno, Qgis.Info)
                QgsMessageLog.logMessage(msg, name, level)
            except Exception:
                self.handleError(record)

    qh = QgsLogHandler()
    qh.setLevel(config['qgis_level'])
    qh.setFormatter(FORMATTER)
    logger.addHandler(qh)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Devuelve uno de los tres loggers principales (ArqueoCid, Tizona, Colada).

    El mapeo es el siguiente:
    - Si name es None o empieza por 'ArqueoCid' (insensible a mayúsculas) → 'ArqueoCid'
    - Si name empieza por 'tizona' (insensible) → 'Tizona'
    - Si name empieza por 'colada' (insensible) → 'Colada'
    - En cualquier otro caso, se asigna a 'ArqueoCid' (logger por defecto).

    Args:
        name: Nombre solicitado (puede ser __name__, 'Tizona', 'colada.main', etc.)

    Returns:
        Instancia del logger correspondiente.
    """
    if name is None:
        name = 'ArqueoCid'

    name_lower = name.lower()
    if name_lower.startswith('tizona'):
        target = 'Tizona'
    elif name_lower.startswith('colada'):
        target = 'Colada'
    else:
        target = 'ArqueoCid'

    if target not in _loggers:
        _loggers[target] = _setup_logger(target)
    return _loggers[target]


def set_global_log_level(level: int) -> None:
    """
    Ajusta el nivel de logging para todos los handlers de consola y QGIS,
    pero mantiene los archivos de log en DEBUG.

    Args:
        level: Nivel de logging (logging.DEBUG, logging.INFO, etc.)
    """
    for logger in _loggers.values():
        for handler in logger.handlers:
            if isinstance(handler, (logging.StreamHandler, QgsLogHandler)):
                handler.setLevel(level)
    # También actualizar la configuración por si se crean nuevos loggers
    for cfg in _LOGGER_CONFIGS.values():
        cfg['console_level'] = level
        cfg['qgis_level'] = level