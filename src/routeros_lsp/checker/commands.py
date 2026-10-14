"""Menu, command and parameter rules, checked against the command database.

The menu path in effect at a point of the script is tracked the way RouterOS does it. RouterOS resolves it while compiling, in
source order, and only a line that is nothing but a path changes it; a full command does not (probes s1 to s30 and l1 to l24):

* the top level, a bare ``{ }`` block, a statement-level ``[ ]`` and the block after a path (``/ip { route }``) carry it forward;
* the bodies of ``:if``, ``:do``, functions and so on, and every command argument, start from it but cannot change it.

``None`` means unknown, after a mistake in a path. Nothing is reported about relative words until an absolute path resets it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schema.schema import ArgInfo, NodeInfo, Schema, match_name, suggest
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
    Word,
)
from .variables import RuleFinding

Path = tuple[str, ...] | None

#: Commands that accept any parameter, or the same parameter again: the router compiled ``:do command=0 zzznope=0`` and
#: ``/ip recursive-print zzznope=0`` (research/tools/differential.py). Their parameters are not checked.
FREE_FORM = frozenset({"do", "time", "retry", "onerror", "recursive-print", "shell"})

#: Commands that exist only inside the body of a loop. They are not in the command tree (probes p19, p20).
LOOP_COMMANDS = frozenset({"break", "continue"})
LOOP_STATEMENTS = frozenset({"for", "foreach", "while", "do"})
LOOP_ONLY_NODE: NodeInfo = {"k": 1, "d": "Leave the loop or go on with its next round. Valid only inside a loop."}


@dataclass(slots=True, eq=False)
class WordResolution:
    """What a word of a command line turned out to be. Hover and completion read these."""

    #: ``menu``, ``command`` or ``parameter``
    kind: str
    start: int
    end: int
    name: str
    path: tuple[str, ...]
    node: NodeInfo
    arg: ArgInfo | None = None
    required: bool = False


@dataclass(slots=True, eq=False)
class CommandAnalysis:
    findings: list[RuleFinding] = field(default_factory=list)
    resolutions: list[WordResolution] = field(default_factory=list)
    #: The menu path in effect at the start of every statement; None where it is unknown.
    contexts: dict[Statement, Path] = field(default_factory=dict)
    #: The menu path after every statement, which differs from the one before only for a line that is just a path.
    after: dict[Statement, Path] = field(default_factory=dict)
    #: The menu path in effect where each block and command substitution starts.
    bodies: dict[Brace | Subst, Path] = field(default_factory=dict)


@dataclass(slots=True, eq=False)
class _Head:
    #: ``path``, ``command``, ``failed`` or ``unchecked``
    kind: str
    path: Path = None
    rest: list[Element] = field(default_factory=list)
    node: NodeInfo | None = None
    word: Word | None = None
    args: list[Element] = field(default_factory=list)
    menu_path: tuple[str, ...] = ()
    command_path: tuple[str, ...] = ()


def check_commands(script: Script, schema: Schema) -> CommandAnalysis:
    return _CommandChecker(schema).run(script)


def _segments(text: str) -> list[tuple[str, int]]:
    """Splits a word such as ``ip/address`` or ``..add`` into the names it holds, with their offsets."""
    out: list[tuple[str, int]] = []
    offset = 0
    for part in text.split("/"):
        at = offset
        rest = part
        while rest.startswith(".."):
            out.append(("..", at))
            rest = rest[2:]
            at += 2
        if rest != "":
            out.append((rest, at))
        offset += len(part) + 1
    return out


def _name_of(named: Named) -> str:
    return named.name.text if isinstance(named.name, Word) else named.name.value


def _list_names(candidates: tuple[str, ...]) -> str:
    return ", ".join(candidates[:6]) + (" ..." if len(candidates) > 6 else "")


class _CommandChecker:
    def __init__(self, schema: Schema) -> None:
        self.schema = schema
        self.loop_depth = 0
        self.result = CommandAnalysis()

    def run(self, script: Script) -> CommandAnalysis:
        self.statements(script.statements, (), True)
        return self.result

    def report(self, rule: str, message: str, start: int, end: int) -> None:
        self.result.findings.append(RuleFinding(rule, message, start, end))

    def node(self, path: tuple[str, ...]) -> NodeInfo:
        node = self.schema.root
        for name in path:
            node = node.get("c", {}).get(name, node)
        return node

    # ------------------------------------------------------------------------------------------------------------------
    # Walking

    def statements(self, items: list[Statement], path: Path, carry: bool, lenient: bool = False) -> Path:
        """The statements of one list see each other's path changes.

        What the list returns is the path after it when ``carry`` is set (the caller keeps it) and the path it was given
        otherwise. ``lenient`` is for braces that may be an array rather than code: only lines that are clearly commands (they
        start with ":" or "/") are checked, because ``{1;2;3}`` and ``{ add ... }`` cannot be told apart by their syntax.
        """
        current = path
        for statement in items:
            current = self.statement(statement, current, lenient)
            self.result.after[statement] = current
        return current if carry else path

    def statement(self, statement: Statement, path: Path, lenient: bool = False) -> Path:
        self.result.contexts[statement] = path
        head = self.head(statement, path, lenient)

        # Statement-level { } and [ ] and the block after a path share the path with the code around them. A path written
        # with a colon (":ip route") reaches the menu but does not make it the current one.
        if head.kind == "path":
            current = path if statement.prefix == ":" else head.path
            closed = False
            for element in head.rest:
                if closed:
                    # nothing can follow a block on its line (probes z23, z24)
                    self.report(
                        "schema/unexpected-argument",
                        "Nothing can follow a closing brace or bracket on the same line. Put ';' or a line break after it.",
                        element.start,
                        element.end,
                    )
                    closed = False
                if isinstance(element, (Brace, Subst)):
                    self.result.bodies[element] = current
                    current = self.statements(element.body, current, True)
                    closed = True
                else:
                    self.nested(element, current)
            return current

        base = path
        if head.kind == "command":
            assert head.node is not None and head.word is not None
            self.arguments(head.node, head.command_path, head.word, head.args)
            # "/ip address remove [find]" runs find in /ip address; a global command keeps the path of the code around it.
            inside = base if statement.prefix == ":" else head.menu_path
            loops = len(head.command_path) == 1 and head.command_path[0] in LOOP_STATEMENTS
            if loops:
                self.loop_depth += 1
            for element in head.args:
                self.nested(element, inside)
            if loops:
                self.loop_depth -= 1
        else:
            for element in statement.elements:
                self.nested(element, base)
        return None if head.kind == "failed" else path

    def nested(self, element: Element, path: Path) -> None:
        """Visits the constructs inside an element. They see ``path`` and cannot change it."""
        if isinstance(element, Named):
            if element.value is not None:
                self.nested(element.value, path)
        elif isinstance(element, Brace):
            self.result.bodies[element] = path
            self.statements(element.body, path, False, element.role != "block")
        elif isinstance(element, Subst):
            self.result.bodies[element] = path
            self.statements(element.body, path, False)
        elif isinstance(element, Group):
            for expr in element.exprs:
                self.expr(expr, path)
        elif isinstance(element, StringLit):
            for part in element.parts:
                if isinstance(part, CommandPart):
                    self.nested(part.subst, path)
                elif isinstance(part, ExpressionPart):
                    self.nested(part.group, path)

    def expr(self, expr: Expr, path: Path) -> None:
        if isinstance(expr, Binary):
            self.expr(expr.left, path)
            self.expr(expr.right, path)
        elif isinstance(expr, Unary):
            self.expr(expr.operand, path)
        elif not isinstance(expr, Word | Missing):
            self.nested(expr, path)

    # ------------------------------------------------------------------------------------------------------------------
    # The words at the start of a command line: menu path and command

    def head(self, statement: Statement, path: Path, lenient: bool) -> _Head:
        elements = statement.elements
        prefix = statement.prefix
        if prefix == "/" and not elements:
            return _Head("path", ())
        if not elements:
            return _Head("path", path)
        if lenient and prefix is None:
            return _Head("unchecked")
        # a line that is only [ ... ] runs its command with the path of the code around it, and keeps any path it sets
        if prefix is None and len(elements) == 1 and elements[0].kind == "subst":
            return _Head("path", path, list(elements))

        if prefix == "/" or prefix == ":":
            current: tuple[str, ...] = ()
        elif path is None:
            return _Head("unchecked")
        else:
            current = path

        # After ':' the word may still be a menu: ":log info" is the command info of the menu log.
        colon = prefix == ":"
        node = self.node(current)
        for i, element in enumerate(elements):
            if isinstance(element, Brace) and not colon:
                return _Head("path", current, list(elements[i:]))
            if not isinstance(element, Word):
                # a value where a name is expected: nothing sensible to say about the path
                return _Head("unchecked") if i == 0 else _Head("path", current, list(elements[i:]))
            for text, offset in _segments(element.text):
                start = element.start + offset
                end = start + len(text)
                if text == "..":
                    current = current[:-1]
                    node = self.node(current)
                    continue
                match = match_name(node.get("c"), text)
                if match.kind == "none" and self.loop_depth > 0 and not current and text in LOOP_COMMANDS:
                    return _Head(
                        "command",
                        node=LOOP_ONLY_NODE,
                        word=element,
                        args=list(elements[i + 1 :]),
                        menu_path=current,
                        command_path=(text,),
                    )
                if match.kind == "ambiguous":
                    self.report(
                        "schema/ambiguous-name",
                        f"'{text}' could be any of {_list_names(match.candidates)}. Write more of the name.",
                        start,
                        end,
                    )
                    return _Head("failed")
                if match.kind == "none":
                    self.unknown_command(text, node, current, colon, start, end)
                    return _Head("failed")
                is_command = bool(match.value.get("k"))
                self.result.resolutions.append(
                    WordResolution(
                        kind="command" if is_command else "menu",
                        start=start,
                        end=end,
                        name=match.name,
                        path=(*current, match.name),
                        node=match.value,
                    )
                )
                if is_command:
                    return _Head(
                        "command",
                        node=match.value,
                        word=element,
                        args=list(elements[i + 1 :]),
                        menu_path=current,
                        command_path=(*current, match.name),
                    )
                current = (*current, match.name)
                node = match.value
        return _Head("path", current)

    def unknown_command(self, word: str, node: NodeInfo, path: tuple[str, ...], colon: bool, start: int, end: int) -> None:
        where = "/" + " ".join(path) if path else "the global commands" if colon else "the top level"
        what = "global command" if colon else "menu or command"
        message = f"'{word}' is not a {what} in {where} of the RouterOS {self.schema.version} command database."
        close = suggest((node.get("c") or {}).keys(), word)
        root_child = (self.schema.root.get("c") or {}).get(word)
        if close:
            message += " Did you mean " + ", ".join(f"'{n}'" for n in close) + "?"
        elif not colon and path and root_child is not None and root_child.get("k"):
            message += f" Global commands need a ':' inside a menu: ':{word}'."
        elif not colon and path and root_child is not None:
            message += f" '{word}' is a top-level menu; start the line with '/' to reach it from here."
        self.report("schema/unknown-command", message, start, end)

    # ------------------------------------------------------------------------------------------------------------------
    # The arguments of a command

    def arguments(self, command: NodeInfo, command_path: tuple[str, ...], word: Word, args: list[Element]) -> None:
        table: dict[str, ArgInfo] | None = command.get("a")
        allowed_unnamed = int(command.get("u", 0))
        # find takes any property as a condition (probes w1 to w6)
        command_name = command_path[-1]
        conditions = command_name == "find" and table is not None and "where" in table
        open_conditions = conditions or command_name in FREE_FORM
        provided: set[str] = set()
        unnamed = 0
        # RouterOS reports the first problem of a command line only. A missing parameter that follows from a mistyped or
        # surplus one is not worth a second message.
        mistaken = False

        def take_unnamed(element: Element) -> None:
            nonlocal unnamed, mistaken
            unnamed += 1
            if unnamed != allowed_unnamed + 1:
                return
            mistaken = True
            if allowed_unnamed == 0:
                what = "This command takes no unnamed arguments"
            else:
                noun = "argument" if allowed_unnamed == 1 else "arguments"
                what = f"This command takes at most {allowed_unnamed} unnamed {noun}"
            if isinstance(element, Word) and element.text.startswith("#"):
                message = (
                    f"{what}, and a '#' only starts a comment at the beginning of a command, so RouterOS reads this as an "
                    "argument. Put ';' before the comment."
                )
            else:
                message = f"{what}. Name the parameter (name=value), or check for a missing ';' between commands."
            self.report("schema/unexpected-argument", message, element.start, element.end)

        for index, element in enumerate(args):
            if isinstance(element, Word):
                if element.text == "where":
                    # RouterOS needs a condition after it (probe b15)
                    if index == len(args) - 1 and table is not None and "where" in table:
                        mistaken = True
                        self.report(
                            "schema/parameter-needs-value", "'where' needs a condition after it.", element.start, element.end
                        )
                    break
                if element.text.startswith("!"):
                    continue
                match = match_name(table, element.text)
                if conditions:
                    continue
                # Where a command takes unnamed values, a word that is only the start of a parameter name is such a value
                # (probes b1 to b3). Where it takes none, only a flag can stand without a value (b5, b6).
                if match.kind == "found" and (allowed_unnamed == 0 or match.name == element.text or match.value.get("f") == 1):
                    provided.add(match.name)
                    self.parameter(command, command_path, match.name, match.value, element.start, element.end)
                    if allowed_unnamed == 0 and match.value.get("f") != 1:
                        mistaken = True
                        self.report(
                            "schema/parameter-needs-value",
                            f"'{match.name}' takes a value: write {match.name}=...",
                            element.start,
                            element.end,
                        )
                elif match.kind == "ambiguous" and allowed_unnamed == 0:
                    mistaken = True
                    self.ambiguous(element.text, match.candidates, element.start, element.end)
                else:
                    take_unnamed(element)
            elif isinstance(element, Named):
                key = _name_of(element)
                match = match_name(table, key)
                end = element.name.end
                if match.kind == "found":
                    if match.name in provided and not open_conditions:
                        self.report("schema/duplicate-parameter", f"'{match.name}' is given more than once.", element.start, end)
                    provided.add(match.name)
                    self.parameter(command, command_path, match.name, match.value, element.name.start, end)
                    if match.value.get("f") == 1:
                        mistaken = True
                        self.report(
                            "schema/flag-with-value",
                            f"'{match.name}' is a flag and takes no value: write it without '=' (probes b13, b14).",
                            element.equals_at,
                            element.equals_at + 1,
                        )
                elif match.kind == "ambiguous":
                    mistaken = True
                    self.ambiguous(key, match.candidates, element.start, end)
                elif not open_conditions:
                    mistaken = True
                    close = suggest((table or {}).keys(), key)
                    hint = " Did you mean " + ", ".join(f"'{n}'" for n in close) + "?" if close else ""
                    self.report(
                        "schema/unknown-parameter",
                        f"'{key}' is not a parameter of this command in the RouterOS {self.schema.version} command database.{hint}",
                        element.start,
                        end,
                    )
            elif element.kind != "operator":
                take_unnamed(element)

        # Unnamed values fill the required arguments that were not named, in the order RouterOS lists them.
        required = [name for name in command.get("r", []) if name not in provided]
        missing = required[min(unnamed, len(required)) :]
        if missing and not mistaken:
            noun = "a value" if len(missing) == 1 else "values"
            self.report("schema/missing-required", f"Missing {noun} for {', '.join(missing)}.", word.start, word.end)

    def parameter(self, command: NodeInfo, path: tuple[str, ...], name: str, arg: ArgInfo, start: int, end: int) -> None:
        self.result.resolutions.append(
            WordResolution(
                kind="parameter",
                start=start,
                end=end,
                name=name,
                path=path,
                node=command,
                arg=arg,
                required=name in command.get("r", []),
            )
        )

    def ambiguous(self, word: str, candidates: tuple[str, ...], start: int, end: int) -> None:
        self.report(
            "schema/ambiguous-name",
            f"'{word}' could be any of {_list_names(candidates)}. Write more of the name.",
            start,
            end,
        )
