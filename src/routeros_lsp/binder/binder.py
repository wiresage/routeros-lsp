"""Scopes, declarations and variable references.

Scopes follow what RouterOS 7.21.4 does (docs/ambiguities.md V-01 to V-05, probe suites 13 to 15):

* a name is declared by ``:local``, ``:global``, the variable of ``:for``, ``:foreach`` and ``:onerror``, and only for the commands
  after it
* a block sees the declarations of the blocks around it, a function body only its own
* in an imported file every line is a scope of its own, however many commands ";" puts on it; in a script body the whole file
  is one (probes d1 and h25)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..syntax.ast import (
    Binary,
    Brace,
    CommandPart,
    Element,
    Expr,
    ExpressionPart,
    Group,
    Missing,
    Named,
    Script,
    Statement,
    StringLit,
    Subst,
    Unary,
    Variable,
    VariablePart,
    Word,
)

_DIGITS = re.compile(r"[0-9]+")


@dataclass(slots=True, eq=False)
class Scope:
    #: ``file``, ``statement``, ``block``, ``loop`` or ``function``
    kind: str
    parent: Scope | None
    declarations: dict[str, Declaration] = field(default_factory=dict)
    #: The source range the scope covers. A line scope grows with each statement added to the line.
    start: int = 0
    end: int = 0


@dataclass(slots=True, eq=False)
class Declaration:
    name: str
    #: ``local``, ``global`` or ``loop``
    kind: str
    start: int
    end: int
    scope: Scope
    #: From this offset on the name exists: the end of the declaring command, so a command's own value does not see it.
    from_offset: int


@dataclass(slots=True, eq=False)
class Resolution:
    """How a variable name was resolved.

    * ``declared``: in scope
    * ``global-elsewhere``: a global declared elsewhere in the file, which RouterOS finds at run time without a new declaration
    * ``local-elsewhere``: a local that exists in the file but is not visible here
    * ``exempt``: not checked (a positional name, a name RouterOS provides, or any name inside a function body)
    * ``none``: not declared anywhere
    """

    kind: str
    declaration: Declaration | None = None
    crossed_function: bool = False


@dataclass(slots=True, eq=False)
class Reference:
    name: str
    start: int
    end: int
    #: ``read`` or ``write``
    access: str
    resolution: Resolution


@dataclass(slots=True, eq=False)
class NameSite:
    """A place where a variable name is written without a ``$``: the checker validates the characters."""

    element: Word | StringLit | Variable
    text: str
    #: Offset of the first character of ``text`` in the document.
    start: int


@dataclass(slots=True, eq=False)
class BindOptions:
    #: ``import`` or ``script``
    mode: str
    #: Variables the environment provides, for example the lease script variables.
    context_variables: frozenset[str]


@dataclass(slots=True, eq=False)
class BindResult:
    scopes: list[Scope]
    declarations: list[Declaration]
    references: list[Reference]
    name_sites: list[NameSite]
    #: ``:local name=value`` and ``:global name=value``, which RouterOS rejects: the name and value are separate arguments.
    named_declarations: list[Named]


def bind(script: Script, text: str, options: BindOptions) -> BindResult:
    return _Binder(text, options).run(script)


def _word_text(element: object) -> str | None:
    return element.text if isinstance(element, Word) else None


def _breaks_line(text: str, start: int, end: int) -> bool:
    """Whether a line break that a backslash does not join lies between the two offsets."""
    for i in range(start, end):
        c = text[i]
        if c != "\n" and c != "\r":
            continue
        # the LF of a CR LF pair belongs to the break already counted at the CR
        if c == "\n" and i - 1 >= start and text[i - 1] == "\r":
            continue
        p = i - 1
        if p >= 0 and text[p] == "\r":
            p -= 1
        while p >= start and (text[p] == " " or text[p] == "\t"):
            p -= 1
        if p < start or text[p] != "\\":
            return True
    return False


class _Binder:
    def __init__(self, text: str, options: BindOptions) -> None:
        self.text = text
        self.options = options
        self.scopes: list[Scope] = []
        self.declarations: list[Declaration] = []
        self.references: list[Reference] = []
        self.name_sites: list[NameSite] = []
        self.named_declarations: list[Named] = []

    def run(self, script: Script) -> BindResult:
        importing = self.options.mode == "import"
        file_scope = self.scope("file", None, 0, script.end)
        line = self.scope("statement", None, 0, 0)
        previous_end = 0
        for statement in script.statements:
            if importing and _breaks_line(self.text, previous_end, statement.start):
                line = self.scope("statement", None, statement.start, statement.start)
            scope = line if importing else file_scope
            if scope is line:
                if line.end == line.start:
                    line.start = statement.start
                line.end = statement.end
            self.statement(statement, scope)
            previous_end = statement.end
        return BindResult(self.scopes, self.declarations, self.references, self.name_sites, self.named_declarations)

    def scope(self, kind: str, parent: Scope | None, start: int, end: int) -> Scope:
        scope = Scope(kind=kind, parent=parent, start=start, end=end)
        self.scopes.append(scope)
        return scope

    def declare(self, scope: Scope, name: str, kind: str, start: int, end: int, from_offset: int) -> None:
        declaration = Declaration(name=name, kind=kind, start=start, end=end, scope=scope, from_offset=from_offset)
        scope.declarations[name] = declaration
        self.declarations.append(declaration)

    # ------------------------------------------------------------------------------------------------------------------
    # Commands that declare or assign

    def statement(self, statement: Statement, scope: Scope) -> None:
        head = statement.elements[0] if statement.elements else None
        command = _word_text(head) if statement.prefix == ":" else None
        if command in ("local", "global"):
            self.declaration(statement, scope, command)
        elif command == "set":
            self.assignment(statement, scope)
        elif command in ("for", "foreach"):
            self.loop(statement, scope, ("do",), False)
        elif command == "onerror":
            self.loop(statement, scope, ("do", "in"), True)
        else:
            self.elements(statement.elements, scope)

    @staticmethod
    def name_of(element: Element | None) -> tuple[str, int, int, Word | StringLit | Variable] | None:
        if isinstance(element, Word):
            return element.text, element.start, element.end, element
        if isinstance(element, StringLit) and element.closed:
            return element.value, element.start, element.end, element
        if isinstance(element, Variable):
            return element.name, element.start, element.end, element
        return None

    def declaration(self, statement: Statement, scope: Scope, kind: str) -> None:
        elements = statement.elements
        # ":local name=x" names the parameter `name` (or an abbreviation of it); any other key is not a parameter at all
        first = elements[1] if len(elements) > 1 else None
        key = ""
        if isinstance(first, Named):
            key = first.name.text if isinstance(first.name, Word) else first.name.value
        parameter = key != "" and any(p.startswith(key) for p in ("name", "value", "do"))
        if isinstance(first, Named) and not parameter:
            self.named_declarations.append(first)
        by_parameter = first.value if isinstance(first, Named) and key != "" and "name".startswith(key) else None
        name = self.name_of(by_parameter if by_parameter is not None else first)
        rest_from = 2 if (by_parameter is not None or name is not None) else 1
        rest = elements[rest_from:]
        if name is not None:
            self.name_sites.append(NameSite(element=name[3], text=name[0], start=name[1]))

        for element in rest:
            # :global name do={ ... } defines a function. Its body sees neither the locals nor the arguments around it.
            if isinstance(element, Named) and _word_text(element.name) == "do" and isinstance(element.value, Brace):
                body = self.scope("function", scope, element.value.start, element.value.end)
                for inner in element.value.body:
                    self.statement(inner, body)
            else:
                self.element(element, scope)
        # The name exists for the commands after this one, not for its own value.
        if name is not None and not isinstance(name[3], Variable) and name[0] != "":
            self.declare(scope, name[0], kind, name[1], name[2], statement.end)

    def assignment(self, statement: Statement, scope: Scope) -> None:
        elements = statement.elements
        target = elements[1] if len(elements) > 1 else None
        if isinstance(target, Word):
            self.name_sites.append(NameSite(element=target, text=target.text, start=target.start))
            self.references.append(
                Reference(
                    name=target.text,
                    start=target.start,
                    end=target.end,
                    access="write",
                    resolution=self.resolve_write(target.text, scope),
                )
            )
            self.elements(elements[2:], scope)
        else:
            # :set "quoted name", :set $name and :set ($array->key) are not checked against the declarations.
            self.elements(elements[1:], scope)

    def loop(self, statement: Statement, scope: Scope, bodies: tuple[str, ...], bare_body: bool) -> None:
        """``:for i``, ``:foreach k,v`` and ``:onerror e``. The word after the command names the variables its bodies can use.

        ``bodies`` are the parameters whose braces see them; with ``bare_body`` an unnamed brace does too.
        """
        name_index = 1
        elements = statement.elements
        name_element = elements[name_index] if len(elements) > name_index else None
        names: list[tuple[str, int, int]] = []
        if isinstance(name_element, Word):
            offset = name_element.start
            for part in name_element.text.split(","):
                self.name_sites.append(NameSite(element=name_element, text=part, start=offset))
                if part != "":
                    names.append((part, offset, offset + len(part)))
                offset += len(part) + 1
        inner = self.scope("loop", scope, statement.start, statement.end)
        for text, start, end in names:
            self.declare(inner, text, "loop", start, end, end)

        for index, element in enumerate(elements):
            if index == name_index and isinstance(name_element, Word):
                continue
            if isinstance(element, Named) and isinstance(element.value, Brace) and (_word_text(element.name) or "") in bodies:
                for s in element.value.body:
                    self.statement(s, inner)
            elif bare_body and isinstance(element, Brace):
                for s in element.body:
                    self.statement(s, inner)
            else:
                self.element(element, scope)

    # ------------------------------------------------------------------------------------------------------------------
    # Reading

    def elements(self, elements: Iterable[Element], scope: Scope) -> None:
        for element in elements:
            self.element(element, scope)

    def element(self, element: Element, scope: Scope) -> None:
        if isinstance(element, Variable):
            self.read(element.name, element.start, element.end, scope)
        elif isinstance(element, StringLit):
            self.string(element, scope)
        elif isinstance(element, Subst):
            for s in element.body:
                self.statement(s, scope)
        elif isinstance(element, Group):
            for e in element.exprs:
                self.expr(e, scope)
        elif isinstance(element, Brace):
            inner = self.scope("block", scope, element.start, element.end)
            for s in element.body:
                self.statement(s, inner)
        elif isinstance(element, Named):
            if isinstance(element.name, StringLit):
                self.string(element.name, scope)
            if element.value is not None:
                self.element(element.value, scope)

    def expr(self, expr: Expr, scope: Scope) -> None:
        if isinstance(expr, Binary):
            self.expr(expr.left, scope)
            self.expr(expr.right, scope)
        elif isinstance(expr, Unary):
            self.expr(expr.operand, scope)
        elif not isinstance(expr, Word | Missing):
            self.element(expr, scope)

    def string(self, literal: StringLit, scope: Scope) -> None:
        for part in literal.parts:
            if isinstance(part, VariablePart):
                self.read(part.name, part.start, part.end, scope)
            elif isinstance(part, ExpressionPart):
                self.element(part.group, scope)
            elif isinstance(part, CommandPart):
                self.element(part.subst, scope)

    def read(self, name: str, start: int, end: int, scope: Scope) -> None:
        if name == "":
            return
        self.references.append(
            Reference(name=name, start=start, end=end, access="read", resolution=self.resolve_read(name, scope))
        )

    # ------------------------------------------------------------------------------------------------------------------
    # Resolution

    @staticmethod
    def lookup(name: str, scope: Scope) -> tuple[Declaration, bool] | None:
        crossed_function = False
        s: Scope | None = scope
        while s is not None:
            declaration = s.declarations.get(name)
            if declaration is not None:
                return declaration, crossed_function
            if s.kind == "function":
                crossed_function = True
            s = s.parent
        return None

    @staticmethod
    def inside_function(scope: Scope) -> bool:
        s: Scope | None = scope
        while s is not None:
            if s.kind == "function":
                return True
            s = s.parent
        return False

    def elsewhere(self, name: str) -> Declaration | None:
        """An earlier declaration of the name anywhere in the file, preferring a global."""
        found: Declaration | None = None
        for d in self.declarations:
            if d.name != name:
                continue
            if d.kind == "global":
                return d
            found = d
        return found

    def resolve_read(self, name: str, scope: Scope) -> Resolution:
        if _DIGITS.fullmatch(name) or name in self.options.context_variables:
            return Resolution("exempt")
        found = self.lookup(name, scope)
        if found is not None and not found[1]:
            return Resolution("declared", found[0])
        if found is not None and found[0].kind == "global":
            return Resolution("global-elsewhere", found[0])
        # A function body can read any global by name and receives arguments under names the file does not declare.
        if self.inside_function(scope):
            return Resolution("exempt")
        other = self.elsewhere(name)
        if other is not None and other.kind == "global":
            return Resolution("global-elsewhere", other)
        if other is not None:
            return Resolution("local-elsewhere", other, False)
        return Resolution("none")

    def resolve_write(self, name: str, scope: Scope) -> Resolution:
        found = self.lookup(name, scope)
        if found is not None and not found[1]:
            return Resolution("declared", found[0])
        if found is not None:
            return Resolution("local-elsewhere", found[0], True)
        other = self.elsewhere(name)
        if other is not None:
            return Resolution("local-elsewhere", other, False)
        return Resolution("none")
