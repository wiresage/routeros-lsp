"""Walking the syntax tree."""

from __future__ import annotations

from collections.abc import Callable

from .ast import Binary, Brace, CommandPart, ExpressionPart, Group, Named, Node, Script, Statement, StringLit, Subst, Unary


def children(node: Node) -> list[Node]:
    """The direct children of a node, in source order."""
    if isinstance(node, Script):
        return list(node.statements)
    if isinstance(node, Statement):
        return list(node.elements)
    if isinstance(node, StringLit):
        out: list[Node] = []
        for part in node.parts:
            if isinstance(part, ExpressionPart):
                out.append(part.group)
            elif isinstance(part, CommandPart):
                out.append(part.subst)
        return out
    if isinstance(node, Subst | Brace):
        return list(node.body)
    if isinstance(node, Group):
        return list(node.exprs)
    if isinstance(node, Named):
        return [node.name] if node.value is None else [node.name, node.value]
    if isinstance(node, Binary):
        return [node.left, node.right]
    if isinstance(node, Unary):
        return [node.operand]
    return []


def visit(node: Node, callback: Callable[[Node, Node | None], bool | None], parent: Node | None = None) -> None:
    """Depth-first walk. Return False from the callback to skip a node's children."""
    if callback(node, parent) is False:
        return
    for child in children(node):
        visit(child, callback, node)


def ancestors_at(root: Node, offset: int) -> list[Node]:
    """The nodes that contain ``offset``, outermost first.

    An offset on the boundary between two nodes counts for both, so a caret right after a word is inside that word.
    """
    chain: list[Node] = []
    node: Node | None = root
    while node is not None:
        chain.append(node)
        nxt: Node | None = None
        for child in children(node):
            if child.start <= offset <= child.end and child.kind != "missing":
                nxt = child
                break
        node = nxt
    return chain
