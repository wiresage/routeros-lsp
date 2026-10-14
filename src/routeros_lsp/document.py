"""A text document, and the conversion between Python string offsets and LSP positions.

The analysis works on Python string offsets (code points). LSP positions are a line and a column counted in UTF-16 code units,
so a character outside the Basic Multilingual Plane counts as two columns. Line breaks are LF, CR LF or CR.
"""

from __future__ import annotations

import bisect
import re
from typing import Any

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _utf16_length(text: str) -> int:
    if text.isascii():
        return len(text)
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


class Document:
    def __init__(self, uri: str, text: str, version: int = 0, language_id: str = "routeros") -> None:
        self.uri = uri
        self.language_id = language_id
        self.version = version
        #: Counts changes to the text, so that results computed from it can be reused until it changes.
        self.revision = 0
        self._text = text
        self._starts: list[int] | None = None

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value
        self._starts = None
        self.revision += 1

    def line_starts(self) -> list[int]:
        """Offsets at which each line starts."""
        if self._starts is None:
            self._starts = [0, *(m.end() for m in _LINE_BREAK.finditer(self._text))]
        return self._starts

    def _line_end(self, line: int) -> int:
        """Offset of the end of the line's text, before its line break."""
        starts = self.line_starts()
        if line + 1 < len(starts):
            end = starts[line + 1]
            while end > starts[line] and self._text[end - 1] in "\r\n":
                end -= 1
            return end
        return len(self._text)

    def line_count(self) -> int:
        return len(self.line_starts())

    def position_at(self, offset: int) -> dict[str, int]:
        """The LSP position of an offset, clamped to the text."""
        offset = max(0, min(offset, len(self._text)))
        starts = self.line_starts()
        line = bisect.bisect_right(starts, offset) - 1
        return {"line": line, "character": _utf16_length(self._text[starts[line] : offset])}

    def offset_at(self, position: dict[str, int]) -> int:
        """The offset of an LSP position. A column past the end of a line means the end of the line."""
        starts = self.line_starts()
        line = position["line"]
        if line < 0:
            return 0
        if line >= len(starts):
            return len(self._text)
        start, end = starts[line], self._line_end(line)
        remaining = max(0, position["character"])
        segment = self._text[start:end]
        if segment.isascii():
            return start + min(remaining, len(segment))
        offset = start
        for ch in segment:
            width = 2 if ord(ch) > 0xFFFF else 1
            if remaining < width:
                break
            remaining -= width
            offset += 1
        return offset

    def range_at(self, start: int, end: int) -> dict[str, Any]:
        return {"start": self.position_at(start), "end": self.position_at(end)}

    def apply_change(self, change: dict[str, Any]) -> None:
        """Applies one ``TextDocumentContentChangeEvent``: a replacement of a range, or of the whole text."""
        rng = change.get("range")
        if rng is None:
            self.text = change["text"]
            return
        start = self.offset_at(rng["start"])
        end = self.offset_at(rng["end"])
        if end < start:
            start, end = end, start
        self.text = self._text[:start] + change["text"] + self._text[end:]
