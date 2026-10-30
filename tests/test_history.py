from __future__ import annotations

import json
import stat
from pathlib import Path

from sirah.adapters.history_file import (
    _KEEP_LINES,
    MAX_BYTES,
    MAX_LINES,
    HistoryFile,
    history_path,
    migrate_default_history,
)
from sirah.core.memory import Message


def test_history_path_uses_persona_name(tmp_path: Path) -> None:
    assert history_path(tmp_path, Path("/x/sirah.json")) == (tmp_path / "history" / "sirah.jsonl")
    assert history_path(tmp_path, Path("/x/default.persona.json")) == (
        tmp_path / "history" / "default.jsonl"
    )
    assert history_path(tmp_path, Path("/x/mi persona!.json")).name == "mi_persona_.jsonl"


def test_default_history_is_migrated_with_a_backup(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    source = history_dir / "default.jsonl"
    source.write_text('{"role":"user","text":"hola"}\n', encoding="utf-8")
    source.chmod(0o600)

    target = migrate_default_history(tmp_path)
    expected = history_dir / "sirah.jsonl"
    assert target == expected
    assert not source.exists()
    assert expected.read_text(encoding="utf-8") == '{"role":"user","text":"hola"}\n'
    assert (history_dir / "sirah.jsonl.bak").read_text(encoding="utf-8") == (
        '{"role":"user","text":"hola"}\n'
    )
    assert stat.S_IMODE(expected.stat().st_mode) == 0o600

    assert migrate_default_history(tmp_path) is None
    assert expected.read_text(encoding="utf-8") == '{"role":"user","text":"hola"}\n'


def test_migration_without_old_history_does_nothing(tmp_path: Path) -> None:
    assert migrate_default_history(tmp_path) is None


def test_round_trip_and_permissions(tmp_path: Path) -> None:
    history = HistoryFile(tmp_path / "history" / "default.jsonl")
    assert history.load(10) == []

    history.append("user", "hola")
    history.append("assistant", "buenas")

    assert history.load(10) == [
        Message("user", "hola"),
        Message("assistant", "buenas"),
    ]
    assert stat.S_IMODE(history.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(history.path.parent.stat().st_mode) == 0o700


def test_jsonl_format_and_limit(tmp_path: Path) -> None:
    history = HistoryFile(tmp_path / "default.jsonl")
    for number in range(5):
        history.append("user", f"mensaje {number}")

    assert history.load(2) == [
        Message("user", "mensaje 3"),
        Message("user", "mensaje 4"),
    ]
    first = json.loads(history.path.read_text(encoding="utf-8").splitlines()[0])
    assert set(first) == {"ts", "role", "text"}
    assert first["role"] == "user"


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "default.jsonl"
    path.write_text(
        '{"role": "user", "text": "válido"}\n'
        "no es json\n"
        '{"role": "system", "text": "no permitido"}\n'
        '{"role": "assistant", "text": 3}\n',
        encoding="utf-8",
    )
    assert HistoryFile(path).load(10) == [Message("user", "válido")]


def test_line_and_size_limits(tmp_path: Path) -> None:
    history = HistoryFile(tmp_path / "default.jsonl")
    for number in range(MAX_LINES + 1):
        history.append("user", f"mensaje {number}")

    lines = history.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == _KEEP_LINES
    assert "mensaje 51" in lines[0]

    for _ in range(100):
        history.append("user", "x" * 5000)

    assert history.path.stat().st_size <= MAX_BYTES
    assert len(history.path.read_text(encoding="utf-8").splitlines()) <= MAX_LINES


def test_compact_hysteresis_does_not_rewrite_until_201(tmp_path: Path, monkeypatch) -> None:
    history = HistoryFile(tmp_path / "default.jsonl")
    for number in range(MAX_LINES + 1):
        history.append("user", f"mensaje {number}")
    assert len(history.path.read_text(encoding="utf-8").splitlines()) == _KEEP_LINES

    writes = {"n": 0}
    original = HistoryFile._write_atomic

    def wrapped(self, lines: list[str]) -> None:
        writes["n"] += 1
        original(self, lines)

    monkeypatch.setattr(HistoryFile, "_write_atomic", wrapped)

    for _ in range(MAX_LINES - _KEEP_LINES):
        history.append("user", "extra")

    assert writes["n"] == 0
    assert len(history.path.read_text(encoding="utf-8").splitlines()) == MAX_LINES

    history.append("user", "disparador")
    assert writes["n"] == 1
    assert len(history.path.read_text(encoding="utf-8").splitlines()) == _KEEP_LINES


def test_compact_no_rewrite_at_160_lines(tmp_path: Path) -> None:
    path = tmp_path / "default.jsonl"
    path.write_text("".join(f'{{"role":"user","text":"m{i}"}}\n' for i in range(160)))
    history = HistoryFile(path)
    before = path.stat().st_ino
    history.append("user", "otro")
    assert path.stat().st_ino == before


def test_long_messages_are_truncated(tmp_path: Path) -> None:
    history = HistoryFile(tmp_path / "default.jsonl")
    history.append("user", "x" * 5000)
    assert history.load(1)[0].content.endswith("…")
    assert len(history.load(1)[0].content) == 4001
