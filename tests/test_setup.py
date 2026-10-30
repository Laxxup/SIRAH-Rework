from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from sirah.setup_wizard import (
    SetupError,
    _is_groq,
    _serial_candidates,
    download_voice,
    ensure_settings_file,
    run_setup,
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, size: int):
        yield self.payload


class _FakeClient:
    payload = b""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def stream(self, method: str, url: str):
        payload = type(self).payload

        class _Stream:
            def __enter__(self):
                return _FakeResponse(payload)

            def __exit__(self, *args: object) -> bool:
                return False

        return _Stream()


def _port(device: str, description: str | None, vid: int | None = None, pid: int | None = None):
    return SimpleNamespace(device=device, description=description, vid=vid, pid=pid)


def test_serial_candidates_skip_fake_ttyS() -> None:
    ports = [
        _port("/dev/ttyS0", "n/a"),
        _port("/dev/ttyS1", "n/a"),
    ]
    assert _serial_candidates(ports, {}) == []


def test_serial_candidates_prefer_by_id() -> None:
    real = str(Path("/dev/ttyUSB0").resolve())
    ports = [_port("/dev/ttyUSB0", "USB Serial", vid=0x1A86, pid=0x7523)]
    found = _serial_candidates(ports, {real: "/dev/serial/by-id/usb-test"})
    assert found == [("/dev/serial/by-id/usb-test", "USB Serial [1a86:7523]")]


def test_serial_candidates_keep_named_port() -> None:
    ports = [_port("/dev/ttyACM0", "Arduino", vid=0x2341, pid=0x0043)]
    assert _serial_candidates(ports, {}) == [("/dev/ttyACM0", "Arduino [2341:0043]")]


def test_ensure_settings_copies_only_the_example(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    example = config_dir / "sirah.toml.example"
    example.write_text('[persona]\nidentity = "robot"\n', encoding="utf-8")

    target = ensure_settings_file(tmp_path)
    assert target == config_dir / "sirah.toml"
    assert target.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    target.write_text("personalizado", encoding="utf-8")
    assert ensure_settings_file(tmp_path) is None
    assert target.read_text(encoding="utf-8") == "personalizado"


def test_ensure_settings_without_example_does_nothing(tmp_path: Path) -> None:
    assert ensure_settings_file(tmp_path) is None
    assert not (tmp_path / "config" / "sirah.toml").exists()


def _patch_setup(monkeypatch, tmp_path, env_content="", ask_overrides=None):
    env_file = tmp_path / ".env"
    if env_content:
        env_file.write_text(env_content, encoding="utf-8")

    monkeypatch.setattr("sirah.setup_wizard.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("sirah.setup_wizard.os.environ", {})
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        "sirah.setup_wizard.update_env_file",
        lambda path, updates: captured.update(updates),
    )
    monkeypatch.setattr("sirah.setup_wizard.detect_serial_ports", lambda: [])
    monkeypatch.setattr("sirah.setup_wizard.detect_cameras", lambda: [])
    monkeypatch.setattr("sirah.setup_wizard._choose", lambda *a, **k: None)
    monkeypatch.setattr("sirah.setup_wizard.ensure_settings_file", lambda *a, **k: None)
    monkeypatch.setattr("sirah.setup_wizard.find_piper", lambda: None)

    answers = {
        "cambiarla": False,
        "cambiar el puerto": False,
        "Activar": False,
        "Preparar": False,
    }
    if ask_overrides:
        answers.update(ask_overrides)

    def fake_ask_yes_no(prompt, default=False):
        for key, value in answers.items():
            if key in prompt:
                return value
        return default

    monkeypatch.setattr("sirah.setup_wizard._ask_yes_no", fake_ask_yes_no)

    def fake_secret(prompt):
        if "GROQ" in prompt.upper():
            return ""
        return "sk-test-llm"

    monkeypatch.setattr("sirah.setup_wizard._ask_secret", fake_secret)
    return env_file, captured


def test_is_groq_hostname() -> None:
    assert _is_groq("https://api.groq.com/openai/v1") is True
    assert _is_groq("https://groq.com.evil.example/v1") is False
    assert _is_groq("") is False


def test_setup_does_not_override_base_url_with_opencode(monkeypatch, tmp_path: Path) -> None:
    env_file, captured = _patch_setup(
        monkeypatch,
        tmp_path,
        env_content="LLM_BASE_URL=https://opencode.ai/v1\n",
    )
    rc = run_setup(env_file)
    assert rc == 0
    assert "LLM_BASE_URL" not in captured
    assert "LLM_MODEL" not in captured


def test_setup_clears_eyes_address_when_no_ports_and_changing(monkeypatch, tmp_path: Path) -> None:
    env_file, captured = _patch_setup(
        monkeypatch,
        tmp_path,
        env_content="EYES_ADDRESS=serial:///dev/ttyUSB0\n",
        ask_overrides={"cambiar el puerto": True},
    )
    rc = run_setup(env_file)
    assert rc == 0
    assert captured.get("EYES_ADDRESS") == ""


def test_download_voice_installs_a_verified_file(tmp_path: Path, monkeypatch) -> None:
    payload = b"modelo de voz"
    monkeypatch.setattr(
        "sirah.setup_wizard.VOICE_FILES",
        {"es.onnx": (hashlib.sha256(payload).hexdigest(), len(payload))},
    )
    monkeypatch.setattr("sirah.setup_wizard.httpx.Client", _FakeClient)
    _FakeClient.payload = payload

    download_voice(tmp_path, assume_yes=True)

    assert (tmp_path / "es.onnx").read_bytes() == payload
    assert not (tmp_path / ".es.onnx.part").exists()


def test_download_voice_rejects_a_file_with_the_wrong_hash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "sirah.setup_wizard.VOICE_FILES",
        {"es.onnx": (hashlib.sha256(b"lo esperado").hexdigest(), len(b"lo esperado"))},
    )
    monkeypatch.setattr("sirah.setup_wizard.httpx.Client", _FakeClient)
    _FakeClient.payload = b"otra cosa"

    with pytest.raises(SetupError, match="SHA256"):
        download_voice(tmp_path, assume_yes=True)

    assert not (tmp_path / "es.onnx").exists()
    assert not (tmp_path / ".es.onnx.part").exists()
