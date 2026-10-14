"""Files that RouterOS accepts.

``verdicts.json`` holds what ``/import file dry-run`` said about each file (research/tools/check_files.py). A file RouterOS
accepts must produce no finding at all: a false positive on valid input is the worst failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routeros_lsp.analyze import analyze

ROOT = Path(__file__).parent / "fixtures"
VERDICTS = json.loads((ROOT / "verdicts.json").read_text(encoding="utf-8"))
FILES = [path for folder in ("scripts", "crlf", "cr") for path in sorted((ROOT / folder).glob("*.rsc"))]


@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_has_no_findings(path: Path) -> None:
    verdict = VERDICTS.get(path.name)
    assert verdict is not None, f"no recorded verdict for {path.name}; run research/tools/check_files.py"
    assert verdict["valid"], f"RouterOS rejects {path.name}: {'; '.join(verdict['errors'])}"

    # newline="" keeps CR and CRLF line endings, which are the point of two of the folders
    with path.open(encoding="utf-8", newline="") as handle:
        text = handle.read()
    findings = [f"{f.rule} at {f.start}: {f.message}" for f in analyze(text).findings]
    assert findings == []


def test_the_fixture_folders_are_not_empty() -> None:
    assert len(FILES) >= 20
