"""Limpieza de Markdown residual sobre el stream, sin guardar toda la respuesta."""

from __future__ import annotations

_MARKDOWN = "`"
_BULLETS = "-+•"


class PlainTextCleaner:
    """Quita énfasis, viñetas, encabezados y espacios sobrantes mientras llega el texto."""

    def __init__(self) -> None:
        self._line_open = True
        self._maybe_bullet: str | None = None
        self._spaces = ""
        self._last_newline = False
        self._stars = 0
        self._before_stars = ""
        self._last_seen = ""
        self._dots = 0

    @staticmethod
    def _needs_gap(before: str, after: str) -> bool:
        """Repone el espacio solo cuando se quitó un marcador de énfasis."""
        return bool(before) and before in ".!?…" and after not in " \t\n"

    def _flush_dots(self, out: list[str]) -> None:
        if not self._dots:
            return
        # Dos puntos seguidos son casi siempre un resto de Markdown; los tres
        # puntos suspensivos se conservan.
        out.append("..." if self._dots > 2 else ".")
        self._dots = 0

    def feed(self, text: str) -> str:
        out: list[str] = []
        for char in text:
            if char == "\r":
                char = "\n"
            if char == "*":
                self._flush_dots(out)
                if not self._stars:
                    self._before_stars = self._last_seen
                self._stars += 1
                continue
            if self._stars:
                # Multiplicación pegada (3*4) o con espacios a ambos lados (3 * 4);
                # el resto es énfasis. El espacio previo va en _spaces y hay que
                # volcarlo antes de emitir el '*'.
                multiplied = self._before_stars.isdigit() and char.isdigit()
                spaced = self._before_stars in " \t" and char in " \t"
                if multiplied or spaced:
                    if spaced and self._spaces:
                        out.append(self._spaces)
                        self._spaces = ""
                    out.append("*" * self._stars)
                elif self._needs_gap(self._before_stars, char):
                    out.append(" ")
                self._stars = 0
            if char == ".":
                self._dots += 1
                self._last_seen = "."
                continue
            if self._dots:
                self._flush_dots(out)
                self._line_open = False
            self._last_seen = char
            if char == "\n":
                self._spaces = ""
                self._maybe_bullet = None
                self._line_open = True
                if not self._last_newline:
                    out.append("\n")
                    self._last_newline = True
                continue

            if self._line_open:
                if self._maybe_bullet is not None:
                    if char in " \t":
                        self._maybe_bullet = None
                        continue
                    out.append(self._maybe_bullet)
                    self._maybe_bullet = None
                    self._line_open = False
                    self._last_newline = False
                else:
                    if char in " \t":
                        continue
                    if char in _MARKDOWN or char == "#":
                        continue
                    if char in _BULLETS:
                        self._maybe_bullet = char
                        continue
                    self._line_open = False
                    self._last_newline = False
                    out.append(char)
                    continue

            if char in _MARKDOWN:
                continue
            if char in " \t":
                self._spaces += char
                continue
            if self._spaces:
                out.append(self._spaces)
                self._spaces = ""
            self._last_newline = False
            out.append(char)

        return "".join(out)

    def finish(self) -> str:
        self._spaces = ""
        self._stars = 0
        out: list[str] = []
        self._flush_dots(out)
        if self._maybe_bullet is not None:
            out.append(self._maybe_bullet)
            self._maybe_bullet = None
        return "".join(out)
