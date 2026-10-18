"""Settings: rule severities, scope mode, extra context variables and the command database."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .rules import RULES, SEVERITIES

#: Variables a DHCP server sets for a lease script (docs/ambiguities.md V-14; the documentation does not list them).
DEFAULT_CONTEXT_VARIABLES = ("leaseBound", "leaseServerName", "leaseActMAC", "leaseActIP")


@dataclass(frozen=True, slots=True)
class Settings:
    #: Overrides the default severity of individual rules. ``off`` disables a rule.
    severities: dict[str, str] = field(default_factory=dict)
    #: How the file is run. ``import`` (the default) treats every line as a scope of its own, which is what /import does and
    #: what pasting into the terminal does. ``script`` treats the whole file as one scope, as in the source of a /system script.
    scope: str = "import"
    #: Variables that the environment provides and that are therefore never reported as undeclared.
    context_variables: tuple[str, ...] = DEFAULT_CONTEXT_VARIABLES
    #: The command database: ``bundled`` (the default), ``off``, or the path of a file made by tools/gen_schema.py.
    schema: str = "bundled"


DEFAULT_SETTINGS = Settings()


def _root(raw: Any) -> Any:
    """The settings object: ``raw`` itself, or what it holds under a ``routeros`` key."""
    return raw["routeros"] if isinstance(raw, dict) and isinstance(raw.get("routeros"), dict) else raw


def has_settings(raw: Any) -> bool:
    """Whether a ``workspace/didChangeConfiguration`` payload carries any settings at all.

    Clients send null or an empty object to say "something changed" and expect the server to ask for the details. That has
    nothing to apply, and applying it would replace the settings in force, including the ``initializationOptions``, with the
    defaults.
    """
    root = _root(raw)
    return isinstance(root, dict) and bool(root)


def parse_settings(raw: Any, warn: Callable[[str], None] = lambda message: None) -> Settings:
    """Reads settings from ``initializationOptions`` or a ``workspace/didChangeConfiguration`` payload.

    Both the bare object and one nested under a ``routeros`` key are accepted. Anything unrecognised is reported through
    ``warn`` and ignored.
    """
    root = _root(raw)
    if not isinstance(root, dict):
        return DEFAULT_SETTINGS

    severities: dict[str, str] = {}
    given = root.get("severities")
    if given is not None and not isinstance(given, dict):
        warn('"severities" must be an object of rule id to severity; ignoring it')
    if isinstance(given, dict):
        for rule, value in given.items():
            if rule not in RULES:
                warn(f'unknown rule "{rule}" in "severities"')
            elif not isinstance(value, str) or value not in SEVERITIES:
                warn(f'"{rule}": expected one of {", ".join(SEVERITIES)}')
            else:
                severities[rule] = value

    scope = "import"
    if "scope" in root:
        if root["scope"] in ("import", "script"):
            scope = root["scope"]
        else:
            warn('"scope" must be "import" or "script"')

    context_variables = DEFAULT_CONTEXT_VARIABLES
    extra = root.get("contextVariables")
    if extra is not None:
        if isinstance(extra, list) and all(isinstance(v, str) for v in extra):
            context_variables = (*DEFAULT_CONTEXT_VARIABLES, *extra)
        else:
            warn('"contextVariables" must be an array of variable names')

    schema = "bundled"
    if "schema" in root:
        if isinstance(root["schema"], str) and root["schema"] != "":
            schema = root["schema"]
        else:
            warn('"schema" must be "bundled", "off" or the path of a command database file')
    return Settings(severities=severities, scope=scope, context_variables=context_variables, schema=schema)
