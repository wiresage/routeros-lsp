"""Runs the stages (parse, bind, check) over a text and applies the severity settings."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .binder.binder import BindOptions, BindResult, bind
from .checker.commands import CommandAnalysis, check_commands
from .checker.variables import RuleFinding, check_variables
from .config import DEFAULT_CONTEXT_VARIABLES
from .rules import RULES
from .schema.schema import Schema
from .syntax.ast import Script
from .syntax.parser import parse


class _Unset:
    """Marks an option that was not given, so that None can mean "turn it off"."""

    __slots__ = ()


UNSET = _Unset()

_bundled: list[Schema | None] = []


def bundled_schema() -> Schema | None:
    """The command database that ships with the package, loaded once."""
    if not _bundled:
        try:
            _bundled.append(Schema.bundled())
        except (OSError, ValueError):
            _bundled.append(None)
    return _bundled[0]


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    message: str
    start: int
    end: int
    #: ``error``, ``warning``, ``information`` or ``hint``
    severity: str


@dataclass(slots=True)
class Analysis:
    script: Script
    bound: BindResult
    #: What the words of the command lines resolved to; None when no command database is in use.
    commands: CommandAnalysis | None
    findings: list[Finding]


def analyze(
    text: str,
    *,
    severities: Mapping[str, str] | None = None,
    scope: str = "import",
    context_variables: Collection[str] = DEFAULT_CONTEXT_VARIABLES,
    schema: Schema | _Unset | None = UNSET,
) -> Analysis:
    """Analyses ``text``.

    ``severities`` overrides the default severity of a rule (``off`` drops it). ``scope`` is ``import`` or ``script``.
    ``schema`` is the command database: left out it is the one that ships with the package, None turns the command checks off.
    """
    parsed = parse(text)
    diagnostics = [RuleFinding(d.rule, d.message, d.start, d.end) for d in parsed.diagnostics]
    return _analyze(parsed.script, diagnostics, text, severities, scope, context_variables, schema)


def _analyze(
    script: Script,
    diagnostics: list[RuleFinding],
    text: str,
    severities: Mapping[str, str] | None,
    scope: str,
    context_variables: Collection[str],
    schema: Schema | _Unset | None,
) -> Analysis:
    bound = bind(script, text, BindOptions(mode=scope, context_variables=frozenset(context_variables)))
    chosen = bundled_schema() if isinstance(schema, _Unset) else schema
    commands = check_commands(script, chosen) if chosen is not None else None
    found = [*diagnostics, *check_variables(bound), *(commands.findings if commands is not None else [])]
    # The hint about a "#" is redundant where the argument count already rejects the same word, and says it better.
    rejected = {f.start for f in found if f.rule == "schema/unexpected-argument"}
    kept = [f for f in found if not (f.rule == "syntax/trailing-comment" and f.start in rejected)]

    findings: list[Finding] = []
    for f in kept:
        severity = (severities or {}).get(f.rule) or RULES[f.rule].severity
        if severity != "off":
            findings.append(Finding(f.rule, f.message, f.start, f.end, severity))
    findings.sort(key=lambda f: (f.start, f.end))
    return Analysis(script, bound, commands, findings)
