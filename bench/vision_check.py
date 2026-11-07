"""Prueba manual de la visión con webcam. No entra en `make check` ni en pytest.

Uso:
    uv sync --all-extras
    uv run python bench/vision_check.py --camera /dev/video0 --seconds 10
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sirah.adapters.camera import CameraError, CameraVision  # noqa: E402
from sirah.config import DEFAULT_VISION_MODEL  # noqa: E402
from sirah.core.vision import FaceTracker  # noqa: E402


class PrintReceiver:
    """Muestra en pantalla solo cuando la mirada cambia de forma visible."""

    def __init__(self) -> None:
        self.last: tuple[float, float] | None = None

    def look(self, x: float, y: float) -> None:
        point = (round(x, 2), round(y, 2))
        if point != self.last:
            print(f"mirada x={x:+.2f} y={y:+.2f}")
            self.last = point

    def center(self) -> None:
        if self.last is not None:
            print("mirada al centro")
            self.last = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba manual de cámara y YuNet.")
    parser.add_argument("--camera", default="/dev/video0")
    parser.add_argument("--model", type=Path, default=DEFAULT_VISION_MODEL)
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--dead-zone", type=float, default=0.15)
    parser.add_argument("--smoothing", type=float, default=0.35)
    parser.add_argument("--seconds", type=float, default=0, help="0 = hasta Ctrl-C")
    args = parser.parse_args()

    tracker = FaceTracker(
        dead_zone=args.dead_zone,
        smoothing=args.smoothing,
        lost_frames=round(args.fps * 1.5),
    )
    vision = CameraVision(
        camera=args.camera,
        model=args.model,
        fps=args.fps,
        tracker=tracker,
        receiver=PrintReceiver(),
    )
    try:
        vision.start()
    except CameraError as exc:
        print(f"[FALLA] {exc}")
        return 1

    print(f"Cámara {args.camera} a {args.fps} FPS. Ctrl-C para salir.")
    started = time.monotonic()
    last_boxes: tuple[tuple[int, int, int, int], ...] = ()
    try:
        while not args.seconds or time.monotonic() - started < args.seconds:
            time.sleep(0.2)
            error = vision.error
            if error is not None:
                print(f"[FALLA] {error}")
                return 1
            boxes = vision.last_boxes
            if boxes != last_boxes:
                print(f"caras: {boxes}")
                last_boxes = boxes
    except KeyboardInterrupt:
        pass
    finally:
        vision.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
