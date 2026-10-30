from __future__ import annotations

import hashlib
import io
import wave
from array import array
from pathlib import Path

from sirah.config import load_config, load_persona_settings
from sirah.core.health import Health
from sirah.doctor import (
    _check_audio,
    _check_calibration,
    _check_config,
    _check_data_dir,
    _check_llm,
    _check_persona,
    _check_piper,
    _check_serial,
    _check_vad,
    _check_vision_model,
    _check_voice,
    find_piper,
    print_report,
    resolve_player,
)

CALIBRATION = """\
[pwm]
frequency_hz = 50
pulse_0_us = 1000
pulse_180_us = 2000

[channels]
X = 0
Y = 1
SD = 2
ID = 3
SI = 4
II = 5

[servo.X]
right = 60
center = 120
left = 180

[servo.Y]
down = 15
center = 30
up = 60

[servo.SD]
open = 110
closed = 15

[servo.ID]
open = 120
closed = 180

[servo.SI]
open = 50
closed = 145

[servo.II]
open = 110
closed = 50

[boot]
X = {boot_x}
Y = 30
SD = 110
ID = 120
SI = 50
II = 110
"""


def _config(tmp_path: Path, **env: str):
    return load_config(
        env_file=tmp_path / "missing.env",
        environ={"XDG_DATA_HOME": str(tmp_path / "xdg"), **env},
    )


def test_calibration_ok(tmp_path: Path) -> None:
    path = tmp_path / "calibration.toml"
    path.write_text(CALIBRATION.format(boot_x=120), encoding="utf-8")
    assert _check_calibration(path).status == "ok"


