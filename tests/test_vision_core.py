from __future__ import annotations

import pytest

from sirah.core.vision import FaceTracker, GazePoint, NullGazeReceiver, largest_box


def test_center_box_gives_center() -> None:
    tracker = FaceTracker(smoothing=1.0)
    assert tracker.update([(120, 80, 80, 80)], (320, 240)) == GazePoint(0.0, 0.0)


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ((240, 80, 80, 80), GazePoint(0.75, 0.0)),
        ((0, 80, 80, 80), GazePoint(-0.75, 0.0)),
        ((120, 0, 80, 80), GazePoint(0.0, 0.6666666666666667)),
        ((120, 160, 80, 80), GazePoint(0.0, -0.6666666666666667)),
    ],
)
def test_box_direction(box, expected: GazePoint) -> None:
    tracker = FaceTracker(smoothing=1.0)
    point = tracker.update([box], (320, 240))
    assert point is not None
    assert point.x == pytest.approx(expected.x)
    assert point.y == pytest.approx(expected.y)


def test_dead_zone_snaps_to_center() -> None:
    tracker = FaceTracker(dead_zone=0.1, smoothing=1.0)
    assert tracker.update([(160, 110, 20, 20)], (320, 240)) == GazePoint(0.0, 0.0)


def test_smoothing_moves_gradually() -> None:
    tracker = FaceTracker(smoothing=0.5)
    first = tracker.update([(240, 80, 80, 80)], (320, 240))
    second = tracker.update([(240, 80, 80, 80)], (320, 240))
    assert first is not None and second is not None
    assert first.x == pytest.approx(0.375)
    assert second.x == pytest.approx(0.5625)


def test_lost_frames_return_center_after_n_frames() -> None:
    tracker = FaceTracker(smoothing=1.0, lost_frames=3)
    tracker.update([(240, 80, 80, 80)], (320, 240))

    assert tracker.update([], (320, 240)) is not None
    assert tracker.update([], (320, 240)) is not None
    assert tracker.update([], (320, 240)) is None
    assert tracker.point == GazePoint(0.0, 0.0)


def test_largest_box_wins_and_zero_area_is_ignored() -> None:
    assert largest_box([(0, 0, 10, 10), (100, 50, 80, 80)]) == (100, 50, 80, 80)
    assert largest_box([(0, 0, 0, 10), (1, 1, 5, 5)]) == (1, 1, 5, 5)
    assert largest_box([]) is None


def test_coordinates_are_clamped() -> None:
    tracker = FaceTracker(smoothing=1.0)
    point = tracker.update([(300, 0, 100, 100)], (320, 240))
    assert point is not None
    assert point.x == 1.0
    assert point.y == pytest.approx(0.5833333333333333)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dead_zone": 1.5}, "dead_zone"),
        ({"smoothing": 0}, "smoothing"),
        ({"lost_frames": 0}, "lost_frames"),
    ],
)
def test_invalid_tracker_arguments(kwargs, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        FaceTracker(**kwargs)


def test_invalid_frame_size_raises() -> None:
    with pytest.raises(ValueError, match="frame_size"):
        FaceTracker().update([], (0, 240))


def test_null_receiver_logs(caplog) -> None:
    receiver = NullGazeReceiver()
    with caplog.at_level("DEBUG", logger="sirah.vision"):
        receiver.look(0.5, -0.5)
        receiver.center()
    assert "0.500" in caplog.text
    assert "centro" in caplog.text
