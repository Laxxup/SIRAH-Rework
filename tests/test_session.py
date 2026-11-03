from __future__ import annotations

from pathlib import Path

from sirah.adapters.history_file import HistoryFile, history_path
from sirah.config import DEFAULT_PERSONA, load_config
from sirah.core.persona import Persona
from sirah.session import build_agent


def _config_and_persona(tmp_path: Path) -> tuple:
    data_dir = tmp_path / "data"
    config = load_config(
        env_file=tmp_path / "missing.env",
        environ={"XDG_DATA_HOME": str(data_dir), "LLM_API_KEY": "key"},
    )
    persona = Persona(
        path=DEFAULT_PERSONA,
        name="SIRAH",
        personality="Serena.",
        first_mes="",
        warnings=(),
    )
    return config, persona


def _seed(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def test_orphan_users_are_merged_on_load(tmp_path: Path) -> None:
    config, persona = _config_and_persona(tmp_path)
    history = HistoryFile(history_path(config.data_dir, persona.path))
    _seed(
        history.path,
        [
            '{"role":"user","text":"huérfano"}',
            '{"role":"user","text":"segundo"}',
            '{"role":"assistant","text":"vale"}',
        ],
    )

    agent, _ = build_agent(config, persona, identity="card", language="es")

    assert [(m.role, m.content) for m in agent.memory.messages] == [
        ("user", "huérfano\nsegundo"),
        ("assistant", "vale"),
    ]


def test_multiple_orphans_are_merged_on_load(tmp_path: Path) -> None:
    config, persona = _config_and_persona(tmp_path)
    history = HistoryFile(history_path(config.data_dir, persona.path))
    _seed(
        history.path,
        [
            '{"role":"user","text":"a"}',
            '{"role":"user","text":"b"}',
            '{"role":"user","text":"c"}',
            '{"role":"assistant","text":"d"}',
        ],
    )

    agent, _ = build_agent(config, persona, identity="card", language="es")

    assert [(m.role, m.content) for m in agent.memory.messages] == [
        ("user", "a\nb\nc"),
        ("assistant", "d"),
    ]


def test_trailing_orphanSurvives_alone(tmp_path: Path) -> None:
    config, persona = _config_and_persona(tmp_path)
    history = HistoryFile(history_path(config.data_dir, persona.path))
    _seed(history.path, ['{"role":"user","text":"solo"}'])

    agent, _ = build_agent(config, persona, identity="card", language="es")

    assert [(m.role, m.content) for m in agent.memory.messages] == [("user", "solo")]
