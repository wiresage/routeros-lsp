from __future__ import annotations

from routeros_lsp.features.hover import hover_at
from tests.helpers import with_caret


def hover(source: str) -> str | None:
    c = with_caret(source)
    result = hover_at(c.document, c.analysis, c.offset)
    return result["contents"]["value"] if result else None


def test_describes_a_menu_with_its_contents() -> None:
    text = hover("/i|p address print")
    assert text is not None
    assert "**/ip** menu" in text
    assert "IP addressing and routing" in text
    assert "`address`" in text


def test_describes_a_command_with_its_required_and_optional_parameters() -> None:
    text = hover("/ip address a|dd address=1.1.1.1/32 interface=ether1")
    assert text is not None
    assert "**/ip address add** command" in text
    assert "Create a new item" in text
    assert "Required: `address`, `interface`" in text
    assert "Parameters: `comment`, `disabled`" in text


def test_describes_a_parameter_with_its_type_and_values() -> None:
    text = hover("/ip address add dis|abled=yes address=1.1.1.1/32 interface=ether1")
    assert text is not None
    assert "**disabled** parameter of `/ip address add`" in text
    assert "Defines whether item is ignored or used" in text
    assert "Type: `yes | no`" in text
    assert "Values: `yes`, `no`" in text


def test_marks_a_required_parameter() -> None:
    assert "(required)" in (hover("/ip address add addr|ess=1.1.1.1/32 interface=ether1") or "")


def test_resolves_an_abbreviated_name_to_the_full_one() -> None:
    assert "**/ip address**" in (hover("/ip addr|ess pr") or "")
    assert "**/ip address print** command" in (hover("/ip address pr|") or "")


def test_describes_a_variable_and_where_it_was_declared() -> None:
    assert "local variable, declared on line 2" in (hover("{\n  :local abc 1\n  :put $a|bc\n}") or "")
    assert "not declared in this file" in (hover(":put $n|ope") or "")


def test_says_nothing_about_plain_text() -> None:
    assert hover(':put "hel|lo"') is None
