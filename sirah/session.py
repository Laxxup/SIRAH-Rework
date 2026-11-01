"""Piezas comunes del chat por texto y por voz."""

from __future__ import annotations

import sys

from sirah.adapters.history_file import HistoryFile, history_path, migrate_default_history
from sirah.adapters.llm import LLMClient
from sirah.config import Config
from sirah.core.agent import Agent
from sirah.core.memory import Memory
from sirah.core.persona import Persona

# Se mantiene la firma con agent/config para no romper terminales y voz.


def build_agent(
    config: Config,
    persona: Persona,
    *,
    identity: str = "card",
    language: str = "es",
    llm: LLMClient | None = None,
) -> tuple[Agent, HistoryFile | None]:
    if llm is None:
        llm = LLMClient(
            config.llm_api_key,
            config.llm_base_url,
            config.llm_model,
            timeout_s=config.llm_timeout_s,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
            reasoning_effort=config.llm_reasoning_effort,
        )

    memory = Memory(config.memory_messages)
    history: HistoryFile | None = None
    if config.memory_persist:
        if persona.path.name == "sirah.json":
            migrate_default_history(config.data_dir)
        history = HistoryFile(history_path(config.data_dir, persona.path))
        for message in history.load(config.memory_messages):
            memory.add(message.role, message.content)

    agent = Agent(
        persona,
        llm,
        memory,
        user_name=config.user_name,
        identity=identity,
        language=language,
    )
    return agent, history


async def opening_greeting(persona: Persona) -> str:
    first = persona.first_mes.strip()
    if first:
        if len(first) > 600:
            first = first[:600].rstrip()
        return first
    return f"Hola, soy {persona.display_name}. ¿De qué quieres hablar?"


def record_opening_greeting(agent: object, history: object, greeting: str) -> None:
    """Guarda el saludo inicial como primer turno assistant, sin llamar al LLM."""
    if not greeting or not greeting.strip():
        return
    memory = getattr(agent, "memory", None)
    if memory is None or memory.messages:
        return
    memory.add("assistant", greeting)
    append = getattr(history, "append", None)
    if append is not None:
        append("assistant", greeting)


def _stdout(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _token_warning(max_tokens: int) -> str:
    return (
        "[AVISO] La respuesta se cortó por el límite de tokens "
        f"(LLM_MAX_TOKENS={max_tokens}). "
        'Puedes pedir "continúa" o subir el valor en .env.\n'
    )
