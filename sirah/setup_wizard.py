"""Asistente `sirah setup`: crea la configuración y detecta hardware."""

from __future__ import annotations

import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from serial.tools import list_ports

from sirah.config import (
    PROJECT_ROOT,
    ConfigError,
    mask_secret,
    read_env_file,
    update_env_file,
)
from sirah.doctor import find_piper

VOICE_REVISION = "5041a7a49ae5b3a0f30e6837769eb03fdbb231bd"
VOICE_BASE = (
    f"https://huggingface.co/rhasspy/piper-voices/resolve/{VOICE_REVISION}/es/es_MX/claude/high"
)
VOICE_FILES = {
    "es_MX-claude-high.onnx": (
        "3ef40a71ea63852cd8ab7e6fa7d2ecdcfa67a0b47c9c48e3f10e02ee02083ea0",
        63_122_309,
    ),
    "es_MX-claude-high.onnx.json": (
        "1afc81f703c0e4cb3b4d7c0dca096b8b54a98806807f0170cf5eb5557723c12d",
        4_963,
    ),
}


class SetupError(Exception):
    """Error recuperable del asistente."""


def ensure_settings_file(project_root: Path = PROJECT_ROOT) -> Path | None:
    """Crea `config/sirah.toml` desde el example, sin sobrescribir lo existente."""
    target = project_root / "config" / "sirah.toml"
    example = target.with_name("sirah.toml.example")
    if target.exists() or not example.exists():
        return None
    shutil.copyfile(example, target)
    os.chmod(target, 0o600)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError as exc:
        raise SetupError("entrada cancelada") from exc
    return answer or default


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    marker = "S/n" if default else "s/N"
    while True:
        answer = _ask(f"{prompt} ({marker})").lower()
        if not answer:
            return default
        if answer in {"s", "si", "sí", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Responde 's' o 'n'.")


def _ask_secret(prompt: str) -> str:
    try:
        return getpass.getpass(f"{prompt}: ").strip()
    except EOFError as exc:
        raise SetupError("entrada cancelada") from exc


def _read_by_id() -> dict[str, str]:
    by_id: dict[str, str] = {}
    links = Path("/dev/serial/by-id")
    if links.is_dir():
        for link in sorted(links.iterdir()):
            try:
                by_id[str(link.resolve())] = str(link)
            except OSError:
                continue
    return by_id


def _serial_candidates(ports: list[object], by_id: dict[str, str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for port in sorted(ports, key=lambda item: item.device):
        try:
            real = str(Path(port.device).resolve())
        except OSError:
            real = port.device
        path = by_id.get(real, port.device)
        description = (port.description or "").strip()
        # pyserial lista /dev/ttyS0..31 aunque no exista hardware real.
        if path == port.device and port.vid is None and description.lower() in {"", "n/a"}:
            continue
        if path in seen:
            continue
        seen.add(path)
        if not description or description.lower() == "n/a":
            description = "sin descripción"
        if port.vid is not None and port.pid is not None:
            description += f" [{port.vid:04x}:{port.pid:04x}]"
        found.append((path, description))
    return found


def detect_serial_ports() -> list[tuple[str, str]]:
    """Lista puertos seriales, prefiriendo siempre /dev/serial/by-id/..."""
    return _serial_candidates(list(list_ports.comports()), _read_by_id())


def detect_cameras() -> list[str]:
    return sorted(str(path) for path in Path("/dev").glob("video*") if path.is_char_device())


def _is_groq(base: str) -> bool:
    """True si la URL base apunta al host de Groq."""
    return (urlparse(base).hostname or "").endswith("groq.com")


def _print_alsa() -> None:
    for tool, title in (("arecord", "Captura"), ("aplay", "Reproducción")):
        print(f"\n{title} ({tool} -l):")
        if shutil.which(tool) is None:
            print(f"  {tool} no está instalado (sudo apt install alsa-utils).")
            continue
        try:
            result = subprocess.run(
                [tool, "-l"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"  No se pudo ejecutar {tool}: {exc}")
            continue
        output = result.stdout.strip()
        if output:
            for line in output.splitlines()[:6]:
                print(f"  {line}")
        else:
            print("  No se detectaron tarjetas.")


def _choose(prompt: str, options: list[str], default_index: int = 0) -> str | None:
    if not options:
        return None
    print()
    for index, option in enumerate(options, start=1):
        marker = " (recomendado)" if index - 1 == default_index else ""
        print(f"  {index}. {option}{marker}")
    raw = _ask(f"{prompt} [1-{len(options)}]", str(default_index + 1))
    try:
        selected = int(raw) - 1
    except ValueError:
        selected = default_index
    if not 0 <= selected < len(options):
        selected = default_index
    return options[selected]


def download_voice(destination: Path, assume_yes: bool = False) -> None:
    """Descarga la voz de Piper con revisión y SHA256 fijados."""
    destination.mkdir(parents=True, exist_ok=True)
    if not assume_yes and not _ask_yes_no(
        f"¿Descargar la voz es_MX-claude-high (unos 60 MB) en {destination}?", True
    ):
        return

    for name, (expected_hash, expected_size) in VOICE_FILES.items():
        target = destination / name
        if target.exists() and _sha256(target) == expected_hash:
            print(f"  {name}: ya está y el SHA256 coincide.")
            continue
        url = f"{VOICE_BASE}/{name}"
        temporary = target.with_name(f".{target.name}.part")
        print(f"  Descargando {name} ({expected_size / 1_000_000:.0f} MB)…")
        try:
            timeout = httpx.Timeout(30.0, read=120.0)
            with (
                httpx.Client(timeout=timeout, follow_redirects=True) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes(65536):
                        handle.write(chunk)
            actual_hash = _sha256(temporary)
            size = temporary.stat().st_size
            if actual_hash != expected_hash or size != expected_size:
                temporary.unlink(missing_ok=True)
                raise SetupError(
                    f"{name} no coincide con el SHA256/tamaño esperado; no se instaló."
                )
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        except SetupError:
            raise
        except (OSError, httpx.HTTPError) as exc:
            temporary.unlink(missing_ok=True)
            raise SetupError(f"No se pudo descargar {name}: {exc}") from exc
        print(f"  {name}: listo.")


def _find_calibration() -> Path:
    return PROJECT_ROOT / "config" / "eyes-calibration.toml"


def run_setup(env_file: Path | None = None) -> int:
    """Asistente interactivo. No abre el puerto serial ni mueve servos."""
    if not sys.stdin.isatty():
        print("`sirah setup` necesita una terminal interactiva.")
        return 1

    if env_file is None:
        raw = os.environ.get("SIRAH_ENV_FILE")
        env_file = Path(raw).expanduser() if raw else PROJECT_ROOT / ".env"
    env_file = env_file.expanduser().resolve()

    try:
        current = {**read_env_file(env_file), **os.environ}
    except ConfigError as exc:
        print(f"No se pudo leer {env_file}: {exc}")
        return 1

    print("SIRAH setup")
    print("===========")
    print(f"Configuración: {env_file}")
    print("Solo la clave del LLM es obligatoria. Todo lo demás es opcional.\n")

    updates: dict[str, str] = {}

    # 1. LLM
    existing_key = current.get("LLM_API_KEY", "").strip()
    if existing_key:
        print(f"LLM_API_KEY ya configurada: {mask_secret(existing_key)}")
        if _ask_yes_no("¿Quieres cambiarla?", False):
            new_key = _ask_secret("Nueva LLM_API_KEY")
            if new_key:
                updates["LLM_API_KEY"] = new_key
    else:
        print("Necesitas una clave de LLM (por ejemplo, Groq Free).")
        new_key = _ask_secret("LLM_API_KEY")
        if new_key:
            updates["LLM_API_KEY"] = new_key
        else:
            print("Aviso: sin clave no habrá conversación. Puedes ejecutar setup otra vez.")

    base = current.get("LLM_BASE_URL", "").strip()
    if not base:
        updates["LLM_BASE_URL"] = "https://api.groq.com/openai/v1"
        updates["LLM_MODEL"] = "openai/gpt-oss-20b"
        base = updates["LLM_BASE_URL"]
        print("Proveedor por defecto: Groq Free (openai/gpt-oss-20b).")
    else:
        print(f"Proveedor actual: {base}")
    effective_key = updates.get("LLM_API_KEY", existing_key)

    # 2. Ojos
    print("\nOjos (ESP32)")
    existing_eyes = current.get("EYES_ADDRESS", "").strip()
    if existing_eyes:
        print(f"Ya configurados en {existing_eyes}")
        if _ask_yes_no("¿Quieres cambiar el puerto?", False):
            existing_eyes = ""
    if not existing_eyes:
        ports = detect_serial_ports()
        if ports:
            labels = [f"{path} — {description}" for path, description in ports]
            selected = _choose("Elige el puerto del ESP32", labels, 0)
            if selected:
                path = selected.split(" — ", 1)[0]
                updates["EYES_ADDRESS"] = f"serial://{path}"
        else:
            print("No encontré ningún puerto serial. Los ojos quedan apagados;")
            print("conecta el ESP32 y vuelve a ejecutar setup o edita EYES_ADDRESS.")
            updates["EYES_ADDRESS"] = ""

    # 3. Visión
    print("\nVisión (cámara)")
    if current.get("VISION_ENABLED", "").lower() in {"1", "true", "yes", "on"}:
        print("La visión ya está activada.")
    elif _ask_yes_no("¿Activar el seguimiento de caras al arrancar?", False):
        cameras = detect_cameras()
        if cameras:
            selected = _choose("Elige la cámara", cameras, 0)
            if selected:
                updates["VISION_ENABLED"] = "true"
                updates["VISION_CAMERA"] = selected
        else:
            print("No encontré /dev/video*. La visión queda desactivada.")

    # 4. Voz
    print("\nVoz (Groq + Piper)")
    is_groq = _is_groq(base)
    has_stt_key = bool(current.get("GROQ_API_KEY", "").strip()) or (is_groq and bool(effective_key))
    want_voice = _ask_yes_no("¿Preparar la voz ahora?", not has_stt_key)
    if want_voice and not has_stt_key:
        print("La voz usa Groq para transcribir; necesitas una clave de Groq.")
        groq_key = _ask_secret("GROQ_API_KEY (vacío = cancelar)")
        if groq_key:
            updates["GROQ_API_KEY"] = groq_key
            has_stt_key = True
        else:
            print("La voz queda pendiente.")
    if want_voice:
        if find_piper() is None:
            print("Piper no está instalado. Instala las dependencias con: uv sync --all-extras")
        else:
            print(f"Piper: {find_piper()}")
        tts_target = Path(
            current.get("TTS_MODEL", "models/voices/es_MX-claude-high.onnx")
        ).expanduser()
        if not tts_target.is_absolute():
            tts_target = PROJECT_ROOT / tts_target
        try:
            download_voice(tts_target.parent)
        except SetupError as exc:
            print(f"Aviso: {exc}")
            print("Puedes reintentar la descarga con `sirah setup`.")
        _print_alsa()
        print("Si el micrófono o el altavoz no son los predeterminados, ajusta")
        print("AUDIO_INPUT_DEVICE y AUDIO_OUTPUT_DEVICE en .env.")

    # 5. Persona
    print("\nPersona")
    settings_file = PROJECT_ROOT / "config" / "sirah.toml"
    try:
        created = ensure_settings_file()
    except OSError as exc:
        print(f"Aviso: no se pudo crear {settings_file}: {exc}")
    else:
        if created is not None:
            print(f"Configuración creada en {created}.")
        elif settings_file.exists():
            print(f"Ya existe {settings_file}.")
        else:
            print("Aviso: falta config/sirah.toml.example; se usan valores por defecto.")

    # 6. Escribir
    if updates:
        try:
            update_env_file(env_file, updates)
        except OSError as exc:
            print(f"No se pudo escribir {env_file}: {exc}")
            return 1
        print(f"\nConfiguración escrita en {env_file} (permisos 600).")
    else:
        print(f"\nNo había cambios que escribir en {env_file}.")

    calibration = _find_calibration()
    print(f"Calibración: {calibration} (no se modifica).")
    print("\nSiguiente paso: `sirah doctor`.")
    return 0
