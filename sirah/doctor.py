"""Diagnóstico de cada capa, con una solución concreta por falla."""

from __future__ import annotations

import contextlib
import grp
import hashlib
import importlib.util
import os
import platform
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx

from sirah.adapters.tts import player_arguments
from sirah.config import (
    PROJECT_ROOT,
    Config,
    PersonaSettings,
    active_card_path,
    identity_for,
    mask_secret,
)
from sirah.core.health import Health
from sirah.core.persona import PersonaError, load_persona
from sirah.core.voice import FRAME_BYTES, SAMPLE_RATE, AdaptiveSpeechDetector, wav_bytes

_CALIBRATION = PROJECT_ROOT / "config" / "eyes-calibration.toml"
_SERVO_KEYS = {
    "X": ("right", "center", "left"),
    "Y": ("down", "center", "up"),
    "SD": ("open", "closed"),
    "ID": ("open", "closed"),
    "SI": ("open", "closed"),
    "II": ("open", "closed"),
}
_LABELS = {"ok": "OK", "warn": "AVISO", "fail": "FALLA", "off": "APAGADA"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _service_active(name: str) -> bool:
    if shutil.which("systemctl") is None:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def alsa_cards(tool: str) -> int:
    try:
        result = subprocess.run(
            [tool, "-l"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    return sum(1 for line in result.stdout.splitlines() if line.startswith("card "))


def _check_python() -> Health:
    version = platform.python_version()
    ok = sys.version_info >= (3, 12)
    detail = f"Python {version} en {platform.system()} {platform.machine()}"
    if not ok:
        return Health(
            "Python", "fail", detail, "Instala Python 3.12 y vuelve a ejecutar `uv sync`."
        )
    if platform.system() != "Linux":
        return Health(
            "Python",
            "warn",
            detail,
            "SIRAH está pensado para Linux; el hardware no funcionará igual en otro sistema.",
        )
    return Health("Python", "ok", detail)


def _check_config(config: Config) -> Health:
    key = mask_secret(config.llm_api_key)
    detail = f"{config.env_file} · LLM {config.llm_model} en {config.llm_base_url} · clave {key}"
    if not config.llm_api_key:
        return Health(
            "Configuración",
            "warn",
            detail,
            "Ejecuta `sirah setup` o escribe LLM_API_KEY en .env.",
        )
    return Health("Configuración", "ok", detail)


def _check_llm(config: Config, offline: bool) -> Health:
    if not config.llm_api_key:
        return Health(
            "LLM",
            "fail",
            "no hay clave configurada",
            "Ejecuta `sirah setup` o escribe LLM_API_KEY en .env.",
        )
    if offline:
        return Health(
            "LLM",
            "ok",
            f"{config.llm_model}: clave configurada; red no comprobada (--offline)",
        )

    url = f"{config.llm_base_url}/models"
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {config.llm_api_key}"})
    except httpx.HTTPError as exc:
        return Health(
            "LLM",
            "warn",
            f"sin conexión con {config.llm_base_url}: {exc.__class__.__name__}",
            "Revisa la red o el firewall; el chat no funcionará hasta recuperarla.",
        )

    if response.status_code == 200:
        return Health("LLM", "ok", f"{config.llm_model}: conexión correcta")
    if response.status_code in {401, 403}:
        return Health(
            "LLM",
            "fail",
            f"la clave fue rechazada (HTTP {response.status_code})",
            "Revisa LLM_API_KEY y LLM_BASE_URL; genera una clave nueva si hace falta.",
        )
    if response.status_code == 404:
        return Health(
            "LLM",
            "warn",
            f"el endpoint no expone /models (HTTP 404): {config.llm_base_url}",
            "El chat puede funcionar igual; confirma que la URL incluye /v1 "
            "si tu proveedor lo pide.",
        )
    return Health(
        "LLM",
        "warn",
        f"respuesta HTTP {response.status_code} al comprobar el endpoint",
        "Revisa el estado del proveedor y LLM_BASE_URL.",
    )


def _check_persona(config: Config, settings: PersonaSettings | None = None) -> Health:
    settings = settings or config.persona_settings
    path = active_card_path(config, settings)
    try:
        persona = load_persona(path, user_name=config.user_name)
    except PersonaError as exc:
        return Health(
            "Persona",
            "fail",
            str(exc),
            "Corrige la tarjeta o elige otra con `--persona`; la tarjeta por "
            "defecto es config/persona/sirah.json.",
        )

    identity = identity_for(settings, persona.path)
    label = "robot (estricto)" if identity == "robot" else "card"
    detail = f"{persona.display_name} · {persona.path} · identidad {label}"
    status = "ok"
    fix = None
    if identity == "robot":
        status = "warn"
        fix = (
            "El modo robot estricto está activo en [persona] identity. "
            "Usa 'card' para que mande la tarjeta."
        )
    if not settings.exists:
        status = "warn"
        fix = (
            "Copia config/sirah.toml.example a config/sirah.toml o ejecuta "
            "`sirah setup`; ahora se usan valores por defecto."
        )
    problems = [*settings.warnings, *persona.warnings]
    if problems:
        status = "warn"
        detail += " · " + "; ".join(problems)
        fix = fix or "Revisa config/sirah.toml y la tarjeta."
    return Health("Persona", status, detail, fix)


def _valid_angle(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 180


def _check_calibration(path: Path = _CALIBRATION) -> Health:
    if not path.exists():
        return Health(
            "Calibración",
            "fail",
            f"no existe {path}",
            "Restaura config/eyes-calibration.toml; es la única fuente válida.",
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return Health(
            "Calibración",
            "fail",
            f"no se pudo leer: {exc}",
            f"Corrige {path}.",
        )

    channels = data.get("channels")
    if not isinstance(channels, dict) or set(channels) != set(_SERVO_KEYS):
        return Health(
            "Calibración",
            "fail",
            "la tabla [channels] debe tener exactamente X, Y, SD, ID, SI, II",
            "Restaura la calibración original; no la edites sin el dueño.",
        )
    for name, channel in channels.items():
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 5:
            return Health(
                "Calibración",
                "fail",
                f"el canal {name} debe ser un entero entre 0 y 5",
                "Restaura la calibración original.",
            )
    if sorted(channels.values()) != list(range(6)):
        return Health(
            "Calibración",
            "fail",
            "los canales deben ser únicos y cubrir 0–5",
            "Restaura la calibración original.",
        )

    servos = data.get("servo")
    if not isinstance(servos, dict):
        return Health(
            "Calibración",
            "fail",
            "falta la tabla [servo]",
            "Restaura la calibración original.",
        )
    for name, keys in _SERVO_KEYS.items():
        table = servos.get(name)
        if not isinstance(table, dict):
            return Health(
                "Calibración",
                "fail",
                f"falta la tabla [servo.{name}]",
                "Restaura la calibración original.",
            )
        for key in keys:
            if not _valid_angle(table.get(key)):
                return Health(
                    "Calibración",
                    "fail",
                    f"servo.{name}.{key} debe estar entre 0 y 180",
                    "Restaura la calibración original.",
                )

    boot = data.get("boot")
    expected = {
        "X": servos["X"]["center"],
        "Y": servos["Y"]["center"],
        "SD": servos["SD"]["open"],
        "ID": servos["ID"]["open"],
        "SI": servos["SI"]["open"],
        "II": servos["II"]["open"],
    }
    if not isinstance(boot, dict) or set(boot) != set(expected):
        return Health(
            "Calibración",
            "fail",
            "la tabla [boot] debe tener X, Y, SD, ID, SI, II",
            "Restaura la calibración original.",
        )
    for name, value in expected.items():
        if not _valid_angle(boot.get(name)) or boot[name] != value:
            return Health(
                "Calibración",
                "fail",
                f"boot.{name}={boot.get(name)} no coincide con la pose segura ({value})",
                "Restaura la calibración original; no dupliques estos valores en el código.",
            )

    return Health(
        "Calibración",
        "ok",
        f"6 canales y pose de arranque coherente · {path}",
    )


def _check_data_dir(config: Config) -> Health:
    try:
        created = not config.data_dir.exists()
        config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if created:
            os.chmod(config.data_dir, 0o700)
        with tempfile.NamedTemporaryFile(
            dir=config.data_dir, prefix=".write-", delete=True
        ) as handle:
            handle.write(b"ok")
    except OSError as exc:
        return Health(
            "Datos",
            "fail",
            f"no se puede escribir en {config.data_dir}: {exc.strerror or exc}",
            "Revisa SIRAH_DATA_DIR y sus permisos; debe ser una carpeta escribible.",
        )

    free = shutil.disk_usage(config.data_dir).free
    gigabytes = free / (1024**3)
    detail = f"{config.data_dir} · {gigabytes:.1f} GB libres"
    if gigabytes < 0.1:
        return Health(
            "Datos",
            "warn",
            detail,
            "Libera espacio; los logs y el historial necesitan al menos 100 MB.",
        )
    return Health("Datos", "ok", detail)


def _check_serial(config: Config) -> Health:
    if not config.eyes_address:
        return Health(
            "Ojos",
            "off",
            "apagados: EYES_ADDRESS está vacío",
            "Ejecuta `sirah setup` o escribe la ruta /dev/serial/by-id/... en EYES_ADDRESS.",
        )

    device = config.eyes_device
    if device is None:
        return Health(
            "Ojos", "fail", "EYES_ADDRESS no tiene una ruta válida", "Corrige EYES_ADDRESS."
        )

    if not device.exists():
        return Health(
            "Ojos",
            "warn",
            f"configurados en {device}, pero no está conectado",
            "Conecta el ESP32; SIRAH reintenta solo cuando aparezca. La prueba real es "
            "`sirah eyes test` (hito 2).",
        )

    try:
        info = device.stat()
    except OSError as exc:
        return Health(
            "Ojos", "fail", f"no se pudo leer {device}: {exc.strerror}", "Revisa el cable."
        )

    if not stat.S_ISCHR(info.st_mode):
        return Health(
            "Ojos",
            "fail",
            f"{device} no es un dispositivo de caracteres",
            "Revisa la ruta; debe ser el puerto del ESP32.",
        )

    try:
        group = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        group = str(info.st_gid)

    notes: list[str] = []
    if not os.access(device, os.R_OK | os.W_OK):
        if group in {"dialout", "uucp", "tty"}:
            return Health(
                "Ojos",
                "fail",
                f"sin permiso de lectura/escritura en {device} (grupo {group})",
                "Añade tu usuario al grupo: `sudo usermod -aG dialout $USER` y vuelve a "
                "iniciar sesión.",
            )
        return Health(
            "Ojos",
            "fail",
            f"sin permiso de lectura/escritura en {device}",
            f"Revisa los permisos del dispositivo (grupo {group}).",
        )

    if "/dev/serial/by-id/" not in config.eyes_address:
        notes.append("usa /dev/serial/by-id/... para sobrevivir a renumeraciones")
    for service in ("ModemManager", "brltty"):
        if _service_active(service):
            notes.append(
                f"{service} está activo y puede capturar el puerto; "
                f"desactívalo si no lo usas (`sudo systemctl disable --now {service}`)"
            )

    detail = f"{device} · grupo {group} · handshake en `sirah eyes test` (hito 2)"
    if notes:
        return Health("Ojos", "warn", f"{detail} · {'; '.join(notes)}")
    return Health("Ojos", "ok", detail)


def _check_camera(config: Config) -> Health:
    if not config.vision_enabled:
        return Health(
            "Visión",
            "off",
            "apagada: VISION_ENABLED=false",
            "Actívala en .env (VISION_ENABLED=true) cuando tengas cámara; el "
            "seguimiento llega en el hito 3.",
        )

    device = Path(config.vision_camera)
    if not device.exists():
        return Health(
            "Visión",
            "fail",
            f"no existe la cámara {device}",
            "Conecta la cámara o cambia VISION_CAMERA; también puedes desactivar la visión.",
        )
    try:
        info = device.stat()
    except OSError as exc:
        return Health(
            "Visión", "fail", f"no se pudo leer {device}: {exc.strerror}", "Revisa la cámara."
        )
    if not stat.S_ISCHR(info.st_mode):
        return Health(
            "Visión", "fail", f"{device} no es un dispositivo de cámara", "Revisa VISION_CAMERA."
        )
    if not os.access(device, os.R_OK):
        try:
            group = grp.getgrgid(info.st_gid).gr_name
        except KeyError:
            group = str(info.st_gid)
        fix = (
            "Añade tu usuario al grupo: `sudo usermod -aG video $USER` y vuelve a iniciar sesión."
            if group == "video"
            else f"Revisa los permisos de {device} (grupo {group})."
        )
        return Health("Visión", "fail", f"sin permiso de lectura en {device}", fix)

    if importlib.util.find_spec("cv2") is None:
        return Health(
            "Visión",
            "fail",
            f"{device} accesible, pero falta OpenCV",
            "La visión llega en el hito 3; mientras tanto deja VISION_ENABLED=false.",
        )
    return Health("Visión", "ok", f"{device} accesible · OpenCV instalado")


def _check_vision_model(config: Config) -> Health:
    model = config.vision_model
    if not model.exists():
        status = "fail" if config.vision_enabled else "warn"
        return Health(
            "Modelo YuNet",
            status,
            f"no existe {model}",
            "Restaura models/face_detection_yunet_2023mar.onnx y su .sha256.",
        )
    checksum_file = model.with_name(f"{model.name}.sha256")
    if not checksum_file.exists():
        return Health(
            "Modelo YuNet",
            "warn",
            f"{model.name} presente, sin archivo .sha256",
            "Restaura el checksum del modelo para poder verificarlo.",
        )
    try:
        lines = checksum_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return Health("Modelo YuNet", "warn", f"no se pudo leer el checksum: {exc.strerror}")
    expected = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            expected = stripped.split()[0].lower()
            break
    if len(expected) != 64:
        return Health(
            "Modelo YuNet",
            "warn",
            f"checksum ilegible en {checksum_file.name}",
            "Restaura el .sha256 original.",
        )
    try:
        actual = _sha256(model)
    except OSError as exc:
        return Health("Modelo YuNet", "fail", f"no se pudo leer el modelo: {exc.strerror}")
    if actual != expected:
        return Health(
            "Modelo YuNet",
            "fail",
            "el SHA256 no coincide: el modelo está alterado o incompleto",
            "Restaura models/face_detection_yunet_2023mar.onnx; no lo modifiques.",
        )
    return Health("Modelo YuNet", "ok", f"{model.name} verificado · SHA256 {actual[:12]}…")


@dataclass(frozen=True)
class PlayerChoice:
    """Reproductor elegido para esta sesión y aviso o fallo asociado."""

    command: tuple[str, ...] | None
    message: str = ""


def _run_player(args: list[str], silent: bytes, timeout: float) -> tuple[int, bytes] | None:
    """Ejecuta el reproductor en su propio grupo; None si se cuelga."""
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        raise
    try:
        _, stderr = process.communicate(silent, timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return None
    return process.returncode or 0, stderr


def _probe(command: list[str], device: str, timeout: float) -> tuple[str | None, bool]:
    """Prueba 200 ms de silencio; devuelve (problema, se_colgó)."""
    silent = wav_bytes(b"\x00\x00" * 4410, rate=22050)  # 200 ms
    name = Path(command[0]).name
    try:
        result = _run_player(player_arguments(command, device), silent, timeout)
    except OSError as exc:
        return f"no se pudo ejecutar {name}: {exc.strerror}", False
    if result is None:
        return f"{name} se colgó al reproducir 200 ms de silencio", True
    code, stderr = result
    if code != 0:
        hint = stderr.decode(errors="replace").strip().splitlines()
        detail = f" ({hint[-1]})" if hint else ""
        return f"{name} no pudo reproducir 200 ms de silencio{detail}", False
    return None, False


def resolve_player(config: Config, *, timeout: float = 3.0) -> PlayerChoice:
    """Elige reproductor: respeta el fijado y, si no, cae de aplay a PipeWire."""
    if config.audio_player_command_set:
        return PlayerChoice(tuple(shlex.split(config.audio_player_command)))
    if shutil.which("aplay") is None:
        problem = "aplay no está disponible"
    else:
        problem, _ = _probe(["aplay"], config.audio_output_device, timeout)
    if problem is None:
        return PlayerChoice(("aplay",))
    for candidate in ("paplay", "pw-play"):
        if shutil.which(candidate) is None:
            continue
        candidate_problem, _ = _probe([candidate], config.audio_output_device, timeout)
        if candidate_problem is None:
            reason = (
                "aplay no responde con PipeWire"
                if problem == "aplay se colgó al reproducir 200 ms de silencio"
                else problem
            )
            return PlayerChoice(
                (candidate,),
                f"{reason}; uso {candidate}. Fíjalo con AUDIO_PLAYER_COMMAND.",
            )
    return PlayerChoice(None, problem)


def _check_audio(config: Config) -> Health:
    if shutil.which("arecord") is None:
        return Health(
            "Audio",
            "warn",
            "falta arecord",
            "Instala ALSA: `sudo apt install alsa-utils`.",
        )
    players = [name for name in ("aplay", "paplay", "pw-play") if shutil.which(name)]
    if not players:
        return Health(
            "Audio",
            "warn",
            "no hay reproductor (aplay, paplay ni pw-play)",
            "Instala alsa-utils o usa AUDIO_PLAYER_COMMAND con un reproductor compatible.",
        )
    choice = resolve_player(config)
    if choice.command is None:
        return Health(
            "Audio",
            "fail",
            choice.message,
            "Reinicia PipeWire (`systemctl --user restart pipewire wireplumber`), "
            "prueba otro AUDIO_OUTPUT_DEVICE o fija AUDIO_PLAYER_COMMAND=paplay.",
        )
    player = Path(choice.command[0]).name
    inputs = alsa_cards("arecord")
    outputs = alsa_cards("aplay") if shutil.which("aplay") else 0
    if not inputs or not outputs:
        return Health(
            "Audio",
            "warn",
            f"{inputs} tarjeta(s) de captura y {outputs} de reproducción",
            "Conecta micrófono/altavoz y revisa `arecord -l` y `aplay -l`.",
        )
    if importlib.util.find_spec("webrtcvad") is None:
        return Health(
            "Audio",
            "warn",
            f"{inputs} captura(s), {outputs} salida(s); falta el VAD",
            "Instala las dependencias de voz con `uv sync --all-extras`.",
        )
    devices = []
    if config.audio_input_device:
        devices.append(f"entrada={config.audio_input_device}")
    if config.audio_output_device:
        devices.append(f"salida={config.audio_output_device}")
    suffix = f" · {' · '.join(devices)}" if devices else " · dispositivos por defecto"
    detail = f"{inputs} captura(s), {outputs} salida(s) · reproductor {player}{suffix}"
    if choice.message:
        return Health(
            "Audio",
            "warn",
            f"{detail} · {choice.message}",
            "Fija el reproductor elegido en AUDIO_PLAYER_COMMAND.",
        )
    return Health("Audio", "ok", detail)


def find_piper() -> Path | None:
    spec = importlib.util.find_spec("piper")
    if spec is None:
        return None
    return Path(spec.origin)


def _check_piper(config: Config) -> Health:
    binary = find_piper()
    model = config.tts_model
    model_json = model.with_name(f"{model.name}.json")
    missing: list[str] = []
    if binary is None:
        missing.append("el módulo piper")
    if not model.exists():
        missing.append(f"el modelo {model.name}")
    if not model_json.exists():
        missing.append("el archivo .onnx.json")
    if missing:
        fixes = []
        if binary is None:
            fixes.append("`uv sync --all-extras`")
        if not model.exists() or not model_json.exists():
            fixes.append("`sirah setup` para descargar la voz")
        return Health(
            "Piper",
            "warn",
            "falta " + ", ".join(missing),
            " y ".join(fixes) + ".",
        )
    return Health("Piper", "ok", f"{binary} · {model.name}")


def _check_vad(config: Config) -> Health:
    """Mide el suelo de ruido real con 1 s de micrófono."""
    if shutil.which("arecord") is None:
        return Health(
            "VAD",
            "warn",
            "falta arecord",
            "Instala alsa-utils: `sudo apt install alsa-utils`.",
        )
    args = [
        "arecord",
        "-q",
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-r",
        str(SAMPLE_RATE),
        "-c",
        "1",
        "-d",
        "1",
    ]
    if config.audio_input_device:
        args += ["-D", config.audio_input_device]
    try:
        done = subprocess.run(args, capture_output=True, timeout=3, check=False)
    except subprocess.TimeoutExpired:
        return Health(
            "VAD",
            "warn",
            "arecord se colgó al medir el ruido",
            "Revisa el micrófono con `arecord -l` y prueba `sirah voice --check`.",
        )
    except OSError as exc:
        return Health("VAD", "warn", f"no se pudo ejecutar arecord: {exc.strerror}")
    if done.returncode != 0:
        detail = done.stderr.decode(errors="replace").strip().splitlines()
        last = detail[-1] if detail else "sin detalle"
        return Health(
            "VAD",
            "warn",
            f"arecord falló ({last})",
            "Revisa AUDIO_INPUT_DEVICE y el micrófono (`arecord -l`).",
        )
    frames = [
        done.stdout[index : index + FRAME_BYTES]
        for index in range(0, len(done.stdout) - FRAME_BYTES + 1, FRAME_BYTES)
    ]
    if not frames:
        return Health(
            "VAD",
            "warn",
            "arecord no devolvió audio",
            "Revisa el micrófono y el volumen de captura (`alsamixer`).",
        )
    detector = AdaptiveSpeechDetector(
        noise_calibration_ms=config.vad_noise_calibration_ms,
        start_multiple=config.vad_start_multiple,
        end_multiple=config.vad_end_multiple,
        min_start_rms=config.vad_min_start_rms,
        min_end_rms=config.vad_min_end_rms,
    )
    for frame in frames:
        detector(frame)
    floor = detector.noise_floor or 0.0
    detail = (
        f"suelo {floor:.0f} RMS · umbrales inicio "
        f"{detector.start_threshold:.0f}, fin {detector.end_threshold:.0f}"
    )
    if detector.pending_warning:
        return Health(
            "VAD",
            "warn",
            detail,
            "Baja la ganancia con `alsamixer -c 0` (F4) o en pavucontrol → "
            "Grabación, y repite `sirah voice --check` en silencio hasta ver "
            "un suelo < 1500.",
        )
    return Health("VAD", "ok", detail)


def _check_voice(config: Config) -> Health:
    missing: list[str] = []
    if not config.stt_api_key:
        missing.append("GROQ_API_KEY")
    for tool in ("arecord", "aplay"):
        if shutil.which(tool) is None:
            missing.append(tool)
    if find_piper() is None:
        missing.append("piper")
    model = config.tts_model
    if not model.exists() or not model.with_name(f"{model.name}.json").exists():
        missing.append(model.name)

    cloud = "nube: el audio se envía a Groq para transcribir; no se guarda en disco"
    if missing:
        return Health(
            "Voz",
            "warn",
            f"faltan {', '.join(missing)} · {cloud}",
            "Completa las variables de voz y ejecuta `sirah doctor`; "
            "`sirah voice --check` ajusta el micrófono.",
        )
    key = config.stt_api_key
    origin = "" if config.groq_api_key else " (se reutiliza LLM_API_KEY)"
    return Health(
        "Voz",
        "ok",
        f"arecord y reproductor listos · {config.stt_model} · {config.stt_language} · "
        f"clave {mask_secret(key)}{origin} · {cloud}",
    )


def run_checks(config: Config, offline: bool = False) -> list[Health]:
    """Comprueba todas las capas sin abrir el puerto serial."""
    return [
        _check_python(),
        _check_config(config),
        _check_llm(config, offline),
        _check_persona(config),
        _check_calibration(),
        _check_data_dir(config),
        _check_serial(config),
        _check_camera(config),
        _check_vision_model(config),
        _check_audio(config),
        _check_vad(config),
        _check_piper(config),
        _check_voice(config),
    ]


def print_report(checks: list[Health], env_file: Path) -> int:
    print(f"SIRAH doctor · configuración: {env_file}")
    print()
    for check in checks:
        print(f"[{_LABELS[check.status]:<7}] {check.name}: {check.detail}")
        if check.fix:
            print(f"          Solución: {check.fix}")

    counts = {status: 0 for status in _LABELS}
    for check in checks:
        counts[check.status] += 1
    print()
    print(
        f"Resumen: {counts['ok']} OK, {counts['warn']} aviso(s), "
        f"{counts['fail']} falla(s), {counts['off']} capa(s) apagada(s)."
    )
    if counts["fail"]:
        print("Corrige las fallas y vuelve a ejecutar `sirah doctor`.")
        return 1
    print("Todo lo comprobado está en orden. Las capas apagadas se activan cuando las configures.")
    return 0
