from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "firmware" / "sirah" / "calibration.h"
TOML = ROOT / "config" / "eyes-calibration.toml"

_DEFINE = re.compile(r"^#define\s+(\w+)\s+(\d+)\s*$", re.MULTILINE)


def _from_toml() -> dict[str, int]:
    data = tomllib.loads(TOML.read_text(encoding="utf-8"))
    expected = {
        "EYES_PWM_HZ": data["pwm"]["frequency_hz"],
        "EYES_PULSE_0_US": data["pwm"]["pulse_0_us"],
        "EYES_PULSE_180_US": data["pwm"]["pulse_180_us"],
    }
    for name, channel in data["channels"].items():
        expected[f"CH_{name}"] = channel
    for name, poses in data["servo"].items():
        for pose, angle in poses.items():
            expected[f"{name}_{pose.upper()}"] = angle
    for name, angle in data["boot"].items():
        expected[f"BOOT_{name}"] = angle
    return expected


def test_calibration_header_matches_the_toml() -> None:
    """El .h que compila el ESP32 no puede separarse del TOML canónico."""
    defines = {
        name: int(value) for name, value in _DEFINE.findall(HEADER.read_text(encoding="utf-8"))
    }
    assert defines == _from_toml()
