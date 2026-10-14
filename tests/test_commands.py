from __future__ import annotations

from pathlib import Path

import pytest

from routeros_lsp.analyze import analyze
from routeros_lsp.schema.schema import Schema, match_name, suggest

schema = Schema.from_file(Path(__file__).parent / "fixtures" / "mini-schema.json")


def rules(text: str) -> list[str]:
    return [f.rule for f in analyze(text, schema=schema).findings if f.rule.startswith("schema/")]


def messages(text: str) -> list[str]:
    return [f.message for f in analyze(text, schema=schema).findings if f.rule.startswith("schema/")]


class TestMatchingNames:
    table = {"address": 1, "accounting": 2, "add": 3, "route": 4}

    def test_prefers_an_exact_match_then_a_unique_prefix(self) -> None:
        for word, name in [("add", "add"), ("rou", "route"), ("ac", "accounting")]:
            found = match_name(self.table, word)
            assert (found.kind, found.name) == ("found", name)

    def test_reports_ambiguity_and_absence(self) -> None:
        ambiguous = match_name(self.table, "a")
        assert ambiguous.kind == "ambiguous"
        assert ambiguous.candidates == ("accounting", "add", "address")
        assert match_name(self.table, "x").kind == "none"
        assert match_name(self.table, "").kind == "none"
        assert match_name(None, "a").kind == "none"

    def test_is_not_fooled_by_names_every_object_has(self) -> None:
        assert match_name(self.table, "constructor").kind == "none"
        assert match_name(self.table, "__class__").kind == "none"

    def test_suggests_close_names(self) -> None:
        assert suggest(["filter", "nat", "mangle"], "filtr") == ["filter"]
        assert suggest(["filter", "nat"], "zzzzzz") == []


class TestMenusAndCommands:
    @pytest.mark.parametrize(
        "text",
        ["/ip address print", "/ip/address/print", "/ip addr pr", "ip address print", ':put "x"', ':pu "x"', 'put "x"'],
    )
    def test_accepts_valid_lines_with_full_names_prefixes_and_either_path_style(self, text: str) -> None:
        assert rules(text) == []

    def test_reports_an_unknown_menu_or_command_and_suggests_the_closest_name(self) -> None:
        assert rules("/foo bar") == ["schema/unknown-command"]
        assert rules("/ip address prnt") == ["schema/unknown-command"]
        assert "Did you mean 'filter'?" in messages("/ip firewall filtr add")[0]

    def test_reports_an_ambiguous_abbreviation_as_an_error(self) -> None:
        (finding,) = analyze("/ip a print", schema=schema).findings
        assert (finding.rule, finding.severity) == ("schema/ambiguous-name", "error")
        assert "accounting, address" in finding.message

    def test_keeps_unknown_names_a_warning_by_default_because_the_database_depends_on_the_device(self) -> None:
        assert analyze("/foo bar", schema=schema).findings[0].severity == "warning"

    def test_requires_the_colon_for_a_global_command_inside_a_menu(self) -> None:
        # probes s14 to s17
        assert rules('/ip address\nput "x"') == ["schema/unknown-command"]
        assert "Global commands need a ':'" in messages('/ip address\nput "x"')[0]
        assert rules('/ip address\n:put "x"') == []

    def test_lets_a_colon_lead_into_a_menu_but_a_colon_line_does_not_become_the_current_path(self) -> None:
        assert rules(":ip address print") == []
        assert rules(":ip address\nprint") == ["schema/unknown-command"]


class TestMenuPathState:
    def test_lets_a_path_only_line_set_the_path_for_the_lines_after_it(self) -> None:
        # s3
        assert rules("/ip address\nprint") == []
        assert rules("/ip\naddress\nprint") == []
        assert rules("/ip address; print") == []

    def test_does_not_let_a_full_command_change_the_path(self) -> None:
        # s1, s2, s4, s5, s20
        assert rules("/ip address print\nadd address=1.1.1.1/32 interface=ether1") == ["schema/unknown-command"]
        assert rules("/ip address\n/ip route print\nadd address=1.1.1.1/32 interface=ether1") == []
        # still in /ip address, which has no dst-address or gateway
        assert "schema/unknown-parameter" in rules("/ip address\n/ip route print\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1")

    def test_resolves_relative_words_only_against_the_current_menu(self) -> None:
        # s11, s12
        assert rules("/ip address\nroute print") == ["schema/unknown-command"]
        assert rules("/ip address\nsystem identity print") == ["schema/unknown-command"]
        assert rules("/ip address\n/\nsystem identity print") == []

    def test_goes_up_with_dot_dot(self) -> None:
        # s10, s19
        assert rules("/ip address\n..\nroute print") == []
        assert rules("/ip address\n..route print") == []

    def test_carries_a_path_change_out_of_a_bare_block_and_a_statement_level_path_block(self) -> None:
        # l1, l12, l18
        assert rules("{ /ip route }\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1") == []
        assert rules("/ip { route }\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1") == []
        assert rules("/ip route\n{ /ip address }\nadd address=1.1.1.1/32 interface=ether1") == []

    @pytest.mark.parametrize(
        "construct",
        [":if (true) do={ /ip route }", ":put [/ip route]", ":local a { /ip route }", ":global f do={ /ip route }"],
    )
    def test_does_not_carry_a_change_out_of_bodies_and_arguments(self, construct: str) -> None:
        # l2 to l17
        assert "schema/unknown-command" in rules(f"{construct}\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1")

    def test_lets_bodies_and_arguments_start_from_the_current_path(self) -> None:
        # s26, s29
        assert rules("/ip address\n:if (true) do={ print }") == []
        assert rules("/ip address\n:put [print count-only]") == []

    def test_stops_reporting_relative_words_after_a_mistake_in_a_path_until_an_absolute_path_resets_it(self) -> None:
        assert rules("/ip nonsense\nprint\nadd address=1.1.1.1/32") == ["schema/unknown-command"]
        assert rules("/ip nonsense\n/ip address\nprint") == ["schema/unknown-command"]


