"""Every diagnostic the server can produce is a rule with a stable id, a default severity and a source.

Sources say how well the rule is founded, so a message never presents a router quirk as the language specification:

* ``doc``          the Scripting documentation states it
* ``doc-example``  not stated, but shown by a documentation example
* ``device``       observed on a router, not documented (see docs/ambiguities.md)
* ``open``         the documentation is silent or contradictory
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("error", "warning", "information", "hint", "off")


@dataclass(frozen=True, slots=True)
class RuleInfo:
    source: str
    severity: str
    #: One line for documentation and configuration listings.
    summary: str
    #: Row ids in docs/ambiguities.md, when the rule rests on one.
    ambiguity: tuple[str, ...] = ()


RULES: dict[str, RuleInfo] = {
    "syntax/bom": RuleInfo(
        source="device",
        severity="error",
        summary="A byte order mark at the start of the file is rejected by RouterOS.",
        ambiguity=("L-06",),
    ),
    "syntax/unterminated-string": RuleInfo(
        source="doc",
        severity="error",
        summary="A string literal is not closed.",
    ),
    "syntax/invalid-escape": RuleInfo(
        source="doc",
        severity="error",
        summary="Backslash followed by something that is not a documented escape sequence.",
        ambiguity=(
            "E-03",
            "E-04",
        ),
    ),
    "syntax/bad-interpolation": RuleInfo(
        source="doc",
        severity="error",
        summary='A "$" inside a string that is not followed by a variable name, "(" or "[".',
    ),
    "syntax/bare-dollar": RuleInfo(
        source="device",
        severity="error",
        summary='A "$" that is not followed by a variable name.',
    ),
    "syntax/dollar-expression-outside-string": RuleInfo(
        source="device",
        severity="error",
        summary='"$(" and "$[" are only valid inside a string.',
        ambiguity=("O-09",),
    ),
    "syntax/missing-closer": RuleInfo(
        source="doc",
        severity="error",
        summary='A "(", "[" or "{" is never closed.',
    ),
    "syntax/unexpected-closer": RuleInfo(
        source="device",
        severity="error",
        summary='A ")" without a matching "(".',
    ),
    "syntax/stray-closer": RuleInfo(
        source="open",
        severity="warning",
        summary='A "}" or "]" without a matching opener. RouterOS accepts it.',
        ambiguity=("L-13",),
    ),
    "syntax/adjacent-tokens": RuleInfo(
        source="device",
        severity="error",
        summary="Two values written with no space between them.",
        ambiguity=(
            "L-10",
            "L-16",
        ),
    ),
    "syntax/space-before-equals": RuleInfo(
        source="doc",
        severity="error",
        summary='Whitespace before "=" in a parameter.',
        ambiguity=("L-09",),
    ),
    "syntax/unexpected-equals": RuleInfo(
        source="device",
        severity="error",
        summary='An "=" that does not belong to a parameter.',
        ambiguity=("L-16",),
    ),
    "syntax/statement-starts-with-pair": RuleInfo(
        source="device",
        severity="error",
        summary='A command line that starts with name=value, for example "else=" on its own line.',
        ambiguity=(
            "C-12",
            "A-01",
        ),
    ),
    "syntax/trailing-comment": RuleInfo(
        source="device",
        severity="warning",
        summary='A "#" after the first word of a command is an argument, not a comment. With a command database the surplus arguments are reported as errors by schema/unexpected-argument.',
        ambiguity=("L-01",),
    ),
    "syntax/missing-separator": RuleInfo(
        source="device",
        severity="error",
        summary='Two commands on one line without ";" between them.',
        ambiguity=("L-11",),
    ),
    "syntax/invalid-character": RuleInfo(
        source="device",
        severity="error",
        summary="A character that RouterOS does not accept outside a string.",
        ambiguity=(
            "L-15",
            "L-16",
        ),
    ),
    "syntax/newline-in-parens": RuleInfo(
        source="device",
        severity="error",
        summary='A line break inside "( )" without a backslash.',
    ),
    "syntax/empty-expression": RuleInfo(
        source="device",
        severity="error",
        summary='An empty "( )".',
    ),
    "syntax/expected-operand": RuleInfo(
        source="device",
        severity="error",
        summary="An operator without the value it needs.",
    ),
    "syntax/unexpected-token": RuleInfo(
        source="device",
        severity="error",
        summary="A token that cannot appear inside an expression.",
    ),
    "syntax/expected-command": RuleInfo(
        source="doc",
        severity="error",
        summary='A prefix such as ":" with no command after it, or a line that starts with something that cannot be a command.',
    ),
    "syntax/stray-backslash": RuleInfo(
        source="open",
        severity="warning",
        summary="A backslash outside a string that does not end the line. The documentation calls it illegal; RouterOS ignores it.",
        ambiguity=("L-03",),
    ),
    "syntax/too-deeply-nested": RuleInfo(
        source="open",
        severity="error",
        summary="Brackets nested deeper than the parser follows.",
    ),
    "vars/set-undeclared": RuleInfo(
        source="device",
        severity="error",
        summary=":set of a variable that is not declared in the same or an enclosing block.",
        ambiguity=(
            "V-01",
            "V-03",
            "V-04",
        ),
    ),
    "vars/undeclared-read": RuleInfo(
        source="doc",
        severity="warning",
        summary="A variable is read but never declared in the file. RouterOS reads it as empty.",
        ambiguity=(
            "V-01",
            "V-14",
        ),
    ),
    "vars/local-out-of-scope": RuleInfo(
        source="device",
        severity="warning",
        summary="A local variable is read where its scope has ended, for example on a later top-level line of an imported file.",
        ambiguity=("V-03",),
    ),
    "vars/invalid-name": RuleInfo(
        source="device",
        severity="error",
        summary='A variable name with characters other than letters and digits, written without quotes, or with a "$" where it is declared.',
        ambiguity=("V-07",),
    ),
    "vars/keyword-name": RuleInfo(
        source="doc",
        severity="warning",
        summary="A variable named and, or or in. The documentation reserves them; RouterOS accepts them.",
        ambiguity=("V-08",),
    ),
    "schema/unknown-command": RuleInfo(
        source="device",
        severity="warning",
        summary="A menu or command that is not in the command database. Menus of packages the database was not generated with are missing from it.",
        ambiguity=(
            "C-02",
            "C-10",
            "P-01",
            "P-02",
        ),
    ),
    "schema/ambiguous-name": RuleInfo(
        source="device",
        severity="error",
        summary="An abbreviated name that matches more than one menu, command or parameter.",
        ambiguity=("C-10",),
    ),
    "schema/unknown-parameter": RuleInfo(
        source="device",
        severity="warning",
        summary="A parameter that the command does not have in the command database. Some parameters exist only on some hardware.",
        ambiguity=("C-10",),
    ),
    "schema/duplicate-parameter": RuleInfo(
        source="device",
        severity="error",
        summary="The same parameter given twice.",
    ),
    "schema/unexpected-argument": RuleInfo(
        source="device",
        severity="error",
        summary="More unnamed arguments than the command takes.",
        ambiguity=("C-04",),
    ),
    "schema/flag-with-value": RuleInfo(
        source="device",
        severity="error",
        summary="A flag such as detail or count-only written as name=value.",
    ),
    "schema/parameter-needs-value": RuleInfo(
        source="device",
        severity="error",
        summary="A parameter that takes a value written without one, as if it were a flag.",
    ),
    "schema/missing-required": RuleInfo(
        source="device",
        severity="error",
        summary="A parameter that the command cannot be compiled without is missing.",
    ),
}
