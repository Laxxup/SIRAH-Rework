from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sirah.cli import main
from sirah.logs import LOGGER_NAME


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "SIRAH" in capsys.readouterr().out


def test_setup_needs_terminal(capsys) -> None:
    assert main(["setup"]) == 1
    assert "terminal interactiva" in capsys.readouterr().out


def test_doctor_without_key(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("EYES_ADDRESS", raising=False)
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert main(["doctor", "--offline"]) == 1
    output = capsys.readouterr().out
    assert "SIRAH doctor" in output
    assert "LLM_API_KEY" in output


def test_run_without_key(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("EYES_ADDRESS", raising=False)
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert main([]) == 1
    output = capsys.readouterr().out
    assert "LLM_API_KEY" in output
    assert "sirah setup" in output


def _card(path: Path, name: str = "Nova") -> Path:
    path.write_text(
        '{"spec":"chara_card_v2","data":{"name":"' + name + '","personality":"Directa."}}',
        encoding="utf-8",
    )
    return path


def _quiet_logs():
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_run_starts_text_chat(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(tmp_path / "missing.toml"))
    calls: dict[str, object] = {}

    async def fake_run(config, persona, **kwargs):
        calls["config"] = config
        calls["persona"] = persona
        calls["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("sirah.cli.run_terminal", fake_run)
    try:
        assert main([]) == 0
        assert calls["persona"].display_name == "SIRAH"
        assert calls["kwargs"] == {"identity": "card", "language": "es"}
        assert calls["config"].llm_api_key == "clave-de-prueba"
        assert (tmp_path / "data" / "sirah" / "logs" / "sirah.log").exists()
    finally:
        _quiet_logs()


def test_voice_command_passes_identity(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(tmp_path / "missing.toml"))
    calls: dict[str, object] = {}

    async def fake_voice(config, persona, **kwargs):
        calls["persona"] = persona
        calls["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("sirah.cli.run_voice", fake_voice)
    try:
        assert main(["voice"]) == 0
        assert calls["persona"].display_name == "SIRAH"
        assert calls["kwargs"] == {"identity": "card", "language": "es"}
    finally:
        _quiet_logs()


def test_voice_check_works_without_the_llm_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(tmp_path / "missing.toml"))
    calls: list[object] = []

    async def fake_check(config):
        calls.append(config)
        return 0

    monkeypatch.setattr("sirah.cli.run_check", fake_check)
    try:
        assert main(["voice", "--check"]) == 0
        assert len(calls) == 1
    finally:
        _quiet_logs()


def test_persona_flag_overrides_file(tmp_path: Path, monkeypatch, capsys) -> None:
    persona_path = _card(tmp_path / "otra.json")
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(tmp_path / "missing.toml"))
    calls: dict[str, object] = {}

    async def fake_run(config, persona, **kwargs):
        calls["persona"] = persona
        return 0

    monkeypatch.setattr("sirah.cli.run_terminal", fake_run)
    try:
        assert main(["--persona", str(persona_path)]) == 0
        assert calls["persona"].display_name == "Nova"
        assert calls["persona"].path == persona_path.resolve()
    finally:
        _quiet_logs()


def test_invalid_persona_falls_back_to_sirah(tmp_path: Path, monkeypatch, capsys) -> None:
    persona_path = tmp_path / "rota.json"
    persona_path.write_text("{no es json", encoding="utf-8")
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("SIRAH_PERSONA", str(persona_path))
    calls: dict[str, object] = {}

    async def fake_run(config, persona, **kwargs):
        calls["persona"] = persona
        return 0

    monkeypatch.setattr("sirah.cli.run_terminal", fake_run)
    try:
        assert main([]) == 0
        output = capsys.readouterr().out
        assert "[AVISO]" in output
        assert "Solución:" in output
        assert "Traceback" not in output
        assert output.count(str(persona_path.resolve())) == 1
        assert calls["persona"].display_name == "SIRAH"
    finally:
        _quiet_logs()


def test_identity_override_reaches_the_terminal(tmp_path: Path, monkeypatch, capsys) -> None:
    card = _card(tmp_path / "ana.json", name="Ana")
    settings = tmp_path / "sirah.toml"
    settings.write_text(
        f'[persona]\nactive = "{card}"\nidentity = "robot"\n\n'
        '[persona.cards."ana.json"]\nidentity = "personaje"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SIRAH_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("SIRAH_SETTINGS_FILE", str(settings))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("SIRAH_PERSONA", raising=False)
    calls: dict[str, object] = {}

    async def fake_run(config, persona, **kwargs):
        calls["persona"] = persona
        calls["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("sirah.cli.run_terminal", fake_run)
    try:
        assert main([]) == 0
        assert calls["persona"].display_name == "Ana"
        assert calls["kwargs"]["identity"] == "card"
    finally:
        _quiet_logs()
