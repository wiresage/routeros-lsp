"""Hover for a menu, command, parameter or variable."""

from __future__ import annotations

from typing import Any

from ..analyze import Analysis
from ..checker.commands import WordResolution
from ..document import Document
from .completion import describe_arg


def _resolution_text(r: WordResolution) -> str:
    path = "/" + " ".join(r.path)
    if r.kind == "parameter":
        header = f"**{r.name}**{' (required)' if r.required else ''} parameter of `{path}`"
        described = describe_arg(r.name, r.arg or {})
        return "\n\n".join(p for p in (header, described["value"] if described else "") if p)
    header = f"**{path}** menu" if r.kind == "menu" else f"**{path}** command"
    lines = [header, r.node.get("d", "")]
    if r.kind == "menu":
        names = list((r.node.get("c") or {}).keys())
        if names:
            shown = ", ".join(f"`{n}`" for n in names[:16])
            lines.append(f"Contains: {shown}{', ...' if len(names) > 16 else ''}")
    else:
        required = r.node.get("r", [])
        if required:
            lines.append("Required: " + ", ".join(f"`{n}`" for n in required))
        optional = [n for n in (r.node.get("a") or {}) if n not in required]
        if optional:
            shown = ", ".join(f"`{n}`" for n in optional[:20])
            lines.append(f"Parameters: {shown}{', ...' if len(optional) > 20 else ''}")
    return "\n\n".join(line for line in lines if line)


def hover_at(document: Document, analysis: Analysis, offset: int) -> dict[str, Any] | None:
    """Hover for a menu, command, parameter or variable at the offset."""
    resolutions = analysis.commands.resolutions if analysis.commands is not None else []
    candidates = sorted((r for r in resolutions if r.start <= offset <= r.end), key=lambda r: r.end - r.start)
    if candidates:
        word = candidates[0]
        return {
            "contents": {"kind": "markdown", "value": _resolution_text(word)},
            "range": document.range_at(word.start, word.end),
        }

    reference = next((r for r in analysis.bound.references if r.start <= offset <= r.end), None)
    if reference is not None:
        resolution = reference.resolution
        declaration = resolution.declaration if resolution.kind in ("declared", "global-elsewhere", "local-elsewhere") else None
        if declaration is not None:
            line = document.position_at(declaration.start)["line"] + 1
            suffix = " but not in scope here" if resolution.kind == "local-elsewhere" else ""
            text = f"**${reference.name}**: {declaration.kind} variable, declared on line {line}{suffix}."
        else:
            text = f"**${reference.name}**: not declared in this file."
        return {"contents": {"kind": "markdown", "value": text}, "range": document.range_at(reference.start, reference.end)}
    declaration = next((d for d in analysis.bound.declarations if d.start <= offset <= d.end), None)
    if declaration is not None:
        return {
            "contents": {"kind": "markdown", "value": f"**{declaration.name}**: {declaration.kind} variable."},
            "range": document.range_at(declaration.start, declaration.end),
        }
    return None
