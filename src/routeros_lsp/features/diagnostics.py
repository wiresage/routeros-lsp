"""Findings as LSP diagnostics."""

from __future__ import annotations

from typing import Any

from ..analyze import Analysis, Finding
from ..document import Document
from ..rules import RULES

DIAGNOSTIC_SOURCE = "routeros-lsp"

_SEVERITY = {"error": 1, "warning": 2, "information": 3, "hint": 4}


def describe(finding: Finding) -> str:
    """Says how well founded a finding is, so a router quirk is never mistaken for the language specification."""
    source = RULES[finding.rule].source
    if source == "device":
        return f"{finding.message} (RouterOS behaviour that the documentation does not describe)"
    if source == "open":
        return f"{finding.message} (the documentation does not specify this)"
    return finding.message


def to_diagnostics(document: Document, analysis: Analysis) -> list[dict[str, Any]]:
    return [
        {
            "range": document.range_at(f.start, f.end),
            "severity": _SEVERITY[f.severity],
            "code": f.rule,
            "source": DIAGNOSTIC_SOURCE,
            "message": describe(f),
        }
        for f in analysis.findings
    ]
