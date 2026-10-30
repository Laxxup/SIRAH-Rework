"""Chat por texto en la terminal."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import threading
from collections.abc import Awaitable, Callable

from sirah.adapters.llm import LLMClient, LLMError
from sirah.config import Config
from sirah.core.actions import Action
from sirah.core.persona import Persona
from sirah.session import build_agent, opening_greeting

logger = logging.getLogger("sirah.terminal")


def _stdout(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


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
        except Exception as exc:
            callback = (deliver, future.set_exception, exc)
        else:
            callback = (deliver, future.set_result, line)
        with contextlib.suppress(RuntimeError):  # el loop ya se cerró (Ctrl-C)
            loop.call_soon_threadsafe(*callback)

    threading.Thread(target=worker, name="sirah-input", daemon=True).start()
    return await future


def _log_actions(actions: tuple[Action, ...]) -> None:
    logger.debug("Acciones ignoradas (ojos en el hito 2): %s", actions)


def _token_warning(config: Config) -> str:
    return (
        "[AVISO] La respuesta se cortó por el límite de tokens "
        f"(LLM_MAX_TOKENS={config.llm_max_tokens}). "
        'Puedes pedir "continúa" o subir el valor en .env.\n'
    )


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

    greeting = await opening_greeting(agent, persona, config)
    write(f"{greeting}\n\n")

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

        write(f"{persona.display_name}> ")
        pieces: list[str] = []
        pending = ""
        try:
            async for chunk in agent.respond(text, on_actions=_log_actions):
                pieces.append(chunk)
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

        # El LLM real lo construye build_agent: el parámetro `llm` suele ser None.
        truncated = getattr(agent.llm, "last_finish_reason", None) == "length"
        if not pieces:
            if truncated:
                write(f"\n{_token_warning(config)}")
            else:
                write(
                    "\n[AVISO] El LLM no devolvió texto. Si se repite, "
                    f"revisa LLM_MAX_TOKENS ({config.llm_max_tokens}) y el log.\n"
                )
            continue

        write("\n")
        if truncated:
            write(_token_warning(config))
        answer = "".join(pieces).strip()
        if answer and history is not None:
            history.append("user", text)
            history.append("assistant", answer)

    return 0
