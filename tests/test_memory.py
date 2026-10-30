from __future__ import annotations

from sirah.core.memory import Memory, Message


def test_empty_memory() -> None:
    assert Memory(4).messages == ()


def test_add_turn_and_limit() -> None:
    memory = Memory(3)
    memory.add_turn("uno", "respuesta uno")
    memory.add_turn("dos", "respuesta dos")
    assert memory.messages == (
        Message("assistant", "respuesta uno"),
        Message("user", "dos"),
        Message("assistant", "respuesta dos"),
    )


def test_history_can_be_preloaded() -> None:
    memory = Memory(2)
    memory.add("user", "antes")
    memory.add("assistant", "respuesta anterior")
    memory.add_turn("ahora", "respuesta nueva")
    assert [item.content for item in memory.messages] == [
        "ahora",
        "respuesta nueva",
    ]
    assert memory.messages[0].role == "user"


def test_blank_messages_are_ignored() -> None:
    memory = Memory(4)
    memory.add_turn("  ", "  ")
    memory.add("assistant", "")
    assert memory.messages == ()
