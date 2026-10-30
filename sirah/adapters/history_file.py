"""Persistencia del historial en JSONL, con permisos y tamaño acotados."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from sirah.core.memory import Message, Role

logger = logging.getLogger("sirah.history")

MAX_LINES = 200
MAX_BYTES = 256_000
MAX_TEXT_CHARS = 4000
_COMPACT_LINES = 50
_KEEP_LINES = 150


def history_path(data_dir: Path, persona_path: Path) -> Path:
    """Un archivo por persona; el nombre se sanea para no salir del directorio."""
    stem = persona_path.stem.removesuffix(".persona")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip(".") or "persona"
    return data_dir / "history" / f"{safe}.jsonl"


def migrate_default_history(data_dir: Path) -> Path | None:
    """Renombra el historial de la tarjeta antigua, dejando una copia de respaldo."""
    history_dir = data_dir / "history"
    source = history_dir / "default.jsonl"
    target = history_dir / "sirah.jsonl"
    if not source.exists() or target.exists():
        return None
    backup = history_dir / "sirah.jsonl.bak"
    try:
        shutil.copy2(source, backup)
        os.chmod(backup, 0o600)
        os.replace(source, target)
        os.chmod(target, 0o600)
    except OSError as exc:
        logger.warning("No se pudo migrar el historial %s: %s", source, exc.strerror)
        return None
    logger.info("Historial migrado de %s a %s (respaldo en %s)", source, target, backup)
    return target


class HistoryFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, limit: int) -> list[Message]:
        if limit <= 0 or not self.path.exists():
            return []
        messages: deque[Message] = deque(maxlen=limit)
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line in handle:
                    parsed = self._parse(line)
                    if parsed is not None:
                        messages.append(parsed)
        except OSError as exc:
            logger.warning("No se pudo leer el historial %s: %s", self.path, exc.strerror)
            return []
        return list(messages)

    def append(self, role: Role, text: str) -> None:
        if not text.strip():
            return
        text = text[:MAX_TEXT_CHARS] + ("…" if len(text) > MAX_TEXT_CHARS else "")
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "role": role,
            "text": text,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.path.parent, 0o700)
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            os.chmod(self.path, 0o600)
            self._compact_if_needed()
        except OSError as exc:
            logger.warning("No se pudo guardar el historial %s: %s", self.path, exc.strerror)

    def _compact_if_needed(self) -> None:
        size = self.path.stat().st_size
        with self.path.open(encoding="utf-8") as handle:
            lines = [line.rstrip("\n") for line in handle]
        if len(lines) <= MAX_LINES and size <= MAX_BYTES:
            return
        keep = _COMPACT_LINES if size > MAX_BYTES else _KEEP_LINES
        self._write_atomic(lines[-keep:])

    def _write_atomic(self, lines: list[str]) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temporary, self.path)

    @staticmethod
    def _parse(line: str) -> Message | None:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Línea de historial inválida descartada")
            return None
        if not isinstance(data, dict):
            return None
        role = data.get("role")
        text = data.get("text")
        if role not in {"user", "assistant"} or not isinstance(text, str) or not text.strip():
            logger.debug("Entrada de historial incompleta descartada")
            return None
        return Message(role, text)
