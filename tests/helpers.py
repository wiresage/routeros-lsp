"""Shared by the feature tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from routeros_lsp.analyze import Analysis, analyze
from routeros_lsp.document import Document
from routeros_lsp.schema.schema import Schema

FIXTURES = Path(__file__).parent / "fixtures"

MINI_SCHEMA = Schema.from_file(FIXTURES / "mini-schema.json")


@dataclass
class Caret:
    document: Document
    analysis: Analysis
    offset: int
    position: dict[str, int]


def with_caret(source: str, **options: Any) -> Caret:
    """Splits "text with a | caret" into the document and the caret offset."""
    offset = source.find("|")
    assert offset >= 0, f"no caret marker in {source!r}"
    text = source[:offset] + source[offset + 1 :]
    document = Document("file:///t.rsc", text, 1, "routeros")
    options.setdefault("schema", MINI_SCHEMA)
    return Caret(document, analyze(text, **options), offset, document.position_at(offset))
