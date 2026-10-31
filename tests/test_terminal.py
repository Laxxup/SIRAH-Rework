from __future__ import annotations

import asyncio
import os
import pty
import select
import signal
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from sirah.adapters.history_file import HistoryFile, history_path
from sirah.adapters.llm import LLMClient, LLMError
from sirah.config import Config, load_config
from sirah.core.memory import Message
from sirah.core.persona import Persona
from sirah.terminal import run_terminal
from tests.fake_llm import FakeLLM, FakeResponse


def _config(tmp_path: Path, persona_path: Path, **env: str) -> Config:
    values = {
        "LLM_API_KEY": "clave",
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "SIRAH_PERSONA": str(persona_path),
        **env,
    }
    return load_config(env_file=tmp_path / "missing.env", environ=values)


def _persona(
    name: str = "SIRAH",
    first_mes: str = "",
    warnings: tuple[str, ...] = (),
) -> Persona:
    return Persona(
        path=Path(f"/tmp/{name.lower()}.json"),
        name=name,
        personality="Serena.",
        first_mes=first_mes,
        warnings=warnings,
    )


class ScriptedLLM:
    def __init__(self, script: list[list[str] | Exception]) -> None:
        self.script = list(script)
        self.calls: list[list[Message]] = []

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        for chunk in item:
            yield chunk


def _reader(lines: list[str]):
    async def read(prompt: str) -> str:
        if not lines:
            raise EOFError
        return lines.pop(0)

    return read


def _run(
    tmp_path: Path,
    persona: Persona,
    llm: ScriptedLLM,
    lines: list[str],
    *,
    identity: str = "card",
    language: str = "es",
    **env: str,
) -> str:
    config = _config(tmp_path, persona.path, **env)
    output: list[str] = []
    result = asyncio.run(
        run_terminal(
            config,
            persona,
            llm=llm,
            identity=identity,
            language=language,
            read_line=_reader(lines),
            write=output.append,
        )
    )
    assert result == 0
    return "".join(output)


def test_chat_turn_streams_and_is_persisted(tmp_path: Path) -> None:
    persona = _persona(first_mes="Hola, soy SIRAH.")
    llm = ScriptedLLM([["Hola, soy SIRAH."], ["Buenas ", "tardes."]])
    output = _run(tmp_path, persona, llm, ["hola", "/salir"])

    assert "Hola, soy SIRAH." in output
    assert "SIRAH> Buenas tardes." in output
    assert "{{" not in output

    history = HistoryFile(history_path(tmp_path / "data" / "sirah", persona.path))
    assert [(item.role, item.content) for item in history.load(10)] == [
        ("user", "hola"),
        ("assistant", "Buenas tardes."),
    ]


def test_trailing_space_is_not_written(tmp_path: Path) -> None:
    output = _run(tmp_path, _persona(), ScriptedLLM([["Vale. "]]), ["hola", "/salir"])
    assert "SIRAH> Vale.\n" in output
    assert "Vale. \n" not in output


