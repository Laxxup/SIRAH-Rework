from __future__ import annotations

from sirah.core.text import PlainTextCleaner


def _clean(*chunks: str) -> str:
    cleaner = PlainTextCleaner()
    return "".join([cleaner.feed(chunk) for chunk in chunks] + [cleaner.finish()])


def test_removes_emphasis_and_backticks() -> None:
    assert _clean("Hola *mundo*, **esto** y `código`.") == "Hola mundo, esto y código."


def test_removes_bullets_and_headings() -> None:
    text = "- uno\n* dos\n+ tres\n• cuatro\n# Título\n"
    assert _clean(text) == "uno\ndos\ntres\ncuatro\nTítulo\n"


def test_removes_spaces_before_newline() -> None:
    assert _clean("Hola.  \nMundo.\t\n") == "Hola.\nMundo.\n"


def test_handles_markdown_split_between_chunks() -> None:
    assert _clean("**", "negrita", "**", " y *", "cursiva", "*") == "negrita y cursiva"


def test_streams_before_the_end() -> None:
    cleaner = PlainTextCleaner()
    assert cleaner.feed("Hola") == "Hola"
    assert cleaner.feed(" mundo") == " mundo"
    assert cleaner.finish() == ""


def test_drops_trailing_spaces_at_the_end() -> None:
    assert _clean("Hola   ") == "Hola"


def test_collapses_blank_lines() -> None:
    assert _clean("Hola.\n\n\nMundo.") == "Hola.\nMundo."


def test_keeps_dashes_inside_a_line() -> None:
    assert _clean("a-b") == "a-b"


def test_keeps_multiplication_asterisks() -> None:
    assert _clean("3*4") == "3*4"
    assert _clean("3*4 y 5*6") == "3*4 y 5*6"
    assert _clean("**negrita** y 3*4") == "negrita y 3*4"


def test_removes_emphasis_adjacent_to_words() -> None:
    assert _clean("hola*mundo*") == "holamundo"
    assert _clean("a*b") == "ab"


def test_chunk_splits_do_not_change_the_cleaned_text() -> None:
    text = (
        "Claro, podemos seguir conversando. **Ok.** ¿Hay algo en particular "
        "que te interese?\n- Uno\n- Dos.  \nEntiendo.. *bien* 3*4."
    )
    expected = _clean(text)

    for cut in range(len(text) + 1):
        assert _clean(text[:cut], text[cut:]) == expected

    assert _clean(*text) == expected


def test_repairs_a_missing_space_only_where_a_marker_was_removed() -> None:
    glued = "podemos seguir conversando.Ok.¿Hay algo en particular que te interese?"
    assert _clean(glued) == glued
    assert (
        _clean("podemos seguir conversando.**Ok.**¿Hay algo?")
        == "podemos seguir conversando. Ok. ¿Hay algo?"
    )


def test_does_not_rewrite_plain_punctuation() -> None:
    for text in (
        "3.14",
        "10.000",
        "v2.0",
        "ejemplo.com",
        "p. ej.",
        "a. m.",
        "etc.",
        "...",
        "¿...?",
        "¡...!",
    ):
        assert _clean(text) == text


def test_keeps_a_multiplication_with_spaces() -> None:
    assert _clean("3 * 4") == "3 * 4"
    assert _clean("3*4") == "3*4"


def test_collapses_a_double_period_but_keeps_an_ellipsis() -> None:
    assert _clean("Entiendo..") == "Entiendo."
    assert _clean("Entiendo...") == "Entiendo..."
