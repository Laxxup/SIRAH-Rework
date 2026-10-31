"""Configuración de SIRAH: `.env`, valores por defecto y validación."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_PERSONA = PROJECT_ROOT / "config" / "persona" / "sirah.json"
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "sirah.toml"
DEFAULT_VISION_MODEL = PROJECT_ROOT / "models" / "face_detection_yunet_2023mar.onnx"
DEFAULT_TTS_MODEL = PROJECT_ROOT / "models" / "voices" / "es_MX-claude-high.onnx"

_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_INLINE_COMMENT = re.compile(r"\s+#")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_IDENTITIES = {"card", "personaje", "robot"}
_CANONICAL_IDENTITY = {"card": "card", "personaje": "card", "robot": "robot"}


def _canonical_identity(value: str) -> str:
    return _CANONICAL_IDENTITY.get(value.strip().lower(), "card")


class ConfigError(Exception):
    """Error de configuración con un mensaje que el usuario puede accionar."""

    def __init__(self, variable: str, value: object, expected: str) -> None:
        self.variable = variable
        self.value = value
        self.expected = expected
        if variable:
            message = f"{variable}: {expected}"
            if value is not None:
                message += f" (valor: {value!r})"
        else:
            message = expected
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PersonaSettings:
    """Contenido tolerante de `config/sirah.toml` (nunca lanza por datos malos)."""

    path: Path
    exists: bool
    active: Path
    language: str = "es"
    identity: str = "card"
    cards: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def load_persona_settings(
    path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> PersonaSettings:
    """Lee `sirah.toml`. Un archivo ausente o inválido usa valores por defecto."""
    env = os.environ if environ is None else environ
    if path is None:
        raw_path = env.get("SIRAH_SETTINGS_FILE")
        path = Path(raw_path).expanduser() if raw_path else DEFAULT_SETTINGS
    path = path.expanduser()

    defaults = {
        "path": path,
        "exists": path.exists(),
        "active": DEFAULT_PERSONA,
        "language": "es",
        "identity": "card",
        "cards": {},
        "warnings": (),
    }
    if not defaults["exists"]:
        return PersonaSettings(**defaults)

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return PersonaSettings(
            **{**defaults, "warnings": (f"No se pudo leer {path}: {exc.strerror}.",)}
        )
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return PersonaSettings(
            **{
                **defaults,
                "warnings": (f"No se pudo leer {path}; se usan valores por defecto.",),
            }
        )

    table = data.get("persona")
    if not isinstance(table, dict):
        return PersonaSettings(
            **{
                **defaults,
                "warnings": (f"{path}: falta la tabla [persona]; se usan valores por defecto.",),
            }
        )

    warnings: list[str] = []
    active = DEFAULT_PERSONA
    raw_active = table.get("active")
    if isinstance(raw_active, str) and raw_active.strip():
        active = Path(raw_active.strip()).expanduser()
        if not active.is_absolute():
            active = PROJECT_ROOT / active
        active = active.resolve()
    elif "active" in table:
        warnings.append(f"{path}: 'active' debe ser una ruta de texto; se usa sirah.json.")

    language = "es"
    raw_language = table.get("language")
    if isinstance(raw_language, str) and raw_language.strip():
        language = raw_language.strip().lower()
    elif "language" in table:
        warnings.append(f"{path}: 'language' debe ser texto; se usa 'es'.")

    identity = "card"
    raw_identity = table.get("identity")
    if isinstance(raw_identity, str) and raw_identity.strip().lower() in _IDENTITIES:
        identity = _canonical_identity(raw_identity)
    elif "identity" in table:
        warnings.append(f"{path}: 'identity' debe ser card (o personaje) o robot; se usa 'card'.")

    cards: dict[str, str] = {}
    raw_cards = table.get("cards")
    if raw_cards is not None and not isinstance(raw_cards, dict):
        warnings.append(f"{path}: 'cards' debe ser una tabla; se ignora.")
    elif isinstance(raw_cards, dict):
        for filename, card in raw_cards.items():
            override = card.get("identity") if isinstance(card, dict) else None
            if (
                isinstance(filename, str)
                and isinstance(override, str)
                and override.strip().lower() in _IDENTITIES
            ):
                cards[filename] = _canonical_identity(override)
            else:
                warnings.append(f"{path}: override de '{filename}' inválido; se ignora.")

    return PersonaSettings(
        path=path,
        exists=True,
        active=active,
        language=language,
        identity=identity,
        cards=cards,
        warnings=tuple(warnings),
    )


def identity_for(settings: PersonaSettings, card_path: Path) -> str:
    """El modo de identidad sale solo de `sirah.toml`, nunca de la tarjeta."""
    override = settings.cards.get(card_path.name)
    return override if override in _IDENTITIES else settings.identity


def active_card_path(config: Config, settings: PersonaSettings) -> Path:
    """`SIRAH_PERSONA`/`--persona` mandan sobre el `active` del TOML."""
    if config.persona_path_set:
        return config.persona_path
    return settings.active


@dataclass(frozen=True, slots=True)
class Config:
    env_file: Path
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout_s: float
    llm_max_tokens: int
    llm_temperature: float
    llm_reasoning_effort: str
    user_name: str
    persona_path: Path
    persona_path_set: bool
    persona_settings: PersonaSettings
    data_dir: Path
    memory_messages: int
    memory_persist: bool
    eyes_address: str
    eyes_baud: int
    eyes_heartbeat_ms: int
    eyes_target_hz: int
    vision_enabled: bool
    vision_camera: str
    vision_model: Path
    groq_api_key: str
    stt_model: str
    stt_language: str
    stt_timeout_s: float
    tts_model: Path
    audio_input_device: str
    audio_output_device: str
    audio_player_command: str
    audio_player_command_set: bool
    vad_aggressiveness: int
    vad_noise_calibration_ms: int
    vad_start_multiple: float
    vad_end_multiple: float
    vad_min_start_rms: int
    vad_min_end_rms: int
    vad_prebuffer_ms: int
    vad_start_frames: int
    vad_silence_ms: int
    vad_max_turn_ms: int
    panel_host: str
    panel_port: int
    panel_token: str
    log_level: str

    @property
    def vad_min_rms(self) -> int:
        """Alias histórico del mínimo de inicio adaptativo."""
        return self.vad_min_start_rms

    @property
    def eyes_device(self) -> Path | None:
        """Ruta del dispositivo serial, o None si los ojos están apagados."""
        if not self.eyes_address:
            return None
        return Path(urlparse(self.eyes_address).path)

    @property
    def stt_api_key(self) -> str:
        """Clave de Groq; si el LLM ya es Groq, se reutiliza su clave."""
        if self.groq_api_key:
            return self.groq_api_key
        host = urlparse(self.llm_base_url).hostname or ""
        if host == "groq.com" or host.endswith(".groq.com"):
            return self.llm_api_key
        return ""

    def require_llm_key(self) -> str:
        if not self.llm_api_key:
            raise ConfigError(
                "LLM_API_KEY",
                None,
                "es obligatoria para conversar; ejecuta `sirah setup` o edita .env",
            )
        return self.llm_api_key


def mask_secret(value: str) -> str:
    """Devuelve una clave enmascarada; nunca la clave completa."""
    if not value:
        return "(vacía)"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in {"'", '"'}:
        quote = raw[0]
        out: list[str] = []
        escaped = False
        for char in raw[1:]:
            if quote == '"' and escaped:
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(char, char))
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                return "".join(out)
            else:
                out.append(char)
        raise ConfigError("", raw, "hay una comilla sin cerrar en .env")
    match = _INLINE_COMMENT.search(raw)
    if match:
        raw = raw[: match.start()]
    return raw.strip()


def read_env_file(path: Path) -> dict[str, str]:
    """Lee un `.env` sencillo. No modifica el entorno del proceso."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("", None, f"no se pudo leer {path}: {exc.strerror}") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE.match(stripped)
        if not match:
            raise ConfigError(
                "",
                None,
                f"{path}:{number} no tiene el formato CLAVE=valor",
            )
        values[match.group(1)] = _parse_env_value(match.group(2))
    return values