def test_empty_response_is_retried_before_the_warning(tmp_path: Path) -> None:
    with FakeLLM([FakeResponse(), FakeResponse(["Vale."])]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        output = _run(tmp_path, _persona(), llm, ["hola", "/salir"])

    assert "SIRAH> Vale." in output
    assert "[AVISO]" not in output
    assert len(server.requests) == 2


def test_two_empty_responses_warn_and_next_turn_works(tmp_path: Path) -> None:
    with FakeLLM([FakeResponse(), FakeResponse(), FakeResponse(["Vale."])]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        output = _run(tmp_path, _persona(), llm, ["hola", "otra vez", "/salir"])

    assert "[AVISO]" in output
    assert "LLM_MAX_TOKENS" in output
    assert "SIRAH> Vale." in output
    assert len(server.requests) == 3


def test_length_finish_shows_a_token_warning(tmp_path: Path) -> None:
    response = FakeResponse(
        ["Hola"],
        finish_reason="length",
        usage={"completion_tokens": 1024},
    )
    with FakeLLM([response]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        output = _run(tmp_path, _persona(), llm, ["hola", "/salir"])

    assert "SIRAH> Hola" in output
    assert "[AVISO]" in output
    assert "LLM_MAX_TOKENS" in output


def test_length_finish_shows_a_token_warning_through_real_wiring(tmp_path: Path) -> None:
    response = FakeResponse(
        ["Hola"],
        finish_reason="length",
        usage={"completion_tokens": 1024},
    )
    with FakeLLM([response]) as server:
        config = _config(
            tmp_path,
            Path("/tmp/sirah.json"),
            LLM_BASE_URL=server.base_url,
            LLM_MODEL="modelo",
        )
        output: list[str] = []
        result = asyncio.run(
            run_terminal(
                config,
                _persona(),
                read_line=_reader(["hola", "/salir"]),
                write=output.append,
            )
        )

    text = "".join(output)
    assert result == 0
    assert "SIRAH> Hola" in text
    assert "límite de tokens" in text


def test_user_name_reaches_the_prompt(tmp_path: Path) -> None:
    llm = ScriptedLLM([["Vale."]])
    _run(tmp_path, _persona(), llm, ["hola", "/salir"], USER_NAME="Luis")

    assert "Nombre del usuario: Luis." in llm.calls[0][0].content


def test_markdown_is_cleaned_before_history(tmp_path: Path) -> None:
    persona = _persona()
    output = _run(
        tmp_path,
        persona,
        ScriptedLLM([["Hola **mundo**  \n"]]),
        ["hola", "/salir"],
    )

    assert "**" not in output
    history = HistoryFile(history_path(tmp_path / "data" / "sirah", persona.path))
    assert [(item.role, item.content) for item in history.load(10)] == [
        ("user", "hola"),
        ("assistant", "Hola mundo"),
    ]


def test_llm_error_keeps_the_chat_open(tmp_path: Path) -> None:
    persona = _persona()
    llm = ScriptedLLM([LLMError("sin conexión"), ["Vale."]])
    output = _run(tmp_path, persona, llm, ["hola", "otra vez", "/salir"])

    assert "[FALLA] sin conexión" in output
    assert "SIRAH> Vale." in output

    history = HistoryFile(history_path(tmp_path / "data" / "sirah", persona.path))
    assert [(item.role, item.content) for item in history.load(10)] == [
        ("user", "otra vez"),
        ("assistant", "Vale."),
    ]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (FakeResponse(status=401), "LLM_API_KEY"),
        (FakeResponse(status=429, headers={"Retry-After": "0"}), "limitando"),
        (FakeResponse(status=503), "HTTP 503"),
        (FakeResponse(body="<html>esto no es SSE</html>"), "respuesta inesperada"),
    ],
)
def test_each_llm_failure_keeps_the_chat_open(
    tmp_path: Path, failure: FakeResponse, message: str
) -> None:
    with FakeLLM([failure, FakeResponse(["Vale."])]) as server:
        llm = LLMClient("clave", server.base_url, "modelo", retries=0)
        output = _run(tmp_path, _persona(), llm, ["hola", "otra vez", "/salir"])

    assert "[FALLA]" in output
    assert message in output
    assert "SIRAH> Vale." in output


def test_eof_and_blank_lines_exit_cleanly(tmp_path: Path) -> None:
    output = _run(tmp_path, _persona(), ScriptedLLM([]), ["", ""])
    assert "Escribe /salir para terminar" in output
    assert "Hola, soy SIRAH." in output


def test_unknown_command_does_not_reach_the_llm(tmp_path: Path) -> None:
    llm = ScriptedLLM([])
    output = _run(tmp_path, _persona(), llm, ["/otra", "/salir"])
    assert "Comando no reconocido" in output
    assert llm.calls == []


def test_empty_response_shows_a_warning_and_is_not_stored(tmp_path: Path) -> None:
    persona = _persona()
    output = _run(tmp_path, persona, ScriptedLLM([[], []]), ["hola", "/salir"])
    assert "[AVISO]" in output

    history = HistoryFile(history_path(tmp_path / "data" / "sirah", persona.path))
    assert history.load(10) == []


def test_history_is_loaded_on_the_next_run(tmp_path: Path) -> None:
    persona = _persona()
    _run(tmp_path, persona, ScriptedLLM([["uno"]]), ["hola", "/salir"])

    second_llm = ScriptedLLM([["dos"]])
    _run(tmp_path, persona, second_llm, ["sigue", "/salir"])

    messages = second_llm.calls[0]
    assert [message.role for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1].content == "hola"
    assert messages[2].content == "uno"
    assert messages[3].content == "sigue"


def test_disabled_persistence_creates_no_history(tmp_path: Path) -> None:
    persona = _persona()
    _run(
        tmp_path,
        persona,
        ScriptedLLM([["uno"]]),
        ["hola", "/salir"],
        MEMORY_PERSIST="false",
    )
    history = history_path(tmp_path / "data" / "sirah", persona.path)
    assert not history.exists()


def test_strict_robot_mode_is_announced_and_card_mode_is_default(tmp_path: Path) -> None:
    persona = _persona(
        first_mes="Hola, soy SIRAH.",
        warnings=("La tarjeta es muy larga.",),
    )
    llm = ScriptedLLM([["Hola."]])
    output = _run(
        tmp_path,
        persona,
        llm,
        ["/salir"],
        identity="robot",
        language="en",
    )

    assert output.count("Modo robot estricto") == 1
    assert "Modo personaje" not in output
    assert output.count("La tarjeta es muy larga.") == 1
    assert "[AVISO] La tarjeta es muy larga." in output
    assert "Modo de identidad: robot." in llm.calls[0][0].content
    assert "inglés (en)" in llm.calls[0][0].content


def test_card_mode_does_not_print_a_mode_banner(tmp_path: Path) -> None:
    llm = ScriptedLLM([["Hola."]])
    output = _run(tmp_path, _persona(first_mes="Hola."), llm, ["/salir"])

    assert "Modo personaje" not in output
    assert "Modo robot estricto" not in output
    assert "Modo de identidad: card." in llm.calls[0][0].content


def test_default_history_is_migrated_on_start(tmp_path: Path) -> None:
    history_dir = tmp_path / "data" / "sirah" / "history"
    history_dir.mkdir(parents=True)
    old = history_dir / "default.jsonl"
    old.write_text('{"role":"user","text":"antes"}\n', encoding="utf-8")

    persona = _persona()
    _run(tmp_path, persona, ScriptedLLM([["uno"]]), ["hola", "/salir"])

    assert not old.exists()
    assert (history_dir / "sirah.jsonl.bak").exists()
    history = HistoryFile(history_dir / "sirah.jsonl")
    assert [(item.role, item.content) for item in history.load(10)] == [
        ("user", "antes"),
        ("user", "hola"),
        ("assistant", "uno"),
    ]


def test_greeting_failure_uses_the_fallback(tmp_path: Path) -> None:
    persona = _persona(first_mes="Hola, soy SIRAH.")
    llm = ScriptedLLM([LLMError("sin red"), ["Vale."]])
    output = _run(tmp_path, persona, llm, ["hola", "/salir"])

    assert "Hola, soy SIRAH." in output
    assert "SIRAH> Vale." in output


def test_sigint_exits_promptly(tmp_path: Path) -> None:
    with FakeLLM([FakeResponse(["Hola, soy SIRAH."])]) as server:
        master, slave = pty.openpty()
        env = dict(os.environ)
        env.update(
            {
                "SIRAH_ENV_FILE": str(tmp_path / "missing.env"),
                "XDG_DATA_HOME": str(tmp_path / "data"),
                "LLM_API_KEY": "prueba",
                "LLM_BASE_URL": server.base_url,
                "LLM_MODEL": "modelo",
                "LLM_TIMEOUT_S": "5",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "sirah"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            start_new_session=True,
        )
        os.close(slave)
        output = b""
        try:
            deadline = time.monotonic() + 5
            while b"t\xc3\xba> " not in output and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    chunk = os.read(master, 4096)
                    if not chunk:
                        break
                    output += chunk
            assert b"Hola, soy SIRAH." in output

            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=3) == 130
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
