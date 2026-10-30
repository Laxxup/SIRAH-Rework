"""Piezas comunes del chat por texto y por voz."""

from __future__ import annotations

import asyncio
import logging

from sirah.adapters.history_file import HistoryFile, history_path, migrate_default_history
from sirah.adapters.llm import LLMClient
from sirah.config import Config
from sirah.core.agent import Agent
from sirah.core.memory import Memory
from sirah.core.persona import Persona

logger = logging.getLogger("sirah.session")
GREETING_TIMEOUT_S = 8.0


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


async def opening_greeting(agent: Agent, persona: Persona, config: Config) -> str:
    try:
        greeting = await asyncio.wait_for(
            agent.greet(),
            timeout=min(GREETING_TIMEOUT_S, config.llm_timeout_s),
        )
    except Exception:
        logger.debug("No se pudo generar el saludo; se usa el de respaldo", exc_info=True)
        greeting = ""
    return greeting or f"Hola, soy {persona.display_name}. ¿De qué quieres hablar?"
