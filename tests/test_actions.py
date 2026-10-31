from __future__ import annotations

import pytest

from sirah.core.actions import Action, ActionParser


def _parse(*chunks: str) -> tuple[str, tuple[Action, ...]]:
    parser = ActionParser()
    text = "".join(parser.feed(chunk) for chunk in chunks) + parser.finish()
    return text, parser.actions


def test_plain_text_is_unchanged() -> None:
    text, actions = _parse("Hola, ¿qué tal?")
    assert text == "Hola, ¿qué tal?"
    assert actions == ()


def test_known_actions_are_removed_from_text() -> None:
    text, actions = _parse("Hola {{look 0.3 -0.2}} mundo\n{{blink}}")
    assert text == "Hola  mundo\n"
    assert actions == (Action("look", 0.3, -0.2), Action("blink"))


def test_tag_split_across_chunks() -> None:
    text, actions = _parse("Hola {{lo", "ok 0.5 -0.5}} mundo")
    assert text == "Hola  mundo"
    assert actions == (Action("look", 0.5, -0.5),)


def test_center_and_tired() -> None:
    text, actions = _parse("{{center}}Vale.{{tired}}")
    assert text == "Vale."
    assert actions == (Action("center"), Action("tired"))


@pytest.mark.parametrize(
    "tag",
    [
        "{{look}}",
        "{{look 0.2}}",
        "{{look 1.1 0}}",
        "{{look -2 0}}",
        "{{look a b}}",
        "{{look nan 0}}",
        "{{center 1}}",
        "{{blink 1}}",
        "{{unknown}}",
        "{{nod}}",
    ],
)
def test_invalid_or_unknown_tags_are_discarded(tag: str) -> None:
    text, actions = _parse(f"Antes {tag} después")
    assert text == "Antes  después"
    assert actions == ()


def test_coordinates_on_the_limits_are_valid() -> None:
    _, actions = _parse("{{look -1 1}}")
    assert actions == (Action("look", -1.0, 1.0),)


def test_maximum_two_actions_and_one_eyelid_action() -> None:
    _, actions = _parse("{{look 0.1 0.1}}{{blink}}{{tired}}{{center}}")
    assert actions == (Action("look", 0.1, 0.1), Action("blink"))


def test_unclosed_tag_is_not_shown() -> None:
    text, actions = _parse("Hola {{blink")
    assert text == "Hola "
    assert actions == ()


def test_unclosed_loose_double_brace_is_shown() -> None:
    text, actions = _parse("En plantillas se usa {{ para abrir.")
    assert text == "En plantillas se usa {{ para abrir."
    assert actions == ()


def test_unclosed_truncated_action_tag_is_hidden() -> None:
    text, actions = _parse("Hola {{look 0.")
    assert text == "Hola "
    assert actions == ()


def test_single_brace_split_across_chunks_still_forms_a_tag() -> None:
    text, actions = _parse("Hola {", "{blink}} mundo")
    assert text == "Hola  mundo"
    assert actions == (Action("blink"),)


def test_single_brace_followed_by_normal_text_is_shown() -> None:
    text, actions = _parse("Hola {", "mundo")
    assert text == "Hola {mundo"
    assert actions == ()
