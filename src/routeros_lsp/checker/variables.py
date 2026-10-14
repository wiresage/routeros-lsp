"""Variable rules: what the binder found, turned into findings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..binder.binder import BindResult, Reference
from ..syntax.ast import StringLit, Variable, Word

_KEYWORDS = frozenset({"and", "or", "in"})
_NOT_NAME_CHAR = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True, slots=True)
class RuleFinding:
    rule: str
    message: str
    start: int
    end: int


def _more(count: int) -> str:
    if count == 0:
        return ""
    return f" It is read {count} more {'time' if count == 1 else 'times'} in this file with the same result."


def _check_write(reference: Reference) -> RuleFinding | None:
    name, resolution = reference.name, reference.resolution
    if resolution.kind == "declared":
        return None
    message = (
        f"':set {name}' needs '{name}' to be declared first, with ':local {name}' or ':global {name}' earlier in the same "
        "block or in a block around it."
    )
    if resolution.kind == "local-elsewhere" and resolution.crossed_function:
        message += " A function cannot set variables of the code around it; declare the name inside the function."
    elif resolution.kind == "local-elsewhere":
        message += (
            f" '{name}' is declared elsewhere in this file, but each line of an imported file is its own scope and a block "
            "that has ended hides its names. Declare it again here or put the commands in one { } block."
        )
    return RuleFinding("vars/set-undeclared", message, reference.start, reference.end)


def _check_reads(references: list[Reference]) -> list[RuleFinding]:
    """A variable that is read where it does not exist is reported once, at its first read, with the number of further reads.

    Every later read has the same cause, and one warning per read buries the useful ones.
    """
    groups: dict[str, list[Reference]] = {}
    for reference in references:
        if reference.access != "read":
            continue
        resolution = reference.resolution
        if resolution.kind == "none":
            key = f"none:{reference.name}"
        elif resolution.kind == "local-elsewhere" and resolution.declaration is not None:
            key = f"local:{reference.name}:{resolution.declaration.start}"
        else:
            continue
        groups.setdefault(key, []).append(reference)

    findings: list[RuleFinding] = []
    for group in groups.values():
        first = group[0]
        rest = _more(len(group) - 1)
        name = first.name
        if first.resolution.kind == "none":
            message = (
                f"${name} is not declared in this file. The documentation requires a declaration before use; RouterOS 7.21.4 "
                f"reads an undeclared variable as empty. Declare it with ':local {name}' or ':global {name}', or list it "
                f'under "contextVariables" if RouterOS provides it.{rest}'
            )
            findings.append(RuleFinding("vars/undeclared-read", message, first.start, first.end))
        else:
            message = (
                f"${name} is a local variable of an earlier line or of a block that has ended, so it is empty here (an "
                f"imported file gives every line its own scope). Use ':global {name}' or put the commands in one {{ }} "
                f"block.{rest}"
            )
            findings.append(RuleFinding("vars/local-out-of-scope", message, first.start, first.end))
    return findings


def _check_names(bound: BindResult) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for site in bound.name_sites:
        element = site.element
        # A quoted name may contain anything.
        if isinstance(element, StringLit):
            continue
        if isinstance(element, Variable):
            findings.append(
                RuleFinding(
                    "vars/invalid-name",
                    "Write the variable name without '$' when you declare it. The '$' is only for reading a variable.",
                    element.start,
                    element.start + 1,
                )
            )
            continue
        assert isinstance(element, Word)
        bad = _NOT_NAME_CHAR.search(site.text)
        if bad is not None:
            at = site.start + bad.start()
            findings.append(
                RuleFinding(
                    "vars/invalid-name",
                    f"A variable name written without quotes may only contain letters and digits, not '{bad.group()}'. "
                    f'Quote the name: "{site.text}".',
                    at,
                    at + len(bad.group()),
                )
            )
        elif site.text in _KEYWORDS:
            findings.append(
                RuleFinding(
                    "vars/keyword-name",
                    f"'{site.text}' is a keyword and the documentation does not allow it as a variable name. RouterOS "
                    "accepts it, but it is easy to misread.",
                    site.start,
                    site.start + len(site.text),
                )
            )
    return findings


def check_variables(bound: BindResult) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for named in bound.named_declarations:
        name = named.name.text if isinstance(named.name, Word) else named.name.value
        findings.append(
            RuleFinding(
                "vars/invalid-name",
                f"Declare a variable as ':local {name} value', with the name and the value as separate arguments, not as "
                f"'{name}=value'.",
                named.equals_at,
                named.equals_at + 1,
            )
        )
    for reference in bound.references:
        if reference.access != "write":
            continue
        finding = _check_write(reference)
        if finding is not None:
            findings.append(finding)
    findings.extend(_check_reads(bound.references))
    findings.extend(_check_names(bound))
    return findings
