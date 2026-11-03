"""Chat por texto en la terminal."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Awaitable, Callable

from sirah.adapters.llm import LLMClient, LLMError
from sirah.config import Config
from sirah.core.actions import Action
from sirah.core.persona import Persona
from sirah.session import (
    _stdout,
    _token_warning,
    build_agent,
    opening_greeting,
    record_assistant_turn,
    record_opening_greeting,
    record_user_turn,
)

logger = logging.getLogger("sirah.terminal")


async def _read_line(prompt: str) -> str:
    """Lee una línea sin bloquear el cierre de asyncio.

    `asyncio.to_thread(input)` usa el executor por defecto y `asyncio.run` espera
    a que termine al salir, así que Ctrl-C se quedaba colgado hasta pulsar Enter.
    Un hilo daemon propio no bloquea ese cierre.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    def deliver(setter: Callable[[object], None], value: object) -> None:
        if not future.done():
            setter(value)

    def worker() -> None:
        try:
            line = input(prompt)
        except (Exception, KeyboardInterrupt) as exc:
            callback = (deliver, future.set_exception, exc)
        else:
            callback = (deliver, future.set_result, line)
        with contextlib.suppress(RuntimeError):  # el loop ya se cerró (Ctrl-C)
            loop.call_soon_threadsafe(*callback)

    threading.Thread(target=worker, name="sirah-input", daemon=True).start()
    return await future


def _log_actions(actions: tuple[Action, ...]) -> None:
    logger.debug("Acciones ignoradas (ojos en el hito 2): %s", actions)


async def run_terminal(
    config: Config,
    persona: Persona,
    *,
    llm: LLMClient | None = None,
    identity: str = "card",
    language: str = "es",
    read_line: Callable[[str], Awaitable[str]] | None = None,
    write: Callable[[str], None] | None = None,
) -> int:
    read_line = read_line or _read_line
    write = write or _stdout
    agent, history = build_agent(
        config,
        persona,
        identity=identity,
        language=language,
        llm=llm,
    )

    write(f"{persona.display_name} — chat por texto. Escribe /salir para terminar.\n")
    if identity == "robot":
        write("Modo robot estricto\n")
    for warning in persona.warnings:
        write(f"[AVISO] {warning}\n")
    if config.eyes_address:
        write("Aviso: los ojos se activan en el hito 2; ahora solo hay texto.\n")
    if config.vision_enabled:
        write("Aviso: la visión se activa en el hito 3; ahora solo hay texto.\n")
    write("\n")

    memory = getattr(agent, "memory", None)
    if getattr(memory, "messages", ()):
        greeting = ""
    else:
        greeting = await opening_greeting(persona)
        write(f"{greeting}\n\n")
    record_opening_greeting(agent, history, greeting)

    while True:
        try:
            line = await read_line("tú> ")
        except EOFError:
            write("\n")
            break
        except KeyboardInterrupt:
            write("\n")
            break

        text = line.strip()
        if not text:
            continue
        if text.lower() in {"/salir", "/exit"}:
            write("Hasta luego.\n")
            break
        if text.startswith("/"):
            write("Comando no reconocido. Usa /salir para terminar.\n")
            continue

        # Persistimos el turno del usuario antes de llamar al LLM: si el
        # proceso muere a mitad de respuesta, el disco conserva la pregunta.
        # El turno del asistente se añade solo tras una respuesta con texto.
        record_user_turn(history, text)

        write(f"{persona.display_name}> ")
        collected_parts: list[str] = []
        pending = ""
        try:
            async for chunk in agent.respond(text, on_actions=_log_actions):
                collected_parts.append(chunk)
                pending += chunk
                visible = pending.rstrip()
                if visible:
                    write(visible)
                    pending = pending[len(visible) :]
        except LLMError as exc:
            write(f"\n[FALLA] {exc}\n")
            continue
        except Exception:
            logger.exception("Fallo inesperado durante el turno")
            write("\n[FALLA] Algo falló al procesar el turno. Revisa el log.\n")
            continue

        # Últimos espacios o roturas de línea no se perdieron mientras fluía.
        if pending:
            write(pending)
            pending = ""

        # El LLM real lo construye build_agent: el parámetro `llm` suele ser None.
        truncated = getattr(agent.llm, "last_finish_reason", None) == "length"
        collected = "".join(collected_parts)
        if not collected:
            if truncated:
                write(f"\n{_token_warning(config.llm_max_tokens)}")
            else:
                write(
                    "\n[AVISO] El LLM no devolvió texto. Si se repite, "
                    f"revisa LLM_MAX_TOKENS ({config.llm_max_tokens}) y el log.\n"
                )
            continue

        write("\n")
        if truncated:
            write(_token_warning(config.llm_max_tokens))
        answer = collected.strip()
        if answer:
            record_assistant_turn(history, answer)

    return 0
