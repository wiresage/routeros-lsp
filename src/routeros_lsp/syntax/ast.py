"""Syntax tree. Offsets are indexes into the Python string (code points); the server converts them to LSP positions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

# Nodes compare and hash by identity (eq=False), which is what the binder and the checkers need to key maps by statement.


@dataclass(slots=True, eq=False, kw_only=True)
class Span:
    start: int
    end: int


@dataclass(slots=True, eq=False, kw_only=True)
class Script(Span):
    kind: ClassVar[str] = "script"
    statements: list[Statement]
    #: Every comment, from the "#" to the end of its line.
    comments: list[Span]


@dataclass(slots=True, eq=False, kw_only=True)
class Statement(Span):
    """One command line.

    The parser does not know which leading words are menu path and which is the command; it keeps every word as an element and
    leaves that split to the checker, which has the command database.
    """

    kind: ClassVar[str] = "statement"
    #: ``:`` for a global command, ``/`` for an absolute menu path, None when neither is written.
    prefix: str | None
    elements: list[Element]


@dataclass(slots=True, eq=False, kw_only=True)
class Word(Span):
    """An unquoted word: a command, a menu name, a flag, a literal such as 10s or 1.1.1.1/24."""

    kind: ClassVar[str] = "word"
    text: str


@dataclass(slots=True, eq=False, kw_only=True)
class TextPart(Span):
    kind: ClassVar[str] = "text"
    text: str


@dataclass(slots=True, eq=False, kw_only=True)
class EscapePart(Span):
    kind: ClassVar[str] = "escape"
    text: str


@dataclass(slots=True, eq=False, kw_only=True)
class VariablePart(Span):
    kind: ClassVar[str] = "variable"
    name: str


@dataclass(slots=True, eq=False, kw_only=True)
class ExpressionPart(Span):
    kind: ClassVar[str] = "expression"
    group: Group


@dataclass(slots=True, eq=False, kw_only=True)
class CommandPart(Span):
    kind: ClassVar[str] = "command"
    subst: Subst


StringPart = TextPart | EscapePart | VariablePart | ExpressionPart | CommandPart


@dataclass(slots=True, eq=False, kw_only=True)
class StringLit(Span):
    kind: ClassVar[str] = "string"
    #: The text with escapes resolved and substitutions left out.
    value: str
    parts: list[StringPart]
    closed: bool


@dataclass(slots=True, eq=False, kw_only=True)
class Variable(Span):
    """``$name`` or ``$"quoted name"``."""

    kind: ClassVar[str] = "variable"
    name: str
    quoted: bool


@dataclass(slots=True, eq=False, kw_only=True)
class Subst(Span):
    """``[ command ]``"""

    kind: ClassVar[str] = "subst"
    body: list[Statement]
    closed: bool


@dataclass(slots=True, eq=False, kw_only=True)
class Group(Span):
    """``( expression )``. Several expressions means operands were written next to each other, which RouterOS accepts."""

    kind: ClassVar[str] = "group"
    exprs: list[Expr]
    closed: bool


@dataclass(slots=True, eq=False, kw_only=True)
class Brace(Span):
    """``{ ... }`` is a code block or an array literal and the syntax does not say which.

    ``role`` is ``"block"`` where the position makes it certain (a line of its own, the value of do= or else=) and ``"unknown"``
    otherwise.
    """

    kind: ClassVar[str] = "brace"
    body: list[Statement]
    role: str
    closed: bool


@dataclass(slots=True, eq=False, kw_only=True)
class Named(Span):
    """``name=value``. The value is None when it is left out (``name=`` at the end of a command)."""

    kind: ClassVar[str] = "named"
    name: Word | StringLit
    #: Offset of the "=".
    equals_at: int
    value: Element | None


@dataclass(slots=True, eq=False, kw_only=True)
class Operator(Span):
    """An "=" standing on its own."""

    kind: ClassVar[str] = "operator"
    op: str


@dataclass(slots=True, eq=False, kw_only=True)
class Binary(Span):
    kind: ClassVar[str] = "binary"
    op: str
    op_start: int
    left: Expr
    right: Expr


@dataclass(slots=True, eq=False, kw_only=True)
class Unary(Span):
    kind: ClassVar[str] = "unary"
    op: str
    operand: Expr


@dataclass(slots=True, eq=False, kw_only=True)
class Missing(Span):
    """Stands in for an operand that is missing, so the tree stays whole after an error."""

    kind: ClassVar[str] = "missing"


Element = Word | StringLit | Variable | Subst | Group | Brace | Named | Operator
Operand = Word | StringLit | Variable | Subst | Group | Brace
Expr = Operand | Binary | Unary | Missing
Node = Script | Statement | Element | Expr

__all__ = [
    "Binary",
    "Brace",
    "CommandPart",
    "Element",
    "EscapePart",
    "Expr",
    "ExpressionPart",
    "Group",
    "Missing",
    "Named",
    "Node",
    "Operand",
    "Operator",
    "Script",
    "Span",
    "Statement",
    "StringLit",
    "StringPart",
    "Subst",
    "TextPart",
    "Unary",
    "Variable",
    "VariablePart",
    "Word",
    "field",
]
