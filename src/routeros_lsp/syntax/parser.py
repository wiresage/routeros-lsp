"""A hand-written, scannerless, recursive-descent parser for RouterOS scripts, with error recovery.

RouterOS lexes by context: ``#`` is a comment only where a command starts, a word is whatever a command argument allows, and
``{ }`` is a block or an array depending on where it stands. Every rule here was measured with ``/import dry-run`` on a router;
docs/grammar.md and docs/ambiguities.md give the evidence.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from .ast import (
    Binary,
    Brace,
    CommandPart,
    Element,
    EscapePart,
    Expr,
    ExpressionPart,
    Group,
    Missing,
    Named,
    Operand,
    Operator,
    Script,
    Span,
    Statement,
    StringLit,
    StringPart,
    Subst,
    TextPart,
    Unary,
    Variable,
    VariablePart,
    Word,
)

#: Python recurses once per nested bracket several times over; the default limit would stop a file nested 100 deep.
_RECURSION_LIMIT = 4000

MAX_DEPTH = 100

#: Parameters whose braces hold commands. The value of any other name= is an array or a block, and the syntax cannot say which.
BLOCK_PARAMS = frozenset({"do", "else", "on-error"})

TWO_CHAR_OPS = ("&&", "||", "<<", ">>", "<=", ">=", "!=", "->", "<>")
ONE_CHAR_OPS = "+-*/%<>=~&|^.,"

#: The documentation gives no precedence table. This is the order observed on RouterOS 7.21.4 (docs/ambiguities.md O-01):
#: "* / %" over "+ -" over "." over comparison, "&&" over "||". Placing the bitwise operators between "." and comparison is a
#: guess; it cannot change which scripts are valid, only how they are grouped.
PRECEDENCE = {
    "||": 1,
    "or": 1,
    "&&": 2,
    "and": 2,
    "=": 3,
    "!=": 3,
    "<>": 3,
    "<": 3,
    ">": 3,
    "<=": 3,
    ">=": 3,
    "~": 3,
    "in": 3,
    "|": 4,
    "^": 4,
    "&": 4,
    "<<": 4,
    ">>": 4,
    ".": 5,
    ",": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "%": 7,
    "->": 8,
}

SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "$": "$",
    "_": " ",
    "a": "\x07",
    "b": "\b",
    # The documentation says 0xFF; RouterOS 7.21.4 produces 0x0C (docs/ambiguities.md E-01).
    "f": "\f",
    "v": "\v",
    # Documented as removed in 7.1rc2, still accepted (E-02).
    "?": "?",
}

#: Characters that end a bare word. Everything else, including # ~ ! < | & + * % ^ - . , / : and @, belongs to it.
NON_WORD = frozenset(" \t\n\r;\"$[](){}=\\?'`")

_PAIR_CONTINUATIONS = ("else", "do", "while", "on-error", "in")
_BINARY_WORD = re.compile(r"(and|or|in)(?![A-Za-z0-9_])")
_COLON_COMMAND = re.compile(r":[A-Za-z]")
_HEX_LIKE = re.compile(r"[0-9a-fA-F]")
_BAD_HEAD = re.compile(r"[!,~*]")
_HAS_UPPER = re.compile(r"[A-Z]")


def _is_eol(c: str) -> bool:
    return c == "\n" or c == "\r"


def _is_alnum(c: str) -> bool:
    return ("0" <= c <= "9") or ("a" <= c <= "z") or ("A" <= c <= "Z")


def _is_upper_hex(c: str) -> bool:
    return ("0" <= c <= "9") or ("A" <= c <= "F")


def _is_word_char(c: str) -> bool:
    return c != "" and ord(c) < 0x80 and c not in NON_WORD


def _is_atom_start(c: str) -> bool:
    return _is_alnum(c) or c == "_" or c == "." or c == ":"


def _is_atom_char(c: str) -> bool:
    return _is_atom_start(c) or c == "/"


def _printable(c: str) -> str:
    if c == "":
        return "the end of the file"
    if _is_eol(c):
        return "the end of the line"
    return f"'{c}'"


@dataclass(frozen=True, slots=True)
class SyntaxDiagnostic:
    rule: str
    message: str
    start: int
    end: int


@dataclass(slots=True)
class ParseResult:
    script: Script
    diagnostics: list[SyntaxDiagnostic]


def parse(text: str) -> ParseResult:
    if sys.getrecursionlimit() < _RECURSION_LIMIT:
        sys.setrecursionlimit(_RECURSION_LIMIT)
    try:
        return _Parser(text).run()
    except RecursionError:
        # Unreachable while MAX_DEPTH holds, but a language server must not die on pathological input.
        script = Script(start=0, end=len(text), statements=[], comments=[])
        message = "Brackets are nested too deeply to analyse the rest of the file."
        return ParseResult(script, [SyntaxDiagnostic("syntax/too-deeply-nested", message, 0, min(1, len(text)))])


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.depth = 0
        #: Closers of the constructs currently open, innermost last. Tells a missing closer from a stray one.
        self.closers: list[str] = []
        self.found: list[SyntaxDiagnostic] = []
        self.comments: list[Span] = []

    # ------------------------------------------------------------------------------------------------------------------
    # Plumbing

    def run(self) -> ParseResult:
        if self.text[:1] == "﻿":
            self.report(
                "syntax/bom",
                "The file starts with a byte order mark, which RouterOS rejects. Save it as UTF-8 without BOM.",
                0,
                1,
            )
            self.pos = 1
        body, _ = self.parse_statements(None, "block")
        script = Script(start=0, end=len(self.text), statements=body, comments=self.comments)
        return ParseResult(script, self.finish())

    def finish(self) -> list[SyntaxDiagnostic]:
        seen: set[tuple[str, int, int]] = set()
        unique: list[SyntaxDiagnostic] = []
        for d in self.found:
            key = (d.rule, d.start, d.end)
            if key not in seen:
                seen.add(key)
                unique.append(d)
        unique.sort(key=lambda d: (d.start, d.end))
        return unique

    def report(self, rule: str, message: str, start: int, end: int) -> None:
        self.found.append(SyntaxDiagnostic(rule, message, start, end))

    def peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.text[i] if 0 <= i < len(self.text) else ""

    def char_at(self, i: int) -> str:
        return self.text[i] if 0 <= i < len(self.text) else ""

    def at_statement_end(self) -> bool:
        c = self.peek()
        return c == "" or c == ";" or _is_eol(c) or c == "}" or c == "]" or c == ")"

    def after_eol(self, p: int) -> int:
        """Index just past the line break that starts at p (CR LF counts as one)."""
        return p + 2 if self.char_at(p) == "\r" and self.char_at(p + 1) == "\n" else p + 1

    def skip_to_eol(self) -> None:
        text, n = self.text, len(self.text)
        pos = self.pos
        while pos < n and not _is_eol(text[pos]):
            pos += 1
        self.pos = pos

    def skip_comment(self) -> None:
        start = self.pos
        self.skip_to_eol()
        # A comment can be reached twice when the parser backs up after an omitted value; positions only ever grow.
        if not self.comments or self.comments[-1].start < start:
            self.comments.append(Span(start=start, end=self.pos))

    def skip_inline(self) -> bool:
        """Skips spaces, tabs and line joins (a backslash before the line break). Returns True when anything was skipped.

        A backslash that does not end the line is ignored by RouterOS although the documentation calls it illegal (L-03).
        """
        start = self.pos
        text, n = self.text, len(self.text)
        while True:
            c = self.text[self.pos] if self.pos < n else ""
            if c == " " or c == "\t":
                self.pos += 1
            elif c == "\\":
                p = self.pos + 1
                while p < n and (text[p] == " " or text[p] == "\t"):
                    p += 1
                if p >= n:
                    self.pos = p
                elif _is_eol(text[p]):
                    self.pos = self.after_eol(p)
                    # A line that starts with # right after a join is a comment line (docs/ambiguities.md L-01, probe z30).
                    if self.peek() == "#":
                        self.skip_comment()
                else:
                    self.report(
                        "syntax/stray-backslash",
                        "A backslash is only valid at the end of a line or inside a string. RouterOS ignores it here.",
                        self.pos,
                        self.pos + 1,
                    )
                    self.pos += 1
            else:
                break
        return self.pos > start

    def skip_separators(self) -> None:
        """Skips whatever can sit between commands: blank space, line breaks, ";" and comments."""
        while True:
            if self.skip_inline():
                continue
            c = self.peek()
            if c == ";" or _is_eol(c):
                self.pos += 1
            elif c == "#":
                self.skip_comment()
            else:
                return

    # ------------------------------------------------------------------------------------------------------------------
    # Statements

    def parse_statements(self, closer: str | None, role: str) -> tuple[list[Statement], bool]:
        body: list[Statement] = []
        while True:
            self.skip_separators()
            if self.pos >= len(self.text):
                return body, False
            c = self.peek()
            if c == closer:
                return body, True
            if c == ")" or c == "]" or c == "}":
                if c in self.closers:
                    return body, False
                self.stray_closer(c)
                continue
            body.append(self.parse_statement(role))

    def stray_closer(self, c: str) -> None:
        if c == ")":
            self.report("syntax/unexpected-closer", "This ')' has no matching '('.", self.pos, self.pos + 1)
        else:
            opener = "{" if c == "}" else "["
            self.report(
                "syntax/stray-closer",
                f"This '{c}' has no matching '{opener}'. RouterOS accepts it, but it is almost certainly a mistake.",
                self.pos,
                self.pos + 1,
            )
        self.pos += 1

    def parse_statement(self, role: str) -> Statement:
        start = self.pos
        prefix: str | None = None
        first = self.peek()
        if first == ":" or first == "/":
            prefix = first
            self.pos += 1
            self.skip_inline()
            # A lone ':' is accepted and does nothing.
            if prefix == ":" and self.peek() == ":":
                self.report("syntax/expected-command", "Expected a command name after ':'.", self.pos, self.pos + 1)

        elements: list[Element] = []
        end = self.pos
        where = False
        while True:
            spaced = self.skip_inline()
            if self.at_statement_end():
                break
            at = self.pos
            c = self.peek()
            prev = elements[-1] if elements else None

            # After "where" the expression language applies and operators sit next to values (where address~"x").
            if not spaced and prev is not None and not where and prev.kind != "operator":
                self.check_adjacent(prev, at, c)

            el: Element | None = None
            if c == '"':
                el = self.parse_string_or_key()
            elif c == "$":
                el = self.parse_variable()
            elif c == "[":
                el = self.parse_subst()
            elif c == "(":
                el = self.parse_group()
            elif c == "{":
                # A brace on a line of its own holds commands. Anywhere else the syntax cannot tell a block from an array.
                el = self.parse_brace("block" if not elements and prefix is None else "unknown")
            elif c == "=":
                el = self.parse_loose_equals(spaced, where)
            elif _is_word_char(c):
                el = self.parse_word_or_named()
            else:
                self.invalid_character()
            end = self.pos
            if el is None:
                continue

            if isinstance(el, Word) and elements:
                self.check_word_position(el)
                if el.text == "where":
                    where = True
            elements.append(el)

        if role == "block" and elements:
            self.check_statement_head(elements[0], prefix)
        return Statement(start=start, end=end, prefix=prefix, elements=elements)

    def check_adjacent(self, prev: Element, at: int, c: str) -> None:
        if c not in ('"', "$", "[", "(", "{") and not _is_word_char(c):
            return
        message = "Put a space before this. RouterOS needs whitespace between values."
        if isinstance(prev, Variable) and not prev.quoted and c in ("_", "-"):
            message = (
                "A variable name ends at the first character that is not a letter or digit. "
                f"Quote the name to include '{c}': $\"{prev.name}{c}...\"."
            )
        self.report("syntax/adjacent-tokens", message, at, at + 1)

    def check_word_position(self, word: Word) -> None:
        if word.text.startswith("#"):
            self.report(
                "syntax/trailing-comment",
                "A '#' only starts a comment at the beginning of a command. Here RouterOS reads it as an argument and the "
                "line fails with 'expected end of command'. Put ';' before the comment.",
                word.start,
                word.start + 1,
            )
        elif _COLON_COMMAND.match(word.text):
            self.report(
                "syntax/missing-separator",
                f"'{word.text}' looks like the start of another command. Separate commands with ';' or a line break.",
                word.start,
                word.end,
            )

    def check_statement_head(self, head: Element, prefix: str | None) -> None:
        if isinstance(head, Named):
            self.report_pair_statement(head)
        elif isinstance(head, StringLit) and prefix is None:
            self.report("syntax/expected-command", "A command name is expected here, not a string.", head.start, head.start + 1)
        elif isinstance(head, Word) and prefix is None and _BAD_HEAD.match(head.text):
            self.report(
                "syntax/expected-command",
                f"A command name is expected here. A command cannot start with '{head.text[0]}'.",
                head.start,
                head.start + 1,
            )
        elif isinstance(head, Word) and _HAS_UPPER.search(head.text):
            self.report(
                "syntax/expected-command",
                f"Command and menu names are lowercase, '{head.text}' is not accepted.",
                head.start,
                head.end,
            )

    def report_pair_statement(self, head: Named) -> None:
        name = head.name.text if isinstance(head.name, Word) else head.name.value
        if name in _PAIR_CONTINUATIONS:
            message = (
                f"'{name}=' cannot start a command line. Keep it on the same line as the closing brace of the command it "
                "belongs to, or end the previous line with a backslash."
            )
        else:
            message = (
                f"'{name}=...' cannot start a command line: a command name is expected here. "
                "Inside braces, name=value is only valid in an array."
            )
        self.report("syntax/statement-starts-with-pair", message, head.equals_at, head.equals_at + 1)

    def invalid_character(self) -> None:
        """Reports and skips the character at the cursor, which cannot start or continue a bare word."""
        c = self.peek()
        code = ord(c)
        if c == "'":
            message = "Single quotes do not quote a string in RouterOS. Use double quotes."
        elif code >= 0x80:
            message = f"Non-ASCII characters such as '{c}' are only accepted inside double quotes or in a comment."
        else:
            message = f"The character '{c}' is not accepted outside a string. Put the value in double quotes."
        self.report("syntax/invalid-character", message, self.pos, self.pos + 1)
        self.pos += 1

    # ------------------------------------------------------------------------------------------------------------------
    # Elements

    def scan_word(self) -> int:
        """Advances over word characters and returns the start of the word."""
        start = self.pos
        text, n = self.text, len(self.text)
        pos = start
        while pos < n:
            c = text[pos]
            if ord(c) >= 0x80 or c in NON_WORD:
                break
            pos += 1
        self.pos = pos
        return start

    def parse_word_or_named(self) -> Word | Named:
        start = self.scan_word()
        word = Word(start=start, end=self.pos, text=self.text[start : self.pos])
        return self.finish_named(word) if self.peek() == "=" else word

    def parse_string_or_key(self) -> StringLit | Named:
        string = self.parse_string()
        return self.finish_named(string) if self.peek() == "=" else string

    def finish_named(self, name: Word | StringLit) -> Named:
        equals_at = self.pos
        self.pos += 1
        after_equals = self.pos
        # A space after "=" is accepted: the documentation's own correct example writes "from= 1".
        self.skip_inline()
        value: Element | None = None
        if not self.at_statement_end():
            key = name.text if isinstance(name, Word) else name.value
            value = self.parse_operand("block" if key in BLOCK_PARAMS else "unknown")
        if value is None:
            self.pos = after_equals
        return Named(
            start=name.start,
            end=value.end if value is not None else after_equals,
            name=name,
            equals_at=equals_at,
            value=value,
        )

    def parse_operand(self, brace_role: str) -> Element | None:
        """A value: what follows name= or sits in an argument position."""
        c = self.peek()
        if c == '"':
            return self.parse_string()
        if c == "$":
            return self.parse_variable()
        if c == "[":
            return self.parse_subst()
        if c == "(":
            return self.parse_group()
        if c == "{":
            return self.parse_brace(brace_role)
        if c == "=":
            return self.parse_loose_equals(False, False)
        start = self.scan_word()
        if self.pos == start:
            self.invalid_character()
            return None
        return Word(start=start, end=self.pos, text=self.text[start : self.pos])

    def parse_loose_equals(self, spaced: bool, where: bool) -> Operator:
        start = self.pos
        self.pos += 1
        if not where:
            if spaced:
                self.report(
                    "syntax/space-before-equals",
                    "Remove the space before '='. Parameters are written name=value.",
                    start,
                    start + 1,
                )
            else:
                self.report(
                    "syntax/unexpected-equals",
                    "Unexpected '='. A parameter value cannot contain '='; put the value in double quotes.",
                    start,
                    start + 1,
                )
        return Operator(start=start, end=self.pos, op="=")

    # ------------------------------------------------------------------------------------------------------------------
    # Strings and variables

    def parse_string(self) -> StringLit:
        text, n = self.text, len(self.text)
        start = self.pos
        self.pos += 1
        parts: list[StringPart] = []
        value: list[str] = []
        text_start = self.pos
        closed = False

        def flush(end: int) -> None:
            if end > text_start:
                chunk = text[text_start:end]
                parts.append(TextPart(start=text_start, end=end, text=chunk))
                value.append(chunk)

        while self.pos < n:
            c = text[self.pos]
            if c == '"':
                flush(self.pos)
                self.pos += 1
                closed = True
                break
            if c == "\\":
                flush(self.pos)
                value.append(self.parse_escape(parts))
                text_start = self.pos
            elif c == "$":
                flush(self.pos)
                self.parse_interpolation(parts)
                text_start = self.pos
            else:
                self.pos += 1
        if not closed:
            flush(self.pos)
            self.report(
                "syntax/unterminated-string", "This string is never closed. Add the closing double quote.", start, start + 1
            )
        return StringLit(start=start, end=self.pos, value="".join(value), parts=parts, closed=closed)

    def parse_escape(self, parts: list[StringPart]) -> str:
        """Returns the text the escape stands for."""
        start = self.pos
        n = self.char_at(start + 1)
        if n == "":
            self.pos += 1
            return ""
        if _is_eol(n):
            # Backslash, line break and the next line's leading whitespace vanish together (docs/ambiguities.md L-04).
            p = self.after_eol(start + 1)
            while self.char_at(p) == " " or self.char_at(p) == "\t":
                p += 1
            self.pos = p
            parts.append(EscapePart(start=start, end=p, text=""))
            return ""
        simple = SIMPLE_ESCAPES.get(n)
        if simple is not None:
            self.pos = start + 2
            parts.append(EscapePart(start=start, end=self.pos, text=simple))
            return simple
        n2 = self.char_at(start + 2)
        if _is_upper_hex(n) and _is_upper_hex(n2):
            self.pos = start + 3
            char = chr(int(n + n2, 16))
            parts.append(EscapePart(start=start, end=self.pos, text=char))
            return char
        hex_like = bool(_HEX_LIKE.fullmatch(n)) and bool(_HEX_LIKE.fullmatch(n2))
        if hex_like:
            message = (
                f"Invalid escape '\\{n}{n2}'. A hexadecimal escape is a backslash and two digits written with capital "
                "letters, for example \\4F."
            )
        else:
            message = (
                f"Invalid escape '\\{n}'. The valid escapes are \\\" \\\\ \\n \\r \\t \\$ \\_ \\a \\b \\f \\v and \\ followed "
                "by two capital hex digits."
            )
        self.report("syntax/invalid-escape", message, start, start + 2)
        self.pos = start + 2
        return ""

    def parse_interpolation(self, parts: list[StringPart]) -> None:
        start = self.pos
        n = self.peek(1)
        if n == "(":
            self.pos += 1
            group = self.parse_group()
            parts.append(ExpressionPart(start=start, end=self.pos, group=group))
        elif n == "[":
            self.pos += 1
            subst = self.parse_subst()
            parts.append(CommandPart(start=start, end=self.pos, subst=subst))
        elif _is_alnum(n):
            self.pos += 1
            name_start = self.pos
            while _is_alnum(self.peek()):
                self.pos += 1
            parts.append(VariablePart(start=start, end=self.pos, name=self.text[name_start : self.pos]))
        else:
            self.report(
                "syntax/bad-interpolation",
                "A '$' in a string must be followed by a variable name, '(' or '['. Write \\$ for a literal dollar sign.",
                start,
                start + 1,
            )
            self.pos += 1

    def parse_variable(self) -> Variable | Group | Subst:
        """``$name``, ``$"quoted name"``. Recovers from ``$(`` and ``$[`` outside a string by parsing the group or command."""
        start = self.pos
        n = self.peek(1)
        if n == '"':
            self.pos += 1
            string = self.parse_string()
            return Variable(start=start, end=self.pos, name=string.value, quoted=True)
        if _is_alnum(n):
            self.pos += 1
            name_start = self.pos
            while _is_alnum(self.peek()):
                self.pos += 1
            return Variable(start=start, end=self.pos, name=self.text[name_start : self.pos], quoted=False)
        if n == "(" or n == "[":
            what = "(expression)" if n == "(" else "[command]"
            self.report(
                "syntax/dollar-expression-outside-string",
                f"'${n}' is only valid inside a string. Outside a string write {what} without the '$'.",
                start,
                start + 1,
            )
            self.pos += 1
            return self.parse_group() if n == "(" else self.parse_subst()
        self.report("syntax/bare-dollar", f"Expected a variable name after '$', found {_printable(n)}.", start, start + 1)
        self.pos += 1
        return Variable(start=start, end=self.pos, name="", quoted=False)

    # ------------------------------------------------------------------------------------------------------------------
    # Brackets

    def too_deep(self, start: int) -> None:
        self.report(
            "syntax/too-deeply-nested", "Brackets are nested too deeply to analyse the rest of the file.", start, start + 1
        )
        self.pos = len(self.text)

    def parse_subst(self) -> Subst:
        start = self.pos
        if self.depth >= MAX_DEPTH:
            self.too_deep(start)
            return Subst(start=start, end=self.pos, body=[], closed=True)
        self.pos += 1
        self.depth += 1
        self.closers.append("]")
        body, closed = self.parse_statements("]", "block")
        self.closers.pop()
        self.depth -= 1
        if closed:
            self.pos += 1
        else:
            self.report("syntax/missing-closer", "Missing ']' for this '['.", start, start + 1)
        return Subst(start=start, end=self.pos, body=body, closed=closed)

    def parse_brace(self, role: str) -> Brace:
        start = self.pos
        if self.depth >= MAX_DEPTH:
            self.too_deep(start)
            return Brace(start=start, end=self.pos, body=[], role=role, closed=True)
        self.pos += 1
        self.depth += 1
        self.closers.append("}")
        body, closed = self.parse_statements("}", role)
        self.closers.pop()
        self.depth -= 1
        if closed:
            self.pos += 1
        else:
            self.report("syntax/missing-closer", "Missing '}' for this '{'.", start, start + 1)
        return Brace(start=start, end=self.pos, body=body, role=role, closed=closed)

    def parse_group(self) -> Group:
        start = self.pos
        if self.depth >= MAX_DEPTH:
            self.too_deep(start)
            return Group(start=start, end=self.pos, exprs=[], closed=True)
        self.pos += 1
        self.depth += 1
        self.closers.append(")")
        exprs = self.parse_expr_seq()
        self.closers.pop()
        self.depth -= 1
        closed = self.peek() == ")"
        if closed:
            self.pos += 1
            if not exprs:
                self.report(
                    "syntax/empty-expression", "This group is empty. Put an expression between the parentheses.", start, self.pos
                )
        else:
            self.report("syntax/missing-closer", "Missing ')' for this '('.", start, start + 1)
        return Group(start=start, end=self.pos, exprs=exprs, closed=closed)

    # ------------------------------------------------------------------------------------------------------------------
    # Expressions, inside ( )

    def skip_expr_space(self) -> None:
        """Whitespace inside an expression. A bare line break is an error; a backslash join is fine."""
        while True:
            self.skip_inline()
            if not _is_eol(self.peek()):
                return
            self.report(
                "syntax/newline-in-parens",
                "A line break is not allowed inside '( )'. End the line with a backslash to continue it.",
                self.pos,
                self.pos + 1,
            )
            self.pos = self.after_eol(self.pos)

    def parse_expr_seq(self) -> list[Expr]:
        exprs: list[Expr] = []
        while True:
            self.skip_expr_space()
            c = self.peek()
            if c == "" or c == ")":
                break
            if (c == "]" or c == "}") and c in self.closers:
                break
            if c == ";" or c == "]" or c == "}":
                self.report("syntax/unexpected-token", f"'{c}' cannot appear inside '( )'.", self.pos, self.pos + 1)
                self.pos += 1
                continue
            before = self.pos
            # Operands written next to each other are accepted by RouterOS, so each one is simply the next expression.
            exprs.append(self.parse_expr(0))
            if self.pos == before:
                self.pos += 1
        return exprs

    def parse_expr(self, min_prec: int) -> Expr:
        left = self.parse_unary()
        while True:
            self.skip_expr_space()
            op = self.peek_binary()
            if op is None or op[2] < min_prec:
                return left
            text, length, prec = op
            op_start = self.pos
            self.pos += length
            right = self.parse_operand_after(text, op_start, prec + 1)
            left = Binary(
                start=left.start,
                end=max(right.end, op_start + length),
                op=text,
                op_start=op_start,
                left=left,
                right=right,
            )

    def parse_operand_after(self, op: str, op_start: int, prec: int) -> Expr:
        self.skip_expr_space()
        c = self.peek()
        if c == "" or c == ")" or c == ";" or ((c == "]" or c == "}") and c in self.closers):
            self.report("syntax/expected-operand", f"Expected a value after '{op}'.", op_start, op_start + len(op))
            return Missing(start=self.pos, end=self.pos)
        return self.parse_expr(prec)

    def parse_unary(self) -> Expr:
        self.skip_expr_space()
        c = self.peek()
        if c == "-" or c == "!" or c == "~":
            start = self.pos
            self.pos += 1
            operand = self.parse_operand_after(c, start, 9)
            return Unary(start=start, end=max(operand.end, start + 1), op=c, operand=operand)
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        c = self.peek()
        operand: Operand
        if c == "$":
            operand = self.parse_variable()
        elif c == '"':
            operand = self.parse_string()
        elif c == "[":
            operand = self.parse_subst()
        elif c == "(":
            operand = self.parse_group()
        elif c == "{":
            operand = self.parse_brace("unknown")
        else:
            if not _is_atom_start(c):
                self.report(
                    "syntax/expected-operand",
                    f"Expected a value here, found {_printable(c)}.",
                    self.pos,
                    self.pos + (0 if c == "" else 1),
                )
                return Missing(start=self.pos, end=self.pos)
            start = self.pos
            while _is_atom_char(self.peek()):
                self.pos += 1
            operand = Word(start=start, end=self.pos, text=self.text[start : self.pos])
        return operand

    def peek_binary(self) -> tuple[str, int, int] | None:
        c = self.peek()
        if c == "":
            return None
        two = self.text[self.pos : self.pos + 2]
        if two in TWO_CHAR_OPS:
            return two, 2, PRECEDENCE[two]
        if c in ONE_CHAR_OPS:
            return c, 1, PRECEDENCE[c]
        if c in ("a", "o", "i"):
            m = _BINARY_WORD.match(self.text[self.pos : self.pos + 4])
            if m:
                word = m.group(1)
                return word, len(word), PRECEDENCE[word]
        return None
