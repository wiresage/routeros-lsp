"""The parser must survive anything: no exception, no hang, no tree that contradicts the text."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from routeros_lsp.syntax.ast import Node
from routeros_lsp.syntax.parser import parse
from routeros_lsp.syntax.walk import children, visit

HERE = Path(__file__).parent

PIECES = [
    '"', "$", "[", "]", "(", ")", "{", "}", "\\", "\n", "\r\n", ";", "#", "=", " ", ":", "/", "!", "-", "->", '"x"', "$(", "$[",
    "where", "\\\n", "é", "﻿",
]  # fmt: skip


def load_seeds() -> list[str]:
    seeds = [case["source"] for case in json.loads((HERE / "conformance" / "cases.json").read_text(encoding="utf-8"))]
    for directory in ("scripts", "crlf", "cr"):
        for path in sorted((HERE / "fixtures" / directory).glob("*.rsc")):
            # newline="" keeps the CR and CRLF fixtures as they are
            with path.open(encoding="utf-8", newline="") as handle:
                seeds.append(handle.read())
    return seeds


SEEDS = load_seeds()


def mutate(text: str, rng: random.Random) -> str:
    out = text
    for _ in range(1 + int(rng.random() * 6)):
        at = int(rng.random() * (len(out) + 1))
        kind = int(rng.random() * 4)
        if kind == 0:
            out = out[:at] + out[at + 1 + int(rng.random() * 8) :]
        elif kind == 1:
            out = out[:at] + PIECES[int(rng.random() * len(PIECES))] + out[at:]
        elif kind == 2:
            out = out[:at]
        else:
            a, b = int(rng.random() * (len(out) + 1)), int(rng.random() * (len(out) + 1))
            out = out[:at] + out[a:b] + out[at:]
    return out


def check_tree(text: str, root: Node) -> str | None:
    problem: list[str] = []

    def check(node: Node, parent: Node | None) -> bool | None:
        if problem:
            return False
        if node.start < 0 or node.end > len(text) or node.start > node.end:
            problem.append(f"{node.kind} has span {node.start}..{node.end} in a text of {len(text)}")
            return False
        if parent is not None and (node.start < parent.start or node.end > parent.end) and parent.kind != "string":
            problem.append(f"{node.kind} {node.start}..{node.end} escapes its {parent.kind} {parent.start}..{parent.end}")
            return False
        previous_end = -1
        for child in children(node):
            if child.start < previous_end:
                problem.append(f"children of {node.kind} overlap or are out of order at {child.start}")
                return False
            previous_end = child.end
        return None

    visit(root, check)
    return problem[0] if problem else None


def test_has_input_to_mutate() -> None:
    assert len(SEEDS) > 600


def test_never_throws_hangs_or_builds_an_inconsistent_tree_on_mutated_input() -> None:
    rng = random.Random(20261012)
    started = time.monotonic()
    for i in range(4000):
        text = mutate(rng.choice(SEEDS), rng)
        try:
            result = parse(text)
        except Exception as error:
            raise AssertionError(f"parse threw on iteration {i}: {error!r}\n{text!r}") from error
        problem = check_tree(text, result.script)
        assert problem is None, f"iteration {i}: {problem}\n{text!r}"
        for d in result.diagnostics:
            assert 0 <= d.start <= d.end <= len(text), f"iteration {i}: bad range {d.start}..{d.end}\n{text!r}"
    assert time.monotonic() - started < 60


def test_parses_a_large_file_quickly() -> None:
    line = '/ip firewall filter add action=accept chain=input comment="rule" connection-state=established,related\n'
    started = time.monotonic()
    result = parse(line * 20000)
    elapsed = time.monotonic() - started
    assert len(result.script.statements) == 20000
    assert result.diagnostics == []
    print(f"20000 lines parsed in {elapsed:.2f} s")
    assert elapsed < 15
