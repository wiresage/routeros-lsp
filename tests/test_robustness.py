"""Input that is long rather than deeply bracketed must not run into the recursion limit.

An operator chain such as ``1+1+1+...`` is parsed in a loop, but it becomes a tree as deep as the chain is long, so every pass over
the tree has to walk it without recursing. The parser raises the recursion limit to 4,000; these chains are far longer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from routeros_lsp.analyze import analyze, bundled_schema
from routeros_lsp.document import Document
from routeros_lsp.features.completion import completions
from routeros_lsp.features.folding import folding_ranges
from routeros_lsp.features.hover import hover_at
from routeros_lsp.features.symbols import document_symbols
from routeros_lsp.syntax.ast import Node
from routeros_lsp.syntax.parser import parse
from routeros_lsp.syntax.walk import children, visit

#: several times the recursion limit
LONG = 20_000

CASES = json.loads((Path(__file__).parent / "conformance" / "cases.json").read_text(encoding="utf-8"))


def chain(operator: str, operand: str, count: int = LONG) -> str:
    return f":put ({operator.join([operand] * count)})\n"


@pytest.mark.parametrize(
    ("operator", "operand", "rules"),
    [
        pytest.param("+", "1", [], id="numbers"),
        pytest.param(" . ", '"x"', [], id="strings"),
        pytest.param(" && ", "$a", ["vars/undeclared-read"], id="logical-and-variables"),
        pytest.param(" = ", "$a", ["vars/undeclared-read"], id="comparisons"),
    ],
)
def test_a_long_operator_chain_is_analysed_to_the_end(operator: str, operand: str, rules: list[str]) -> None:
    result = analyze(chain(operator, operand))
    assert [f.rule for f in result.findings] == rules
    if rules:
        # the first read is reported once, and the count proves every operand was visited
        assert f"It is read {LONG - 1} more times" in result.findings[0].message


def test_a_finding_at_the_far_end_of_a_long_chain_is_still_found() -> None:
    text = ":put (1" + "+1" * LONG + "+$late)\n"
    (finding,) = analyze(text).findings
    assert finding.rule == "vars/undeclared-read"
    assert text[finding.start : finding.end] == "$late"


def test_every_feature_copes_with_a_long_chain() -> None:
    text = chain("+", "1")
    result = analyze(text)
    document = Document("file:///chain.rsc", text)
    middle = len(text) // 2
    assert folding_ranges(document, result.script) == []
    assert document_symbols(document, result.script) == []
    assert hover_at(document, result, middle) is None
    assert isinstance(completions(document, result, bundled_schema(), document.position_at(middle)), list)


def reference_walk(node: Node) -> Iterator[Node]:
    yield node
    for child in children(node):
        yield from reference_walk(child)


@pytest.mark.parametrize("case", [c for c in CASES if len(c["source"]) < 400][:300], ids=lambda c: c["id"])
def test_visit_keeps_the_order_of_a_plain_recursive_walk(case: dict) -> None:
    script = parse(case["source"]).script
    seen: list[Node] = []
    visit(script, lambda node, _parent: seen.append(node))
    assert seen == list(reference_walk(script))


def test_visit_reports_each_parent_and_skips_the_children_of_a_node_when_asked() -> None:
    script = parse(":put ($a + ($b * 2))\n").script
    pairs: list[tuple[str, str | None]] = []

    def callback(node: Node, parent: Node | None) -> bool | None:
        pairs.append((node.kind, parent.kind if parent is not None else None))
        return False if node.kind == "group" and parent is not None and parent.kind == "binary" else None

    visit(script, callback)
    assert pairs == [
        ("script", None),
        ("statement", "script"),
        ("word", "statement"),
        ("group", "statement"),
        ("binary", "group"),
        ("variable", "binary"),
        ("group", "binary"),  # the inner group is visited, its children are not
    ]


def test_visit_walks_a_tree_deeper_than_the_recursion_limit() -> None:
    script = parse(chain("+", "1")).script
    count = 0

    def callback(_node: Node, _parent: Node | None) -> None:
        nonlocal count
        count += 1

    visit(script, callback)
    assert count > LONG
