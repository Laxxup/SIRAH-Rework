"""Historial acotado en memoria, sin I/O."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]

MAX_STORED_TEXT_CHARS = 4000


def limit_text(text: str, limit: int = MAX_STORED_TEXT_CHARS) -> str:
    """Recorta el texto para persistencia acotada sin dejar campos parciales."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


class Memory:
    """Ventana de los últimos mensajes que se envían al LLM."""

    def __init__(self, max_messages: int) -> None:
        self._messages: deque[Message] = deque(maxlen=max_messages)

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def add(self, role: Role, content: str) -> None:
        if content.strip():
            self._messages.append(Message(role, content))

    def add_turn(self, user: str, assistant: str) -> None:
        self.add("user", user)
        self.add("assistant", assistant)