def _text(values: Mapping[str, str], key: str, default: str = "") -> str:
    value = values.get(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def _optional_text(values: Mapping[str, str], key: str, default: str) -> str:
    """Como `_text`, pero una clave presente y vacía significa "sin valor"."""
    if key not in values:
        return default
    return values[key].strip()


def _integer(values: Mapping[str, str], key: str, default: int, low: int, high: int) -> int:
    raw = _text(values, key)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(key, raw, f"debe ser un entero entre {low} y {high}") from exc
    if not low <= value <= high:
        raise ConfigError(key, raw, f"debe estar entre {low} y {high}")
    return value


def _number(values: Mapping[str, str], key: str, default: float, low: float, high: float) -> float:
    raw = _text(values, key)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(key, raw, f"debe ser un número entre {low} y {high}") from exc
    if not low <= value <= high:
        raise ConfigError(key, raw, f"debe estar entre {low} y {high}")
    return value


def _boolean(values: Mapping[str, str], key: str, default: bool) -> bool:
    raw = _text(values, key)
    if not raw:
        return default
    lowered = raw.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ConfigError(key, raw, "debe ser true o false")


def _path(values: Mapping[str, str], key: str, default: Path) -> Path:
    raw = _text(values, key)
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _default_data_dir(values: Mapping[str, str]) -> Path:
    base = Path(values.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return (base / "sirah").expanduser()


def load_config(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Config:
    """Carga la configuración: entorno > `.env` > valores por defecto."""
    process_env = dict(os.environ if environ is None else environ)
    if env_file is None:
        raw_env = process_env.get("SIRAH_ENV_FILE")
        env_file = Path(raw_env).expanduser() if raw_env else DEFAULT_ENV_FILE
    env_file = env_file.expanduser().resolve()

    values = {**read_env_file(env_file), **process_env}
    settings = load_persona_settings(environ=values)

    eyes_address = _text(values, "EYES_ADDRESS")
    if eyes_address:
        parsed = urlparse(eyes_address)
        if parsed.scheme != "serial":
            raise ConfigError(
                "EYES_ADDRESS",
                eyes_address,
                "solo se admite el esquema serial:// por ahora",
            )
        if not parsed.path:
            raise ConfigError("EYES_ADDRESS", eyes_address, "falta la ruta del dispositivo")
        if not parsed.path.startswith("/"):
            raise ConfigError(
                "EYES_ADDRESS",
                eyes_address,
                "la ruta del dispositivo debe ser absoluta",
            )

    base_url = _text(values, "LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError("LLM_BASE_URL", base_url, "debe ser una URL http(s) válida")

    model = _text(values, "LLM_MODEL", "openai/gpt-oss-20b")
    if not model:
        raise ConfigError("LLM_MODEL", model, "no puede estar vacío")

    reasoning_effort = _optional_text(values, "LLM_REASONING_EFFORT", "low").lower()
    if reasoning_effort not in {"", "low", "medium", "high"}:
        raise ConfigError(
            "LLM_REASONING_EFFORT",
            reasoning_effort,
            "debe ser low, medium, high o vacío",
        )

    log_level = _text(values, "LOG_LEVEL", "INFO").upper()
    if log_level not in _LOG_LEVELS:
        raise ConfigError("LOG_LEVEL", log_level, "debe ser DEBUG, INFO, WARNING o ERROR")

    panel_host = _text(values, "PANEL_HOST", "127.0.0.1")
    panel_token = _text(values, "PANEL_TOKEN")
    if panel_host not in _LOOPBACK and len(panel_token) < 16:
        raise ConfigError(
            "PANEL_TOKEN",
            None,
            "se necesitan al menos 16 caracteres si el panel no escucha en localhost",
        )

    vad_prebuffer_ms = _integer(values, "VAD_PREBUFFER_MS", 300, 100, 1000)
    vad_start_frames = _integer(values, "VAD_START_FRAMES", 3, 1, 10)
    if vad_start_frames * 20 > vad_prebuffer_ms:
        raise ConfigError(
            "VAD_PREBUFFER_MS",
            vad_prebuffer_ms,
            f"debe cubrir VAD_START_FRAMES ({vad_start_frames * 20} ms)",
        )

    # VAD_MIN_RMS sigue valiendo como alias del mínimo de inicio.
    legacy_min = _text(values, "VAD_MIN_RMS")
    legacy = _integer(values, "VAD_MIN_RMS", 0, 0, 20000) if legacy_min else None
    default_start = legacy if legacy is not None else 1200
    # Con un .env antiguo (350) el fin baja para mantener inicio > fin.
    default_end = 600 if legacy is None or legacy > 600 else max(0, legacy // 2)
    vad_min_start_rms = _integer(values, "VAD_MIN_START_RMS", default_start, 0, 20000)
    vad_min_end_rms = _integer(values, "VAD_MIN_END_RMS", default_end, 0, 20000)
    if vad_min_start_rms <= vad_min_end_rms:
        raise ConfigError(
            "VAD_MIN_END_RMS",
            vad_min_end_rms,
            f"debe ser menor que VAD_MIN_START_RMS ({vad_min_start_rms})",
        )
    vad_start_multiple = _number(values, "VAD_START_MULTIPLE", 1.6, 1.01, 10)
    if vad_start_multiple <= 1:
        raise ConfigError("VAD_START_MULTIPLE", vad_start_multiple, "debe ser mayor que 1")
    vad_end_multiple = _number(values, "VAD_END_MULTIPLE", 1.2, 1.01, 10)
    if vad_end_multiple <= 1:
        raise ConfigError("VAD_END_MULTIPLE", vad_end_multiple, "debe ser mayor que 1")

    return Config(
        env_file=env_file,
        llm_api_key=_text(values, "LLM_API_KEY"),
        llm_base_url=base_url,
        llm_model=model,
        llm_timeout_s=_number(values, "LLM_TIMEOUT_S", 60.0, 5, 300),
        llm_max_tokens=_integer(values, "LLM_MAX_TOKENS", 1024, 32, 4096),
        llm_temperature=_number(values, "LLM_TEMPERATURE", 0.6, 0, 2),
        llm_reasoning_effort=reasoning_effort,
        user_name=_text(values, "USER_NAME"),
        persona_path=_path(values, "SIRAH_PERSONA", settings.active),
        persona_path_set=bool(_text(values, "SIRAH_PERSONA")),
        persona_settings=settings,
        data_dir=_path(values, "SIRAH_DATA_DIR", _default_data_dir(values)),
        memory_messages=_integer(values, "MEMORY_MESSAGES", 12, 2, 50),
        memory_persist=_boolean(values, "MEMORY_PERSIST", True),
        eyes_address=eyes_address,
        eyes_baud=_integer(values, "EYES_BAUD", 115200, 9600, 921600),
        eyes_heartbeat_ms=_integer(values, "EYES_HEARTBEAT_MS", 1000, 500, 2500),
        eyes_target_hz=_integer(values, "EYES_TARGET_HZ", 15, 5, 30),
        vision_enabled=_boolean(values, "VISION_ENABLED", False),
        vision_camera=_text(values, "VISION_CAMERA", "/dev/video0"),
        vision_model=_path(values, "VISION_MODEL", DEFAULT_VISION_MODEL),
        groq_api_key=_text(values, "GROQ_API_KEY"),
        stt_model=_text(values, "STT_MODEL", "whisper-large-v3-turbo"),
        stt_language=_text(values, "STT_LANGUAGE", "es"),
        stt_timeout_s=_number(values, "STT_TIMEOUT_S", 30.0, 5, 120),
        tts_model=_path(values, "TTS_MODEL", DEFAULT_TTS_MODEL),
        audio_input_device=_text(values, "AUDIO_INPUT_DEVICE"),
        audio_output_device=_text(values, "AUDIO_OUTPUT_DEVICE"),
        audio_player_command=_text(values, "AUDIO_PLAYER_COMMAND", "aplay"),
        audio_player_command_set=bool(_text(values, "AUDIO_PLAYER_COMMAND")),
        vad_aggressiveness=_integer(values, "VAD_AGGRESSIVENESS", 2, 0, 3),
        vad_noise_calibration_ms=_integer(values, "VAD_NOISE_CALIBRATION_MS", 500, 100, 3000),
        vad_start_multiple=vad_start_multiple,
        vad_end_multiple=vad_end_multiple,
        vad_min_start_rms=vad_min_start_rms,
        vad_min_end_rms=vad_min_end_rms,
        vad_prebuffer_ms=vad_prebuffer_ms,
        vad_start_frames=vad_start_frames,
        vad_silence_ms=_integer(values, "VAD_SILENCE_MS", 400, 200, 1500),
        vad_max_turn_ms=_integer(values, "VAD_MAX_TURN_MS", 10000, 2000, 30000),
        panel_host=panel_host,
        panel_port=_integer(values, "PANEL_PORT", 8765, 1024, 65535),
        panel_token=panel_token,
        log_level=log_level,
    )


def _format_env_value(value: str) -> str:
    if not value:
        return ""
    if re.search(r"[\s#\"']", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def update_env_file(path: Path, updates: Mapping[str, str]) -> None:
    """Actualiza o añade claves sin borrar comentarios ni otros valores."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    elif (PROJECT_ROOT / ".env.example").exists():
        lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# Configuración de SIRAH."]

    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        match = _ENV_LINE.match(line.strip())
        if match and match.group(1) in remaining:
            key = match.group(1)
            result.append(f"{key}={_format_env_value(remaining.pop(key))}")
        else:
            result.append(line)
    for key, value in remaining.items():
        result.append(f"{key}={_format_env_value(value)}")

    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(result) + "\n")
    # Un .tmp viejo conserva su modo: O_CREAT no lo cambia.
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
