from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_architecture_does_not_advertise_a_missing_eyes_command() -> None:
    text = (ROOT / "docs" / "ARQUITECTURA.md").read_text(encoding="utf-8")
    assert "sirah eyes test" not in text
    assert "PENDIENTES.md" in text


def test_readme_mentions_ci_workflow() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert ".github/workflows/check.yml" in text
    assert "No hay CI configurado" not in text


def test_architecture_marks_future_files_and_has_no_vision_flag() -> None:
    text = (ROOT / "docs" / "ARQUITECTURA.md").read_text(encoding="utf-8")
    assert "--vision" not in text
    assert "**Futuro:**" in text
    assert "core/supervisor.py" in text
    assert "bench/" in text
