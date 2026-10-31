"""Etiquetas de acción del LLM: parseo y validación."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("sirah.actions")

_TAG = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_EYELID = {"blink", "tired"}
_MAX_ACTIONS = 2
_ACTION_NAMES = ("look", "blink", "tired", "center")


def _is_truncated_action(buffer: str) -> bool:
    """Indica si el tail pendiente parece una etiqueta de acción cortada."""
    if buffer.startswith("{{"):
        content = buffer[2:]
    elif buffer.startswith("{"):
        content = buffer[1:]
    else:
        return False
    content = content.lstrip()
    return any(word.startswith(content) or content.startswith(word) for word in _ACTION_NAMES)


@dataclass(frozen=True, slots=True)
class Action:
    name: Literal["look", "blink", "tired", "center"]
    x: float | None = None
    y: float | None = None


class ActionParser:
    """Separa texto visible de etiquetas, incluso si llegan partidas."""

    def __init__(self) -> None:
        self._buffer = ""
        self._actions: list[Action] = []

    @property
    def actions(self) -> tuple[Action, ...]:
        return tuple(self._actions)

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        parts: list[str] = []
        position = 0
        for match in _TAG.finditer(self._buffer):
            parts.append(self._buffer[position : match.start()])
            self._handle(match.group(1))
            position = match.end()
        parts.append(self._buffer[position:])

        text = "".join(parts)
        pending = text.rfind("{{")
        if pending >= 0:
            self._buffer = text[pending:]
            return text[:pending]
        if text.endswith("{"):
            self._buffer = "{"
            return text[:-1]
        self._buffer = ""
        return text

    def finish(self) -> str:
        """Devuelve el texto pendiente salvo si parecía una etiqueta cortada."""
        buffer = self._buffer
        self._buffer = ""
        if _is_truncated_action(buffer):
            return ""
        return buffer

    def _handle(self, content: str) -> None:
        parts = content.split()
        if not parts:
            logger.debug("Etiqueta de acción vacía descartada")
            return

        name = parts[0]
        if name == "look" and len(parts) == 3:
            try:
                x, y = float(parts[1]), float(parts[2])
            except ValueError:
                logger.debug("Coordenadas de mirada no numéricas descartadas")
                return
            if not (-1 <= x <= 1 and -1 <= y <= 1):
                logger.debug("Coordenadas de mirada fuera de rango descartadas")
                return
            self._add(Action("look", x, y))
            return

        if name in {"blink", "tired", "center"} and len(parts) == 1:
            self._add(Action(name))
            return

        logger.debug("Etiqueta de acción desconocida o mal formada descartada")

    def _add(self, action: Action) -> None:
        if len(self._actions) >= _MAX_ACTIONS:
            logger.debug("Límite de dos acciones por respuesta alcanzado")
            return
        if action.name in _EYELID and any(item.name in _EYELID for item in self._actions):
            logger.debug("Solo se admite una acción de párpados por respuesta")
            return
        self._actions.append(action)
