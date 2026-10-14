"""Looking things up in a bind result by source offset."""

from __future__ import annotations

from .binder import BindResult, Declaration, Scope


def scope_at(bound: BindResult, offset: int) -> Scope | None:
    """The innermost scope that covers the offset."""
    best: Scope | None = None
    for scope in bound.scopes:
        if offset < scope.start or offset > scope.end:
            continue
        if best is None or scope.end - scope.start <= best.end - best.start:
            best = scope
    return best


def variables_at(bound: BindResult, offset: int) -> list[Declaration]:
    """The variables a command at ``offset`` can read.

    Those declared before it in the scopes around it, up to the edge of a function body (which only sees its own), and every
    global declared earlier in the file, which RouterOS finds by name.
    """
    found: dict[str, Declaration] = {}
    chain: set[int] = set()
    crossed_at: dict[int, bool] = {}
    crossed = False
    s = scope_at(bound, offset)
    while s is not None:
        chain.add(id(s))
        crossed_at[id(s)] = crossed
        if s.kind == "function":
            crossed = True
        s = s.parent
    for d in bound.declarations:
        if d.from_offset > offset:
            continue
        # a local of a scope around a function is out of reach of the function; a global is visible from everywhere
        visible = d.kind == "global" or (id(d.scope) in chain and not crossed_at[id(d.scope)])
        if visible:
            found[d.name] = d
    return sorted(found.values(), key=lambda d: (d.name.casefold(), d.name))
