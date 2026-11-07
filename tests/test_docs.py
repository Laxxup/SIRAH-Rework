from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_architecture_does_not_advertise_a_missing_eyes_command() -> None:
    text = (ROOT / "docs" / "ARQUITECTURA.md").read_text(encoding="utf-8")
    assert "sirah eyes test" not in text
    assert "PENDIENTES.md" in text
