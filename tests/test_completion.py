from __future__ import annotations

from typing import Any

from routeros_lsp.features.completion import completions
from tests.helpers import MINI_SCHEMA, with_caret


def items(source: str) -> list[dict[str, Any]]:
    c = with_caret(source)
    return completions(c.document, c.analysis, MINI_SCHEMA, c.position)


def labels(source: str) -> list[str]:
    return [i["label"] for i in items(source)]


class TestMenusAndCommands:
    def test_offers_the_top_level_in_an_empty_file_and_after_a_colon(self) -> None:
        assert {"ip", "system", "put", "local"} <= set(labels("|"))
        # a colon reaches menus as well as global commands: ":log info" is a command of the menu log
        assert {"if", "local", "put", "ip", "system"} <= set(labels(":|"))

    def test_offers_the_children_of_the_menu_written_so_far(self) -> None:
        assert sorted(labels("/ip |")) == ["accounting", "address", "firewall", "route"]
        assert sorted(labels("/ip address |")) == ["add", "find", "print", "remove", "set"]
        assert "add" in labels("ip address |")

    def test_replaces_the_word_being_typed(self) -> None:
        first = items("/ip ad|")[0]
        assert first["label"] == "address"
        assert first["textEdit"] == {
            "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 6}},
            "newText": "address",
        }

    def test_continues_a_path_set_on_an_earlier_line(self) -> None:
        assert "print" in labels("/ip address\n|")
        assert "print" in labels("/ip address\n:if (true) do={ | }")
        assert "print" not in labels("/ip address print\n|")

    def test_starts_again_from_the_top_level_after_a_colon_inside_a_menu(self) -> None:
        assert {"if", "local", "put", "ip"} <= set(labels("/ip address\n:|"))
        assert "print" not in labels("/ip address\n:|")

    def test_describes_each_item(self) -> None:
        address = next(i for i in items("/ip |") if i["label"] == "address")
        assert address["detail"] == "IP address settings"
        assert next(i for i in items("/ip address |") if i["label"] == "add")["kind"] == 3


class TestParametersAndValues:
    def test_offers_the_parameters_of_a_command_required_ones_first(self) -> None:
        listed = items("/ip address add |")
        assert [i["label"] for i in listed] == ["address", "interface", "comment", "disabled"]
        assert listed[0]["detail"] == "required, A.B.C.D (IP address)"
        assert listed[0]["textEdit"]["newText"] == "address="
        assert listed[0]["sortText"] < listed[2]["sortText"]

    def test_leaves_out_the_parameters_that_are_already_given(self) -> None:
        assert labels("/ip address add address=1.1.1.1/32 |") == ["interface", "comment", "disabled"]

    def test_completes_the_part_of_a_parameter_name_that_is_typed(self) -> None:
        # every parameter is offered; the editor narrows the list by what is typed, and the edit replaces that text
        item = next(i for i in items("/ip address add inter|") if i["label"] == "interface")
        edit = item["textEdit"]
        assert (edit["range"]["start"]["character"], edit["range"]["end"]["character"]) == (16, 21)
        assert edit["newText"] == "interface="

    def test_offers_the_known_values_after_the_equals_sign(self) -> None:
        assert labels("/ip address add disabled=|") == ["yes", "no"]
        assert labels("/ip address add disabled=y|") == ["yes", "no"]
        assert labels("/ip address add comment=|") == []

    def test_writes_a_flag_without_an_equals_sign(self) -> None:
        detail = next(i for i in items("/ip address print |") if i["label"] == "detail")
        assert detail["textEdit"]["newText"] == "detail"

    def test_offers_nothing_in_a_where_expression(self) -> None:
        assert labels("/ip address print where |") == []


class TestVariables:
    def test_offers_the_variables_in_scope_after_a_dollar_sign(self) -> None:
        assert labels("{ :local abc 1; :local abd 2; :put $| }") == ["abc", "abd"]
        assert labels("{ :local abc 1; :put $a| }") == ["abc"]

    def test_offers_a_global_declared_earlier_but_not_a_local_of_a_block_that_ended(self) -> None:
        assert labels(":global g 1\n{ :local inner 1 }\n:put $|") == ["g"]

    def test_does_not_offer_the_locals_of_the_code_around_a_function(self) -> None:
        assert labels("{ :local outer 1; :global f do={ :local own 2; :put $| } }") == ["own"]

    def test_works_inside_a_string(self) -> None:
        assert labels('{ :local abc 1; :put "x $a|" }') == ["abc"]


class TestWhereNothingIsOffered:
    def test_stays_quiet_in_comments_and_strings(self) -> None:
        assert labels("# /ip |") == []
        assert labels(':put "/ip |"') == []

    def test_stays_quiet_when_the_path_is_unknown(self) -> None:
        assert labels("/nonsense\n|") == []

    def test_returns_nothing_without_a_command_database(self) -> None:
        c = with_caret("/ip |")
        assert completions(c.document, c.analysis, None, c.position) == []
