from __future__ import annotations

from routeros_lsp.document import Document


def doc(text: str) -> Document:
    return Document("file:///t.rsc", text)


def test_line_breaks_are_lf_crlf_and_cr() -> None:
    assert doc("a\nb\r\nc\rd").line_starts() == [0, 2, 5, 7]
    assert doc("").line_starts() == [0]
    assert doc("a\n").line_count() == 2


def test_converts_between_offsets_and_positions() -> None:
    d = doc("ab\ncd\n")
    assert d.position_at(0) == {"line": 0, "character": 0}
    assert d.position_at(4) == {"line": 1, "character": 1}
    assert d.position_at(6) == {"line": 2, "character": 0}
    assert d.position_at(99) == {"line": 2, "character": 0}
    assert d.offset_at({"line": 1, "character": 1}) == 4


def test_columns_past_the_end_of_a_line_stop_at_the_line_break() -> None:
    d = doc("ab\r\ncd")
    assert d.offset_at({"line": 0, "character": 50}) == 2
    assert d.offset_at({"line": 9, "character": 0}) == 6
    assert d.offset_at({"line": -1, "character": 3}) == 0


def test_a_character_outside_the_bmp_is_two_columns() -> None:
    d = doc("\U0001f600x")
    assert d.position_at(1) == {"line": 0, "character": 2}
    assert d.position_at(2) == {"line": 0, "character": 3}
    assert d.offset_at({"line": 0, "character": 2}) == 1
    # the middle of a surrogate pair rounds down to the start of the character
    assert d.offset_at({"line": 0, "character": 1}) == 0


def test_applies_ranged_and_whole_text_changes_and_counts_revisions() -> None:
    d = doc("hello world")
    before = d.revision
    d.apply_change({"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}}, "text": "bye"})
    assert d.text == "bye world"
    d.apply_change({"text": "new"})
    assert d.text == "new"
    assert d.revision == before + 2
    # a reversed range is read the right way round
    d.apply_change({"range": {"start": {"line": 0, "character": 3}, "end": {"line": 0, "character": 1}}, "text": ""})
    assert d.text == "n"
