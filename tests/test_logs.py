from __future__ import annotations

import logging
import os
from pathlib import Path

from sirah.logs import LOGGER_NAME, setup_logging


def test_setup_logging_writes_file_and_replaces_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    try:
        log_path = setup_logging(tmp_path)
        logger.info("hola desde el test")
        for handler in logger.handlers:
            handler.flush()
        assert log_path.exists()
        assert "hola desde el test" in log_path.read_text(encoding="utf-8")
        assert os.stat(log_path).st_mode & 0o777 == 0o600

        setup_logging(tmp_path, debug=True)
        assert len(logger.handlers) == 1
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_rotated_log_and_new_active_file_stay_private(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sirah.logs._MAX_BYTES", 200)
    logger = logging.getLogger(LOGGER_NAME)
    try:
        log_path = setup_logging(tmp_path)
        for _ in range(20):
            logger.info("mensaje de relleno para forzar la rotación")
        for handler in logger.handlers:
            handler.flush()

        files = [log_path, *log_path.parent.glob("sirah.log.*")]
        assert len(files) > 1
        for path in files:
            assert os.stat(path).st_mode & 0o777 == 0o600, path
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_warnings_do_not_reach_the_terminal(tmp_path: Path, capsys) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    try:
        setup_logging(tmp_path)
        logger.warning("esto solo debe ir al archivo")
        for handler in logger.handlers:
            handler.flush()
        assert "esto solo debe ir al archivo" not in capsys.readouterr().err
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
