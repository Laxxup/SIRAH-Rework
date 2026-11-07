from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from sirah.adapters.camera import CameraError, CameraVision, _boxes
from sirah.core.vision import FaceTracker


class RecordingReceiver:
    def __init__(self) -> None:
        self.points: list[tuple[float, float]] = []
        self.centers = 0
        self.seen = threading.Event()

    def look(self, x: float, y: float) -> None:
        self.points.append((x, y))
        self.seen.set()

    def center(self) -> None:
        self.centers += 1
        self.seen.set()


class FakeCapture:
    def __init__(self, camera: str) -> None:
        self.camera = camera
        self.released = False

    def isOpened(self) -> bool:
        return True

    def set(self, prop: int, value: int) -> bool:
        return True

    def read(self):
        return True, "frame"

    def release(self) -> None:
        self.released = True


class FakeDetector:
    def detect(self, frame):
        return 1, [[100.0, 50.0, 80.0, 80.0, 0.0]]


class FakeCV2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4

    VideoCapture = FakeCapture

    class FaceDetectorYN:
        @staticmethod
        def create(*args, **kwargs) -> FakeDetector:
            return FakeDetector()

    @staticmethod
    def resize(frame, size):
        return frame


def test_boxes_parses_yunet_rows() -> None:
    assert _boxes(None) == ()
    assert _boxes([[1.2, 2.8, 3.1, 4.9, 0.0]]) == ((1, 2, 3, 4),)


def test_camera_without_cv2_raises_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "cv2", None)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"modelo")
    vision = CameraVision(
        camera="/dev/video0",
        model=model,
        fps=8,
        tracker=FaceTracker(),
        receiver=RecordingReceiver(),
    )
    with pytest.raises(CameraError, match="OpenCV"):
        vision.start()


def test_camera_without_model_raises_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "cv2", FakeCV2())
    vision = CameraVision(
        camera="/dev/video0",
        model=tmp_path / "missing.onnx",
        fps=8,
        tracker=FaceTracker(),
        receiver=RecordingReceiver(),
    )
    with pytest.raises(CameraError, match="YuNet"):
        vision.start()


def test_camera_thread_calls_receiver(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "cv2", FakeCV2())
    model = tmp_path / "model.onnx"
    model.write_bytes(b"modelo")
    receiver = RecordingReceiver()
    vision = CameraVision(
        camera="/dev/video0",
        model=model,
        fps=10,
        tracker=FaceTracker(smoothing=1.0),
        receiver=receiver,
    )

    vision.start()
    try:
        assert receiver.seen.wait(2.0)
    finally:
        vision.close()

    assert vision.error is None
    assert receiver.points
    assert vision.last_boxes == ((100, 50, 80, 80),)


class _FaceThenNothingDetector:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        if self.calls == 1:
            return 1, [[100.0, 50.0, 80.0, 80.0, 0.0]]
        return 1, None


class _CenteringCV2(FakeCV2):
    class FaceDetectorYN:
        @staticmethod
        def create(*args, **kwargs) -> _FaceThenNothingDetector:
            return _FaceThenNothingDetector()


def test_camera_centers_once_after_losing_the_face(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "cv2", _CenteringCV2())
    model = tmp_path / "model.onnx"
    model.write_bytes(b"modelo")
    receiver = RecordingReceiver()
    vision = CameraVision(
        camera="/dev/video0",
        model=model,
        fps=10,
        tracker=FaceTracker(smoothing=1.0, lost_frames=2),
        receiver=receiver,
    )

    vision.start()
    try:
        deadline = time.monotonic() + 2.0
        while receiver.centers == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
    finally:
        vision.close()

    assert receiver.points
    assert receiver.centers == 1
