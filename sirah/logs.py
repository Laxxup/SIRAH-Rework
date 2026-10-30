"""Logging solo a archivo, con rotación."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "sirah"
_MAX_BYTES = 1_000_000
_BACKUPS = 3


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler que crea/abre el log con modo 0600 tras rotar."""

    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        return os.fdopen(fd, self.mode, encoding=self.encoding, errors=self.errors)


def setup_logging(data_dir: Path, level: str = "INFO", debug: bool = False) -> Path:
    """Configura el logger de SIRAH y devuelve la ruta del archivo."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = log_dir / "sirah.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    effective = logging.DEBUG if debug else getattr(logging, level, logging.INFO)
    logger.setLevel(effective)

    file_handler = _PrivateRotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUPS,
        encoding="utf-8",
    )
    file_handler.setLevel(effective)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(file_handler)
    os.chmod(log_path, 0o600)
    return log_path
