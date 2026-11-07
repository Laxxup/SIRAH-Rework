"""Lógica pura de seguimiento de mirada: sin cv2, hardware ni red."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class GazePoint:
    """Punto normalizado: x -1 izquierda/+1 derecha, y -1 abajo/+1 arriba."""

    x: float
    y: float


class GazeReceiver(Protocol):
    """Destino de la mirada. El receptor nulo solo registra."""

    def look(self, x: float, y: float) -> None: ...

    def center(self) -> None: ...


class NullGazeReceiver:
    """Receptor de prueba: registra la mirada sin mover nada."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("sirah.vision")

    def look(self, x: float, y: float) -> None:
        self._logger.debug("Mirada x=%.3f y=%.3f", x, y)

    def center(self) -> None:
        self._logger.debug("Mirada al centro")


def largest_box(boxes: Iterable[Box]) -> Box | None:
    """Devuelve la caja con más área; ignora cajas sin área."""
    best: Box | None = None
    best_area = 0
    for x, y, width, height in boxes:
        if width <= 0 or height <= 0:
            continue
        area = width * height
        if area > best_area:
            best = (x, y, width, height)
            best_area = area
    return best


class FaceTracker:
    """Convierte las cajas de cara en un punto de mirada suavizado."""

    def __init__(
        self,
        *,
        dead_zone: float = 0.15,
        smoothing: float = 0.35,
        lost_frames: int = 15,
    ) -> None:
        if not 0 <= dead_zone <= 1:
            raise ValueError("dead_zone debe estar entre 0 y 1")
        if not 0 < smoothing <= 1:
            raise ValueError("smoothing debe estar entre 0 y 1")
        if lost_frames < 1:
            raise ValueError("lost_frames debe ser >= 1")
        self.dead_zone = dead_zone
        self.smoothing = smoothing
        self.lost_frames = lost_frames
        self._x = 0.0
        self._y = 0.0
        self._missing = 0

    @property
    def point(self) -> GazePoint:
        return GazePoint(self._x, self._y)

    def update(self, boxes: Iterable[Box], frame_size: tuple[int, int]) -> GazePoint | None:
        """Actualiza la mirada. `None` significa que toca volver al centro."""
        width, height = frame_size
        if width <= 0 or height <= 0:
            raise ValueError("frame_size debe ser positivo")

        box = largest_box(boxes)
        if box is None:
            self._missing += 1
            if self._missing >= self.lost_frames:
                self._x = 0.0
                self._y = 0.0
                return None
            return self.point

        self._missing = 0
        x, y, box_width, box_height = box
        center_x = x + box_width / 2
        center_y = y + box_height / 2

        target_x = (center_x / width) * 2 - 1
        target_y = 1 - (center_y / height) * 2
        target_x = 0.0 if abs(target_x) < self.dead_zone else max(-1.0, min(1.0, target_x))
        target_y = 0.0 if abs(target_y) < self.dead_zone else max(-1.0, min(1.0, target_y))

        self._x += (target_x - self._x) * self.smoothing
        self._y += (target_y - self._y) * self.smoothing
        return self.point
