"""Captura de cámara y detección YuNet. Único módulo que importa cv2."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from sirah.core.vision import Box, FaceTracker, GazeReceiver

logger = logging.getLogger("sirah.camera")

FRAME_WIDTH = 320
FRAME_HEIGHT = 240


class CameraError(Exception):
    """Fallo de cámara con un mensaje accionable en español."""


def _boxes(faces: Any) -> tuple[Box, ...]:
    """Convierte la salida de YuNet en cajas enteras."""
    if faces is None:
        return ()
    return tuple((int(face[0]), int(face[1]), int(face[2]), int(face[3])) for face in faces)


class CameraVision:
    """Captura en un hilo, detecta la cara más grande y avisa al receptor."""

    def __init__(
        self,
        *,
        camera: str,
        model: Path,
        fps: int,
        tracker: FaceTracker,
        receiver: GazeReceiver,
    ) -> None:
        if fps < 1:
            raise ValueError("fps debe ser >= 1")
        self.camera = camera
        self.model = Path(model)
        self.fps = fps
        self.tracker = tracker
        self.receiver = receiver
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._capture: Any = None
        self._detector: Any = None
        self._cv2: Any = None
        self._last_frame: Any = None
        self._last_boxes: tuple[Box, ...] = ()
        self._error: CameraError | None = None
        self._centered = False

    @property
    def error(self) -> CameraError | None:
        with self._lock:
            return self._error

    @property
    def last_frame(self) -> Any:
        with self._lock:
            return self._last_frame

    @property
    def last_boxes(self) -> tuple[Box, ...]:
        with self._lock:
            return self._last_boxes

    def start(self) -> None:
        """Abre la cámara y arranca el hilo. Lanza CameraError si no puede."""
        if self._thread is not None:
            return
        try:
            import cv2
        except ImportError as exc:
            raise CameraError(
                "Falta OpenCV. Instala el extra de visión con `uv sync --all-extras`."
            ) from exc
        if not self.model.exists():
            raise CameraError(f"No existe el modelo YuNet: {self.model}")

        capture = cv2.VideoCapture(self.camera)
        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"No se pudo abrir la cámara {self.camera}. "
                "Revisa VISION_CAMERA y que no la use otro programa."
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        try:
            detector = cv2.FaceDetectorYN.create(str(self.model), "", (FRAME_WIDTH, FRAME_HEIGHT))
        except Exception as exc:
            capture.release()
            raise CameraError(f"No se pudo cargar YuNet: {exc}") from exc

        self._cv2 = cv2
        self._capture = capture
        self._detector = detector
        self._thread = threading.Thread(target=self._run, name="sirah-vision", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        cv2 = self._cv2
        interval = 1.0 / self.fps
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                ok, frame = self._capture.read()
                if not ok:
                    raise CameraError(
                        f"La cámara {self.camera} dejó de entregar imagen. "
                        "Revisa el cable o VISION_CAMERA."
                    )
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                _, faces = self._detector.detect(frame)
                boxes = _boxes(faces)
                with self._lock:
                    self._last_frame = frame
                    self._last_boxes = boxes

                point = self.tracker.update(boxes, (FRAME_WIDTH, FRAME_HEIGHT))
                if point is None:
                    if not self._centered:
                        self.receiver.center()
                        self._centered = True
                else:
                    self._centered = False
                    self.receiver.look(point.x, point.y)

                elapsed = time.monotonic() - started
                self._stop.wait(max(0.0, interval - elapsed))
        except CameraError as exc:
            with self._lock:
                self._error = exc
            logger.error("Visión detenida: %s", exc)
        except Exception as exc:
            error = CameraError(f"Fallo inesperado de la cámara: {exc}")
            with self._lock:
                self._error = error
            logger.exception("Fallo inesperado de la cámara")
        finally:
            self._capture.release()

    def close(self) -> None:
        """Detiene el hilo y libera la cámara. Se puede llamar dos veces."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            self._thread = None
        capture = self._capture
        if capture is not None:
            capture.release()
            self._capture = None
