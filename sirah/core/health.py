"""Estado de salud de una capa, compartido por adaptadores y doctor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "warn", "fail", "off"]


@dataclass(frozen=True, slots=True)
class Health:
    """Resultado de una comprobación, con su solución si algo falla."""

    name: str
    status: Status
    detail: str
    fix: str | None = None
