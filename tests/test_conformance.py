"""Replays the answers RouterOS 7.21.4 gave to every ``check`` probe (``/import ... dry-run``).

The corpus is built by ``research/tools/build_corpus.py``. A case the implementation does not match goes in ``known-gaps.json``
with a reason, and the test fails when a listed case starts passing, so the list cannot rot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routeros_lsp.analyze import analyze

HERE = Path(__file__).parent / "conformance"
CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
GAPS: dict[str, str] = json.loads((HERE / "known-gaps.json").read_text(encoding="utf-8"))

# The recorded answers come from the device itself, where an unknown name is an error. The server reports those as warnings
# because its command database comes from a CHR (docs/configuration.md), so here they count as errors.
AS_THE_DEVICE = {"schema/unknown-command": "error", "schema/unknown-parameter": "error"}


def agrees(case: dict) -> bool:
    failed = any(f.severity == "error" for f in analyze(case["source"], severities=AS_THE_DEVICE).findings)
    return failed == (not case["valid"])


def test_corpus_is_present() -> None:
    assert len(CASES) > 800


@pytest.mark.parametrize("case", [c for c in CASES if c["id"] not in GAPS], ids=lambda c: c["id"])
def test_agrees_with_the_router(case: dict) -> None:
    verdict = "OK" if case["valid"] else case.get("message")
    assert agrees(case), f"{case['note']}; the router said: {verdict}; source: {case['source']!r}"


@pytest.mark.parametrize("case", [c for c in CASES if c["id"] in GAPS], ids=lambda c: c["id"])
def test_known_gap_is_still_a_gap(case: dict) -> None:
    assert not agrees(case), f"{case['id']} now agrees with the router; remove it from known-gaps.json"


def test_every_known_gap_is_in_the_corpus() -> None:
    assert set(GAPS) <= {c["id"] for c in CASES}