def test_piper_missing_suggests_combined_extras(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sirah.doctor.find_piper", lambda: None)
    config = _config(tmp_path, TTS_MODEL=str(tmp_path / "voz.onnx"))
    result = _check_piper(config)
    assert result.status == "warn"
    assert result.fix is not None
    assert "uv sync --all-extras" in result.fix


def test_voice_warns_about_the_cloud_and_the_missing_key(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = _check_voice(config)
    assert result.status == "warn"
    assert "GROQ_API_KEY" in result.detail
    assert "nube" in result.detail and "no se guarda en disco" in result.detail
    assert result.fix is not None


def test_calibration_boot_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "calibration.toml"
    path.write_text(CALIBRATION.format(boot_x=121), encoding="utf-8")
    result = _check_calibration(path)
    assert result.status == "fail"
    assert "boot.X" in result.detail


def test_calibration_missing(tmp_path: Path) -> None:
    result = _check_calibration(tmp_path / "no.toml")
    assert result.status == "fail"


def test_calibration_bad_channels(tmp_path: Path) -> None:
    path = tmp_path / "calibration.toml"
    text = CALIBRATION.format(boot_x=120).replace("X = 0", "X = 9")
    path.write_text(text, encoding="utf-8")
    result = _check_calibration(path)
    assert result.status == "fail"
    assert "canal X" in result.detail


def test_config_requires_key(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert _check_config(config).status == "warn"
    assert _check_config(_config(tmp_path, LLM_API_KEY="key")).status == "ok"


def test_llm_offline_does_not_touch_network(tmp_path: Path) -> None:
    config = _config(tmp_path, LLM_API_KEY="key")
    assert _check_llm(config, offline=True).status == "ok"
    assert _check_llm(_config(tmp_path), offline=True).status == "fail"


def test_persona_check_reports_card_and_identity(tmp_path: Path) -> None:
    path = tmp_path / "prueba.json"
    path.write_text(
        '{"spec":"chara_card_v2","data":{"name":"Prueba","personality":"Directa."}}',
        encoding="utf-8",
    )
    config = _config(tmp_path, SIRAH_PERSONA=str(path))
    missing = load_persona_settings(tmp_path / "no.toml")
    result = _check_persona(config, missing)
    assert result.status == "warn"
    assert "Prueba" in result.detail
    assert "identidad card" in result.detail
    assert "sirah.toml" in result.fix

    settings_path = tmp_path / "sirah.toml"
    settings_path.write_text('[persona]\nidentity = "personaje"\n', encoding="utf-8")
    settings = load_persona_settings(settings_path)
    assert _check_persona(config, settings).status == "ok"
    assert "identidad card" in _check_persona(config, settings).detail

    settings_path.write_text('[persona]\nidentity = "robot"\n', encoding="utf-8")
    strict = _check_persona(config, load_persona_settings(settings_path))
    assert strict.status == "warn"
    assert "identidad robot (estricto)" in strict.detail
    assert "modo robot estricto" in strict.fix.lower()

    path.write_text("{}", encoding="utf-8")
    assert _check_persona(config, settings).status == "fail"


def test_data_dir_is_created(tmp_path: Path) -> None:
    target = tmp_path / "data"
    config = _config(tmp_path, SIRAH_DATA_DIR=str(target))
    assert _check_data_dir(config).status == "ok"
    assert target.is_dir()


def test_serial_off_and_missing(tmp_path: Path) -> None:
    assert _check_serial(_config(tmp_path)).status == "off"
    missing = _config(tmp_path, EYES_ADDRESS=f"serial://{tmp_path}/no-existe")
    assert _check_serial(missing).status == "warn"


def test_serial_rejects_regular_file(tmp_path: Path) -> None:
    device = tmp_path / "tty-falso"
    device.write_text("no soy un puerto", encoding="utf-8")
    result = _check_serial(_config(tmp_path, EYES_ADDRESS=f"serial://{device}"))
    assert result.status == "fail"
    assert "caracteres" in result.detail


def test_vision_model_checksum(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"modelo de prueba")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    model.with_name(f"{model.name}.sha256").write_text(
        f"# comentario\n{digest}  {model.name}\n",
        encoding="utf-8",
    )
    config = _config(tmp_path, VISION_MODEL=str(model))
    assert _check_vision_model(config).status == "ok"

    model.write_bytes(b"modelo alterado")
    assert _check_vision_model(config).status == "fail"


def test_find_piper_ignores_fake_executable(monkeypatch) -> None:
    monkeypatch.setattr(
        "sirah.doctor.shutil.which",
        lambda name: "/tmp/piper" if name == "piper" else None,
    )
    monkeypatch.setattr("sirah.doctor.importlib.util.find_spec", lambda name: None)
    assert find_piper() is None


def test_find_piper_returns_spec_origin(monkeypatch) -> None:
    class Spec:
        origin = "/ruta/piper/__init__.py"

    monkeypatch.setattr("sirah.doctor.importlib.util.find_spec", lambda name: Spec())
    assert find_piper() == Path("/ruta/piper/__init__.py")


def test_print_report_exit_code(capsys) -> None:
    checks = [
        Health("A", "ok", "bien"),
        Health("B", "fail", "mal", "haz esto"),
    ]
    assert print_report(checks, Path("/tmp/.env")) == 1
    output = capsys.readouterr().out
    assert "FALLA" in output
    assert "Solución: haz esto" in output


def test_doctor_audio_reports_a_hung_player(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("sirah.doctor.alsa_cards", lambda tool: 1)
    monkeypatch.setattr("sirah.doctor.importlib.util.find_spec", lambda name: object())

    monkeypatch.setattr("sirah.doctor._run_player", lambda *args, **kwargs: None)

    result = _check_audio(config)

    assert result.status == "fail"
    assert "pipewire" in (result.fix or "").lower()


def test_doctor_reports_vad_floor_and_thresholds(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    noise = array("h", [1500] * 320).tobytes() * 50

    class Done:
        returncode = 0
        stdout = noise
        stderr = b""

    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("sirah.doctor.subprocess.run", lambda *a, **k: Done())

    result = _check_vad(config)

    assert result.status == "ok"
    assert "suelo 1500" in result.detail
    assert "inicio 2400" in result.detail and "fin 1800" in result.detail


def test_doctor_vad_warns_when_arecord_fails(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")

    class Done:
        returncode = 1
        stdout = b""
        stderr = b"device busy"

    monkeypatch.setattr("sirah.doctor.subprocess.run", lambda *a, **k: Done())

    result = _check_vad(config)

    assert result.status == "warn"
    assert "device busy" in result.detail


class _PlayerOK:
    returncode = 0
    stderr = b""


def test_player_autoselection_keeps_aplay_when_it_works(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr("sirah.doctor._run_player", lambda *a, **k: (0, b""))

    choice = resolve_player(config)

    assert choice.command == ("aplay",)
    assert choice.message == ""


def test_player_autoselection_falls_back_to_paplay_when_aplay_hangs(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")

    def run(args, *extra):
        if Path(args[0]).name == "aplay":
            return None
        return (0, b"")

    monkeypatch.setattr("sirah.doctor._run_player", run)

    choice = resolve_player(config)

    assert choice.command == ("paplay",)
    assert "aplay no responde" in choice.message
    assert "AUDIO_PLAYER_COMMAND" in choice.message


def test_player_autoselection_uses_pw_play_when_paplay_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        "sirah.doctor.shutil.which", lambda tool: None if tool == "paplay" else f"/usr/bin/{tool}"
    )

    def run(args, *extra):
        if Path(args[0]).name == "aplay":
            return None
        return (0, b"")

    monkeypatch.setattr("sirah.doctor._run_player", run)

    choice = resolve_player(config)

    assert choice.command == ("pw-play",)


def test_explicit_player_is_used_without_probing(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path, AUDIO_PLAYER_COMMAND="paplay --volume=30000")
    monkeypatch.setattr(
        "sirah.doctor._run_player",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe probar")),
    )

    choice = resolve_player(config)

    assert choice.command == ("paplay", "--volume=30000")
    assert choice.message == ""


def test_player_autoselection_fails_when_nothing_plays(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("sirah.doctor.shutil.which", lambda tool: f"/usr/bin/{tool}")

    monkeypatch.setattr("sirah.doctor._run_player", lambda *args, **kwargs: None)

    choice = resolve_player(config)

    assert choice.command is None
    assert "aplay" in choice.message


def test_playback_probe_uses_200_ms(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    captured: dict[str, bytes] = {}

    def run(args, silent, timeout):
        captured["silent"] = silent
        return (0, b"")

    monkeypatch.setattr("sirah.doctor._run_player", run)

    resolve_player(config)

    with wave.open(io.BytesIO(captured["silent"]), "rb") as wav:
        assert abs(wav.getnframes() / wav.getframerate() - 0.2) < 0.001


def test_player_autoselection_without_aplay_uses_paplay(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        "sirah.doctor.shutil.which", lambda tool: None if tool == "aplay" else f"/usr/bin/{tool}"
    )
    monkeypatch.setattr("sirah.doctor._run_player", lambda *a, **k: (0, b""))

    choice = resolve_player(config)

    assert choice.command == ("paplay",)
    assert "aplay no está disponible" in choice.message
