from __future__ import annotations

import os
from pathlib import Path

import pytest

from sirah.config import (
    DEFAULT_PERSONA,
    ConfigError,
    active_card_path,
    identity_for,
    load_config,
    load_persona_settings,
    mask_secret,
    read_env_file,
    update_env_file,
)


def _load(
    tmp_path: Path,
    env_file: Path | None = None,
    settings_file: Path | None = None,
    **env: str,
):
    values = {
        "XDG_DATA_HOME": str(tmp_path / "xdg"),
        "SIRAH_SETTINGS_FILE": str(settings_file or tmp_path / "missing.toml"),
        **env,
    }
    return load_config(env_file=env_file or tmp_path / "missing.env", environ=values)


def _settings(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sirah.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults(tmp_path: Path) -> None:
    config = _load(tmp_path)
    assert config.llm_base_url == "https://api.groq.com/openai/v1"
    assert config.llm_model == "openai/gpt-oss-20b"
    assert config.llm_max_tokens == 1024
    assert config.llm_reasoning_effort == "low"
    assert config.user_name == ""
    assert config.llm_api_key == ""
    assert config.eyes_address == ""
    assert config.eyes_device is None
    assert config.vision_enabled is False
    assert config.memory_messages == 12
    assert config.data_dir == (tmp_path / "xdg" / "sirah").resolve()
    assert config.persona_path == DEFAULT_PERSONA
    assert config.persona_path_set is False
    assert config.persona_settings.language == "es"
    assert config.persona_settings.identity == "card"
    assert config.persona_settings.exists is False


def test_settings_defaults_when_file_is_missing(tmp_path: Path) -> None:
    settings = load_persona_settings(tmp_path / "no.toml")
    assert settings.exists is False
    assert settings.active == DEFAULT_PERSONA
    assert settings.language == "es"
    assert settings.identity == "card"
    assert settings.cards == {}
    assert settings.warnings == ()


def test_settings_read_persona_table(tmp_path: Path) -> None:
    settings = load_persona_settings(
        _settings(
            tmp_path,
            '[persona]\nactive = "config/persona/ana.json"\nlanguage = "en"\n'
            'identity = "personaje"\n\n'
            '[persona.cards."ana.json"]\nidentity = "robot"\n',
        )
    )
    assert settings.exists is True
    assert settings.active.name == "ana.json"
    assert settings.language == "en"
    assert settings.identity == "card"
    assert settings.cards == {"ana.json": "robot"}
    assert settings.warnings == ()


def test_identity_personaje_is_an_alias_of_card(tmp_path: Path) -> None:
    settings = load_persona_settings(_settings(tmp_path, '[persona]\nidentity = "personaje"\n'))
    assert settings.identity == "card"
    assert identity_for(settings, tmp_path / "ana.json") == "card"


def test_identity_for_uses_per_card_identity_override(tmp_path: Path) -> None:
    settings = load_persona_settings(
        _settings(
            tmp_path,
            '[persona]\nidentity = "robot"\n\n[persona.cards."ana.json"]\nidentity = "personaje"\n',
        )
    )
    assert identity_for(settings, tmp_path / "ana.json") == "card"
    assert identity_for(settings, tmp_path / "otra.json") == "robot"


def test_identity_ignores_the_card_contents(tmp_path: Path) -> None:
    card = tmp_path / "ana.json"
    card.write_text('{"spec":"chara_card_v2","data":{"name":"Ana"}}', encoding="utf-8")
    settings = load_persona_settings(tmp_path / "no.toml")
    assert identity_for(settings, card) == "card"


def test_invalid_settings_fall_back_with_warnings(tmp_path: Path) -> None:
    settings = load_persona_settings(
        _settings(
            tmp_path,
            '[persona]\nactive = 3\nlanguage = 5\nidentity = "dios"\ncards = []\n',
        )
    )
    assert settings.active == DEFAULT_PERSONA
    assert settings.language == "es"
    assert settings.identity == "card"
    assert settings.cards == {}
    assert settings.warnings

    broken = load_persona_settings(_settings(tmp_path, "no es toml ["))
    assert broken.identity == "card"
    assert any("No se pudo leer" in warning for warning in broken.warnings)


def test_active_card_uses_sirah_persona_when_set(tmp_path: Path) -> None:
    settings = load_persona_settings(
        _settings(tmp_path, '[persona]\nactive = "config/persona/ana.json"\n')
    )
    default = _load(tmp_path, settings_file=settings.path)
    assert active_card_path(default, settings) == settings.active

    explicit = _load(
        tmp_path,
        settings_file=settings.path,
        SIRAH_PERSONA="config/persona/otra.json",
    )
    assert explicit.persona_path.name == "otra.json"
    assert explicit.persona_path_set is True
    assert active_card_path(explicit, settings) == explicit.persona_path


def test_reasoning_effort_can_be_empty(tmp_path: Path) -> None:
    assert _load(tmp_path, LLM_REASONING_EFFORT="low").llm_reasoning_effort == "low"
    assert _load(tmp_path, LLM_REASONING_EFFORT="").llm_reasoning_effort == ""


def test_user_name_is_optional_data(tmp_path: Path) -> None:
    assert _load(tmp_path, USER_NAME="Luis").user_name == "Luis"
    assert _load(tmp_path, USER_NAME="  ").user_name == ""


def test_env_file_and_process_precedence(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_API_KEY=from-file\nLLM_MODEL=file-model\nLLM_TIMEOUT_S=30\n",
        encoding="utf-8",
    )
    config = load_config(
        env_file=env_file,
        environ={"LLM_API_KEY": "from-process", "XDG_DATA_HOME": str(tmp_path)},
    )
    assert config.llm_api_key == "from-process"
    assert config.llm_model == "file-model"
    assert config.llm_timeout_s == 30


def test_quoted_values_and_comments(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'LLM_MODEL="model with space"\n'
        "LLM_BASE_URL=https://example.com/v1  # comentario\n"
        "LLM_API_KEY='key # literal'\n",
        encoding="utf-8",
    )
    config = load_config(env_file=env_file, environ={"XDG_DATA_HOME": str(tmp_path)})
    assert config.llm_model == "model with space"
    assert config.llm_base_url == "https://example.com/v1"
    assert config.llm_api_key == "key # literal"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("LLM_TIMEOUT_S", "400", "entre 5 y 300"),
        ("LLM_TIMEOUT_S", "abc", "número"),
        ("LLM_MAX_TOKENS", "10", "entre 32 y 4096"),
        ("LLM_TEMPERATURE", "3", "entre 0 y 2"),
        ("LLM_REASONING_EFFORT", "max", "low, medium, high o vacío"),
        ("MEMORY_PERSIST", "maybe", "true o false"),
        ("LOG_LEVEL", "LOUD", "DEBUG"),
        ("VAD_AGGRESSIVENESS", "7", "entre 0 y 3"),
    ],
)
def test_invalid_values(tmp_path: Path, key: str, value: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        _load(tmp_path, **{key: value})


def test_invalid_url(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="URL"):
        _load(tmp_path, LLM_BASE_URL="not-a-url")


def test_eyes_address_parsing(tmp_path: Path) -> None:
    path = "/dev/serial/by-id/usb-test"
    config = _load(tmp_path, EYES_ADDRESS=f"serial://{path}")
    assert config.eyes_device == Path(path)


@pytest.mark.parametrize("address", ["tcp://127.0.0.1:1", "serial://relative", "serial://"])
def test_eyes_address_rejected(tmp_path: Path, address: str) -> None:
    with pytest.raises(ConfigError, match="EYES_ADDRESS"):
        _load(tmp_path, EYES_ADDRESS=address)


def test_panel_requires_token_off_loopback(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="PANEL_TOKEN") as info:
        _load(tmp_path, PANEL_HOST="0.0.0.0", PANEL_TOKEN="tokenReal12345!")
    assert "tokenReal12345!" not in str(info.value)
    config = _load(tmp_path, PANEL_HOST="0.0.0.0", PANEL_TOKEN="x" * 16)
    assert config.panel_token == "x" * 16


def test_vad_prebuffer_must_cover_start_frames(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="VAD_PREBUFFER_MS"):
        _load(tmp_path, VAD_START_FRAMES="10", VAD_PREBUFFER_MS="100")
    config = _load(tmp_path, VAD_START_FRAMES="10", VAD_PREBUFFER_MS="300")
    assert config.vad_start_frames == 10


def test_stt_key_falls_back_to_groq_llm(tmp_path: Path) -> None:
    config = _load(tmp_path, LLM_API_KEY="llm-key")
    assert config.stt_api_key == "llm-key"

    other = _load(tmp_path, LLM_API_KEY="llm-key", LLM_BASE_URL="https://example.com/v1")
    assert other.stt_api_key == ""

    explicit = _load(tmp_path, GROQ_API_KEY="groq-key", LLM_BASE_URL="https://example.com/v1")
    assert explicit.stt_api_key == "groq-key"


def test_require_llm_key(tmp_path: Path) -> None:
    config = _load(tmp_path)
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        config.require_llm_key()
    assert _load(tmp_path, LLM_API_KEY="key").require_llm_key() == "key"


def test_mask_secret() -> None:
    assert mask_secret("") == "(vacía)"
    assert mask_secret("short") == "***"
    assert mask_secret("abcdefghijkl") == "abcd…ijkl"


def test_read_env_file_rejects_bad_line(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("THIS IS NOT VALID\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="formato"):
        read_env_file(env_file)


def test_update_env_file_preserves_and_protects(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    update_env_file(
        env_file,
        {"LLM_API_KEY": "secret", "AUDIO_INPUT_DEVICE": "plughw:CARD=X,DEV=0"},
    )
    text = env_file.read_text(encoding="utf-8")
    assert "# Configuración de SIRAH." in text
    assert "LLM_API_KEY=secret" in text
    assert "AUDIO_INPUT_DEVICE=plughw:CARD=X,DEV=0" in text
    assert os.stat(env_file).st_mode & 0o777 == 0o600

    update_env_file(env_file, {"LLM_API_KEY": "new secret"})
    text = env_file.read_text(encoding="utf-8")
    assert 'LLM_API_KEY="new secret"' in text
    assert text.count("LLM_API_KEY=") == 1
    assert "# Configuración de SIRAH." in text


def test_update_env_file_tmp_is_private_from_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El temporal lleva el secreto: no debe existir ni un instante legible por otros."""
    env_file = tmp_path / ".env"
    seen: list[int] = []
    original_chmod = os.chmod

    def patched_chmod(path, mode, *args, **kwargs):
        seen.append(Path(path).stat().st_mode & 0o777)
        return original_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr("sirah.config.os.chmod", patched_chmod)
    previous_umask = os.umask(0o022)
    try:
        update_env_file(env_file, {"LLM_API_KEY": "secret"})
    finally:
        os.umask(previous_umask)

    assert seen == [0o600]
    assert os.stat(env_file).st_mode & 0o777 == 0o600


def test_audio_player_command_defaults_to_aplay(tmp_path: Path) -> None:
    config = _load(tmp_path, LLM_API_KEY="k")
    assert config.audio_player_command == "aplay"
    other = _load(tmp_path, LLM_API_KEY="k", AUDIO_PLAYER_COMMAND="paplay")
    assert other.audio_player_command == "paplay"


def test_adaptive_vad_defaults(tmp_path: Path) -> None:
    config = _load(tmp_path, LLM_API_KEY="k")
    assert config.vad_noise_calibration_ms == 500
    assert config.vad_start_multiple == 1.6
    assert config.vad_end_multiple == 1.2
    assert config.vad_min_start_rms == 1200
    assert config.vad_min_end_rms == 600


def test_vad_min_rms_is_an_alias_of_the_start_minimum(tmp_path: Path) -> None:
    config = _load(tmp_path, LLM_API_KEY="k", VAD_MIN_RMS="2500")
    assert config.vad_min_start_rms == 2500
    both = _load(tmp_path, LLM_API_KEY="k", VAD_MIN_RMS="2500", VAD_MIN_START_RMS="3000")
    assert both.vad_min_start_rms == 3000
    high = _load(tmp_path, LLM_API_KEY="k", VAD_MIN_RMS="8000")
    assert high.vad_min_start_rms == 8000
    # Un .env antiguo con 350 no debe romper la validación inicio > fin.
    legacy = _load(tmp_path, LLM_API_KEY="k", VAD_MIN_RMS="350")
    assert legacy.vad_min_start_rms == 350
    assert legacy.vad_min_end_rms == 175
    with pytest.raises(ConfigError, match="VAD_MIN_RMS"):
        _load(tmp_path, LLM_API_KEY="k", VAD_MIN_RMS="mucho")


def test_vad_rejects_incoherent_thresholds(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="VAD_MIN_END_RMS"):
        _load(tmp_path, LLM_API_KEY="k", VAD_MIN_START_RMS="600", VAD_MIN_END_RMS="600")
    with pytest.raises(ConfigError, match="VAD_START_MULTIPLE"):
        _load(tmp_path, LLM_API_KEY="k", VAD_START_MULTIPLE="1")
    with pytest.raises(ConfigError, match="VAD_END_MULTIPLE"):
        _load(tmp_path, LLM_API_KEY="k", VAD_END_MULTIPLE="0.9")


def test_audio_player_command_reports_whether_it_was_set(tmp_path: Path) -> None:
    default = _load(tmp_path, LLM_API_KEY="k")
    assert default.audio_player_command == "aplay"
    assert default.audio_player_command_set is False
    custom = _load(tmp_path, LLM_API_KEY="k", AUDIO_PLAYER_COMMAND="paplay")
    assert custom.audio_player_command_set is True