class TestArguments:
    def test_accepts_named_parameters_flags_and_abbreviations(self) -> None:
        assert rules('/ip address add address=1.1.1.1/32 interface=ether1 comment="x"') == []
        assert rules("/ip address add addr=1.1.1.1/32 inter=ether1") == []
        assert rules("/ip address print detail count-only") == []
        assert rules("/ip address print det") == []

    def test_reports_an_unknown_parameter_and_suggests_one(self) -> None:
        assert rules("/ip address add address=1.1.1.1/32 interface=ether1 nope=1") == ["schema/unknown-parameter"]
        (message,) = messages("/ip address add adress=1.1.1.1/32 interface=ether1")
        assert "Did you mean 'address'?" in message

    def test_reports_a_parameter_given_twice_also_under_an_abbreviation(self) -> None:
        assert rules("/ip address add address=1.1.1.1/32 address=2.2.2.2/32 interface=ether1") == ["schema/duplicate-parameter"]
        assert rules("/ip address add address=1.1.1.1/32 addr=2.2.2.2/32 interface=ether1") == ["schema/duplicate-parameter"]

    def test_reports_more_unnamed_arguments_than_the_command_takes(self) -> None:
        assert rules(':put "a" "b"') == ["schema/unexpected-argument"]
        assert rules("/ip address add 1.1.1.1/32 interface=ether1") == ["schema/unexpected-argument"]
        assert rules("/ip address print nope") == ["schema/unexpected-argument"]
        assert rules("/ip address set 0 comment=x") == []
        assert rules("/ip address set 0 1 comment=x") == ["schema/unexpected-argument"]

    def test_reports_missing_required_parameters_counting_unnamed_values_for_them(self) -> None:
        assert rules("/ip address add") == ["schema/missing-required"]
        assert "interface" in messages("/ip address add address=1.1.1.1/32")[0]
        assert rules(":put") == ["schema/missing-required"]
        assert rules(':put "x"') == []
        assert rules("/ip address remove") == ["schema/missing-required"]
        assert rules("/ip address remove 0") == []
        assert rules("/ip address remove numbers=0") == []
        assert rules("/ip address remove [find]") == []

    def test_rejects_a_flag_written_with_a_value_and_a_valued_parameter_written_bare(self) -> None:
        # probes b5, b6, b13, b14
        assert rules("/ip address print detail=yes") == ["schema/flag-with-value"]
        assert rules("/ip address add address=1.1.1.1/32 interface=ether1 comment") == ["schema/parameter-needs-value"]
        assert rules("/ip address add address=1.1.1.1/32 interface=ether1 comm") == ["schema/parameter-needs-value"]

    def test_takes_a_bare_word_that_names_a_parameter_as_a_value_where_the_command_has_unnamed_values(self) -> None:
        # probes b1 to b3
        assert rules(":put message") == []
        assert rules(":put m") == []

    def test_does_not_look_past_where(self) -> None:
        assert rules('/ip address print where address~"1" and nonsense=1') == []

    def test_checks_the_commands_inside_bodies_substitutions_and_strings(self) -> None:
        assert rules(":if (true) do={ /nope x }") == ["schema/unknown-command"]
        assert rules(":put [/nope x]") == ["schema/unknown-command"]
        assert rules(':put "x $[/nope x]"') == ["schema/unknown-command"]

    def test_can_be_turned_off_or_made_strict(self) -> None:
        assert analyze("/foo bar", schema=None).findings == []
        strict = analyze("/foo bar", schema=schema, severities={"schema/unknown-command": "error"})
        assert strict.findings[0].severity == "error"
