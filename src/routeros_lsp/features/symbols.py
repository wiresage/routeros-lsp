"""The outline of a script: functions, variables and the menu path headers that divide an export into sections."""

from __future__ import annotations

from typing import Any

from ..document import Document
from ..syntax.ast import Brace, Named, Script, Statement, StringLit, Word

NAMESPACE = 3
FUNCTION = 12
VARIABLE = 13


def _name_of(element: object) -> tuple[str, int, int] | None:
    """A word or a quoted string used as a name."""
    if isinstance(element, Word):
        return element.text, element.start, element.end
    if isinstance(element, StringLit) and element.closed:
        return element.value, element.start, element.end
    return None


def _is_menu_header(statement: Statement) -> bool:
    """Whether the statement is only a menu path such as ``/ip firewall filter``, the header of a section in an export."""
    return statement.prefix == "/" and bool(statement.elements) and all(isinstance(e, Word) for e in statement.elements)


def document_symbols(document: Document, script: Script) -> list[dict[str, Any]]:
    """Function definitions (``:global name do={ ... }``), variables declared with ``:global`` or ``:local``, and section headers."""

    def from_statements(statements: list[Statement], depth: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        section: dict[str, Any] | None = None

        def close_section(until: int) -> None:
            nonlocal section
            if section is None:
                return
            symbol = section["symbol"]
            symbol["range"] = {"start": symbol["range"]["start"], "end": document.position_at(until)}
            count = section["commands"]
            symbol["detail"] = f"{count} {'command' if count == 1 else 'commands'}"
            section = None

        for statement in statements:
            if depth == 0 and _is_menu_header(statement):
                close_section(statement.start)
                path = " ".join(e.text for e in statement.elements if isinstance(e, Word))
                symbol: dict[str, Any] = {
                    "name": f"/{path}",
                    "kind": NAMESPACE,
                    "range": document.range_at(statement.start, statement.end),
                    "selectionRange": document.range_at(statement.start, statement.end),
                }
                out.append(symbol)
                section = {"symbol": symbol, "commands": 0}
                continue
            if section is not None:
                section["commands"] += 1

            head = statement.elements[0] if statement.elements else None
            if not isinstance(head, Word) or head.text not in ("global", "local"):
                continue
            name = _name_of(statement.elements[1]) if len(statement.elements) > 1 else None
            if name is None:
                continue

            body = next(
                (e for e in statement.elements[2:] if isinstance(e, Named) and isinstance(e.name, Word) and e.name.text == "do"),
                None,
            )
            block = body.value if body is not None and isinstance(body.value, Brace) else None
            item: dict[str, Any] = {
                "name": name[0],
                "kind": FUNCTION if block is not None else VARIABLE,
                "detail": head.text,
                "range": document.range_at(statement.start, statement.end),
                "selectionRange": document.range_at(name[1], name[2]),
            }
            if block is not None:
                children = from_statements(block.body, depth + 1)
                if children:
                    item["children"] = children
            out.append(item)
        if section is not None:
            close_section(statements[-1].end if statements else script.end)
        return out

    return from_statements(script.statements, 0)
