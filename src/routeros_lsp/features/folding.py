"""Folding ranges: brackets, commands continued with a backslash, multi-line strings and runs of comment lines."""

from __future__ import annotations

from typing import Any

from ..document import Document
from ..syntax.ast import Script
from ..syntax.walk import visit

_BRACKETS = ("brace", "subst", "group")


def folding_ranges(document: Document, script: Script) -> list[dict[str, Any]]:
    """The closing line stays visible when the bracket sits alone on its line."""
    text = document.text
    ranges: dict[int, dict[str, Any]] = {}

    def add(start: int, end: int, kind: str | None = None, keep_last_line: bool = False) -> None:
        start_line = document.position_at(start)["line"]
        end_line = document.position_at(end)["line"]
        if keep_last_line:
            end_line -= 1
        if end_line <= start_line:
            return
        existing = ranges.get(start_line)
        if existing is None or existing["endLine"] < end_line:
            item: dict[str, Any] = {"startLine": start_line, "endLine": end_line}
            if kind:
                item["kind"] = kind
            ranges[start_line] = item

    def closes_on_own_line(end: int) -> bool:
        p = end - 2
        while p >= 0 and text[p] in " \t":
            p -= 1
        return p < 0 or text[p] in "\n\r"

    def callback(node: Any, _parent: Any) -> None:
        kind = node.kind
        if kind in _BRACKETS:
            add(node.start, node.end, None, node.closed and closes_on_own_line(node.end))
        elif kind == "statement":
            # A statement that ends in a bracket on its own line folds like that bracket does.
            last = node.elements[-1] if node.elements else None
            value = last.value if last is not None and last.kind == "named" else last
            bracket = value if value is not None and value.kind in _BRACKETS else None
            add(node.start, node.end, None, bracket is not None and bracket.closed and closes_on_own_line(node.end))
        elif kind == "string":
            add(node.start, node.end)

    visit(script, callback)

    # Consecutive comment lines fold together.
    run: list[int] | None = None
    for comment in script.comments:
        line = document.position_at(comment.start)["line"]
        if run is not None and document.position_at(run[1])["line"] + 1 == line:
            run[1] = comment.end
        else:
            if run is not None:
                add(run[0], run[1], "comment")
            run = [comment.start, comment.end]
    if run is not None:
        add(run[0], run[1], "comment")

    return [ranges[line] for line in sorted(ranges)]
