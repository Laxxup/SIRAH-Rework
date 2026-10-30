"""Tarjetas de personaje (Character Card v2/v3) como datos."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CARD_BYTES = 1_000_000
MAX_CARD_CHARS = 12_000
_SPECS = {"chara_card_v2", "chara_card_v3"}

_CHAR_MACRO = re.compile(r"\{\{\s*char\s*\}\}|<\s*bot\s*>", re.IGNORECASE)
_USER_MACRO = re.compile(r"\{\{\s*user\s*\}\}|<\s*user\s*>", re.IGNORECASE)
_EMPHASIS = re.compile(r"(?<![\w*])\*{1,2}([^*\n]+?)\*{1,2}(?![\w*])")

# Líneas que intentan anular el contrato fijo del código. No se descarta una
# línea solo por hablar de rol o por pedir el nombre del usuario.
_NULLIFY = (
    re.compile(r"\bno restrictions?\b", re.IGNORECASE),
    re.compile(r"\bwithout restrictions?\b", re.IGNORECASE),
    re.compile(r"\bsin restricciones?\b", re.IGNORECASE),
    re.compile(r"\bassume consent\b", re.IGNORECASE),
    re.compile(r"\basume consentimiento\b", re.IGNORECASE),
    re.compile(r"\bconsentimiento asumido\b", re.IGNORECASE),
    re.compile(r"\bexplicit content (?:is )?encouraged\b", re.IGNORECASE),
    re.compile(
        r"\bcontenido explícit[oa]\b.*"
        r"\b(?:permitid[oa]|obligatori[oa]|alentad[oa]|animad[oa]|sin límites)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bignore (?:all )?previous instructions\b", re.IGNORECASE),
    re.compile(r"\bignora (?:las )?instrucciones (?:anteriores|previas)\b", re.IGNORECASE),
    re.compile(r"\byou are not an? (?:ai|robot|human)\b", re.IGNORECASE),
    re.compile(r"\bno eres (?:una? )?(?:ia|ai|robot|humano)\b", re.IGNORECASE),
    re.compile(r"\b(?:max|maximum|token) (?:token )?limit\b", re.IGNORECASE),
    re.compile(r"\blímite de tokens\b", re.IGNORECASE),
    re.compile(r"\blimite de tokens\b", re.IGNORECASE),
    re.compile(r"\bdescrib(?:e|ir|a) (?:la |su )?(?:ropa|cuerpo)\b", re.IGNORECASE),
    re.compile(r"\bdescribe (?:clothing|body)\b", re.IGNORECASE),
)

_ENGLISH = re.compile(
    r"\b(?:the|and|you|your|with|this|that|have|will|are|is|of|for|not|from|they"
    r"|she|his|her|it|its|was|were|be|been|had|do|does|did|can|could|would"
    r"|should|who|what|when|where|why|how|my|we|our|us|an|at|on|in|to|but|or"
    r"|if|about)\b",
    re.IGNORECASE,
)
_SPANISH = re.compile(
    r"\b(?:el|la|los|las|de|que|y|en|un|una|es|por|para|con|no|tu|tus|usted|del|se)\b",
    re.IGNORECASE,
)
_FIELDS = ("description", "personality", "scenario", "mes_example", "nickname", "first_mes")


class PersonaError(Exception):
    """La tarjeta no se pudo cargar o no es válida."""


@dataclass(frozen=True, slots=True)
class Persona:
    path: Path
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    mes_example: str = ""
    nickname: str = ""
    first_mes: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        return self.name


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _card_data(parsed: object, path: Path) -> dict[str, object]:
    if not isinstance(parsed, dict):
        raise PersonaError(f"{path}: la tarjeta debe ser un objeto JSON")

    spec = parsed.get("spec")
    if spec is None:
        # Un chat exportado no es una tarjeta, aunque tenga "data" con mensajes.
        if parsed.get("type") == "risuChat":
            raise PersonaError(
                f"{path}: Este archivo es un chat exportado de RisuAI, no una tarjeta de "
                "personaje. Exporta el personaje en formato Character Card V2 (JSON)"
            )
        if "name" not in parsed:
            raise PersonaError(f"{path}: No parece una tarjeta de personaje (faltan spec y name)")
        # Formato antiguo: los campos están en la raíz.
        return parsed
    if not isinstance(spec, str) or spec not in _SPECS:
        raise PersonaError(
            f"{path}: spec {spec!r} no soportada; se aceptan chara_card_v2, chara_card_v3 "
            "o una tarjeta antigua sin spec"
        )
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise PersonaError(f"{path}: la tarjeta {spec} no tiene un objeto 'data'")
    return data


def _clean_text(text: str, char_name: str, user_name: str) -> tuple[str, int]:
    if not text:
        return "", 0
    text = _CHAR_MACRO.sub(char_name, text)
    text = _USER_MACRO.sub(user_name, text)

    kept: list[str] = []
    discarded = 0
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in _NULLIFY):
            discarded += 1
            continue
        kept.append(_EMPHASIS.sub(r"\1", line))
    return "\n".join(kept).strip(), discarded


def _looks_english(text: str) -> bool:
    english = len(_ENGLISH.findall(text))
    spanish = len(_SPANISH.findall(text))
    # Dos señales claras ya bastan para una ficha corta sin primer mensaje.
    return english >= 2 and english > spanish


def load_persona(path: Path, *, user_name: str = "") -> Persona:
    """Lee una tarjeta v2/v3 o una tarjeta antigua simple, sin tocarla."""
    path = path.expanduser()
    try:
        size = path.stat().st_size
        if size > MAX_CARD_BYTES:
            raise PersonaError(
                f"{path}: la tarjeta es demasiado grande ({size} bytes; máximo {MAX_CARD_BYTES})."
            )
        raw = path.read_bytes()
    except PersonaError:
        raise
    except OSError as exc:
        raise PersonaError(f"No se pudo leer la tarjeta {path}: {exc.strerror}") from exc

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PersonaError(f"{path}: la tarjeta no es UTF-8 válido") from exc
    if not text.strip():
        raise PersonaError(f"{path}: la tarjeta está vacía")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersonaError(
            f"{path}: JSON inválido en la línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
        ) from exc

    data = _card_data(parsed, path)
    name = _text(data, "name")
    if not name:
        raise PersonaError(f"{path}: la tarjeta no tiene un campo 'name' válido")

    char_name = _text(data, "nickname") or name
    resolved_user = user_name.strip() or "el usuario"
    cleaned: dict[str, str] = {}
    discarded = 0
    for field in _FIELDS:
        cleaned[field], removed = _clean_text(_text(data, field), char_name, resolved_user)
        discarded += removed

    warnings: list[str] = []
    if discarded:
        warnings.append(
            f"Se descartaron {discarded} línea(s) de la tarjeta que intentaban "
            "anular el contrato de SIRAH."
        )
    card_text = "\n".join(cleaned.values())
    if _looks_english(card_text):
        warnings.append(
            "La tarjeta parece estar en inglés; las respuestas podrían mezclar idiomas."
        )
    if len(card_text) > MAX_CARD_CHARS:
        warnings.append(
            f"La tarjeta es muy larga ({len(card_text)} caracteres; "
            f"más de {MAX_CARD_CHARS:,}). Puede consumir mucho contexto.".replace(",", ".")
        )
    if data.get("character_book"):
        warnings.append(
            "La tarjeta incluye character_book; SIRAH lo ignora (solo usa la ficha básica)."
        )

    return Persona(
        path=path,
        name=name,
        description=cleaned["description"],
        personality=cleaned["personality"],
        scenario=cleaned["scenario"],
        mes_example=cleaned["mes_example"],
        nickname=cleaned["nickname"],
        first_mes=cleaned["first_mes"],
        warnings=tuple(warnings),
    )
