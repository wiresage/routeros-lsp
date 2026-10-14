"""Completion: menus, commands, parameters, values, and the variables in scope."""

from __future__ import annotations

import re
from typing import Any

from ..analyze import Analysis
from ..binder.query import variables_at
from ..checker.commands import Path, WordResolution
from ..document import Document
from ..schema.schema import ArgInfo, NodeInfo, Schema
from ..syntax.ast import Brace, Named, Node, Script, Statement, StringLit, Subst, Word
from ..syntax.walk import ancestors_at

MODULE = 9
FUNCTION = 3
PROPERTY = 10
VARIABLE = 6
ENUM_MEMBER = 20

_DOLLAR = re.compile(r"\$([A-Za-z0-9]*)$")
_BLANK = re.compile(r"[ \t]*")


def _one_line(text: str | None) -> str:
    return text.split("\n")[0] if text else ""


def markdown(*parts: str | None) -> dict[str, str]:
    return {"kind": "markdown", "value": "\n\n".join(p for p in parts if p)}


def _inside_string(chain: list[Node], offset: int) -> bool:
    """Whether the offset is inside a string literal, not just at its edge."""
    return any(isinstance(n, StringLit) and ((n.start < offset < n.end) or (not n.closed and offset >= n.end)) for n in chain)


def completions(document: Document, analysis: Analysis, schema: Schema | None, position: dict[str, int]) -> list[dict[str, Any]]:
    """Completion for the position, from the command database and the variables in scope."""
    text = document.text
    offset = document.offset_at(position)
    if any(c.start < offset <= c.end for c in analysis.script.comments):
        return []

    dollar = _DOLLAR.search(text[:offset])
    if dollar:
        typed = dollar.group(1)
        rng = document.range_at(offset - len(typed), offset)
        return [
            {
                "label": d.name,
                "kind": VARIABLE,
                "detail": f"{d.kind} variable",
                "textEdit": {"range": rng, "newText": d.name},
            }
            for d in variables_at(analysis.bound, offset)
        ]

    chain = ancestors_at(analysis.script, offset)
    if _inside_string(chain, offset) or schema is None or analysis.commands is None:
        return []

    holder = next((n for n in reversed(chain) if isinstance(n, Script | Brace | Subst)), None)
    if not isinstance(holder, Script | Brace | Subst):
        return []
    items = holder.statements if isinstance(holder, Script) else holder.body
    statement = next(
        (s for s in reversed(items) if s.start <= offset and (offset <= s.end or _BLANK.fullmatch(text[s.end : offset]))),
        None,
    )
    commands = analysis.commands

    def node_at(path: tuple[str, ...]) -> NodeInfo:
        node = schema.root
        for name in path:
            node = node.get("c", {}).get(name, node)
        return node

    if statement is None:
        previous = next((s for s in reversed(items) if s.end <= offset), None)
        path: Path | None
        if previous is not None:
            path = commands.after[previous] if previous in commands.after else commands.contexts.get(previous)
        elif isinstance(holder, Script):
            path = ()
        else:
            path = commands.bodies.get(holder)
        if path is None:
            return []
        return _menu_items(node_at(path), document.range_at(offset, offset))

    elements = statement.elements
    if any(isinstance(e, Word) and e.text == "where" and e.end <= offset for e in elements):
        return []

    partial = _partial_word(statement, offset)
    rng = document.range_at(partial[0] + partial[1] if partial else offset, offset)
    typed_start = partial[0] if partial else offset
    inside = [r for r in commands.resolutions if r.start >= statement.start and r.end <= statement.end]
    before = [r for r in inside if r.end <= offset]
    command_res = next((r for r in reversed(before) if r.kind == "command"), None)

    # Typing the command word itself counts as choosing a command, not as an argument.
    if command_res is None or (partial is not None and partial[0] == command_res.start):
        menus = [r for r in before if r.kind == "menu" and r.end <= typed_start]
        if menus:
            menu_path: Path = menus[-1].path
        elif statement.prefix in ("/", ":"):
            menu_path = ()
        else:
            menu_path = commands.contexts.get(statement)
        if menu_path is None:
            return []
        return _menu_items(node_at(menu_path), rng)

    command = command_res.node
    # the word being typed does not count as given
    provided = {r.name for r in inside if r.kind == "parameter" and r.end <= typed_start}

    named = next(
        (
            e
            for e in elements
            if isinstance(e, Named)
            and e.name.start < offset
            and offset > e.equals_at
            and offset <= (e.value.end if e.value is not None else e.equals_at + 1)
        ),
        None,
    )
    if named is not None:
        parameter = next((r for r in inside if r.kind == "parameter" and r.start == named.name.start), None)
        value_start = named.value.start if isinstance(named.value, Word) else offset
        return _value_items(parameter.arg if parameter is not None else None, document.range_at(value_start, offset))

    return _parameter_items(command, provided, rng)


def _partial_word(statement: Statement, offset: int) -> tuple[int, int] | None:
    """The word being typed at the cursor: its start, and how many leading characters belong to a path separator."""
    for e in statement.elements:
        if isinstance(e, Word) and e.start < offset <= e.end:
            return e.start, e.text.rfind("/") + 1
        if isinstance(e, Named) and e.name.start < offset <= e.equals_at:
            return e.name.start, 0
    return None


def _menu_items(node: NodeInfo, rng: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, child in (node.get("c") or {}).items():
        is_command = bool(child.get("k"))
        item: dict[str, Any] = {
            "label": name,
            "kind": FUNCTION if is_command else MODULE,
            "detail": _one_line(child.get("d")),
            "textEdit": {"range": rng, "newText": name},
            "sortText": ("1" if is_command else "0") + name,
        }
        if child.get("d"):
            item["documentation"] = markdown(child["d"])
        items.append(item)
    return items


def _parameter_items(command: NodeInfo, provided: set[str], rng: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    required = set(command.get("r", []))
    for name, arg in (command.get("a") or {}).items():
        if name in provided:
            continue
        flag = arg.get("f") == 1
        item: dict[str, Any] = {
            "label": name,
            "kind": PROPERTY,
            "detail": ", ".join(p for p in ("required" if name in required else "", arg.get("t", "")) if p),
            "textEdit": {"range": rng, "newText": name if flag else f"{name}="},
            "sortText": ("0" if name in required else "1") + name,
        }
        documentation = describe_arg(name, arg)
        if documentation is not None:
            item["documentation"] = documentation
        items.append(item)
    return items


def _value_items(arg: ArgInfo | None, rng: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"label": value, "kind": ENUM_MEMBER, "textEdit": {"range": rng, "newText": value}}
        for value in ((arg or {}).get("e") or [])
    ]


def describe_arg(name: str, arg: ArgInfo) -> dict[str, str] | None:
    if not arg.get("d") and not arg.get("t") and not arg.get("e"):
        return None
    values = None
    if arg.get("e"):
        shown = ", ".join(f"`{v}`" for v in arg["e"][:20])
        more = ", ..." if len(arg["e"]) > 20 else ""
        values = f"{'Values' if arg.get('x') else 'Suggested values'}: {shown}{more}"
    return markdown(arg.get("d"), f"Type: `{arg['t']}`" if arg.get("t") else None, values)


__all__ = ["WordResolution", "completions", "describe_arg", "markdown"]
