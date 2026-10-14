"""These tests are about variables only, so the command database is left out."""

from __future__ import annotations

from typing import Any

import pytest

from routeros_lsp.analyze import Analysis
from routeros_lsp.analyze import analyze as analyze_with_schema


def analyze(text: str, **options: Any) -> Analysis:
    return analyze_with_schema(text, schema=None, **options)


def rules(text: str, **options: Any) -> list[str]:
    return [f.rule for f in analyze(text, **options).findings]


# Probe ids refer to research/suites/suite14_declare.py and suite13_scope.py; each was judged by /import dry-run.
ACCEPTED_SETS = [
    ("d1: local on the same line", ":local a; :set a 1"),
    ("d2: global on the same line", ":global a; :set a 1"),
    ("d4: block inside the declaring block", "{ :local a; { :set a 1 } }"),
    ("d6: do= of the declaring block", ":local a; :if (true) do={ :set a 1 }"),
    ("d7: :for variable", ":for i from=1 to=2 do={ :set i 5 }"),
    ("d8: :foreach variable", ":foreach i in={1;2} do={ :set i 5 }"),
    ("d9: :foreach k,v", ":foreach k,v in={1;2} do={ :set v 5 }"),
    ("d12: local inside a function", ":global f do={ :local a; :set a 1 }"),
    ("d14: global redeclared in a function", ":global f do={ :global g; :set g 1 }"),
    ("d16: through $a", ":local a; :set $a 1"),
    ("d17: array element", ":local a {1;2}; :set ($a->0) 5"),
    ("d19: quoted name", ':local "a b"; :set "a b" 1'),
    ("d20: undeclared quoted name", ':set "a b" 1'),
    ("d21: inside a substitution", ":local a; [:set a 1]"),
    ("d23: :onerror variable", ":onerror e in={ } do={ :set e 1 }"),
    ("d25: outer local inside :do", ":local a; :do { :set a 1 } on-error={ }"),
    ("d26: with no value", ":local a; :set a"),
    ("d29: global then local", ":global a; :local a; :set a 1"),
    ("d36: outer local inside :while", ":local t; :while (false) do={ :set t 1 }"),
    ("d37: outer loop variable", ":for i from=1 to=2 do={ :for j from=1 to=2 do={ :set i 1 } }"),
    ("a backslash join keeps one line", ":local a; \\\n:set a 1"),
    ("a block that spans lines is one scope", ":local a; {\n  :set a 1\n}"),
]

REJECTED_SETS = [
    ("v5: never declared", ':set nope "x"'),
    ("d3: declared after", ":set a 1; :local a"),
    ("d5: inner block ended", "{ { :local a }; :set a 1 }"),
    ("d10: function argument", ":global f do={ :set a 5 }"),
    ("d11: positional argument", ":global f do={ :set 1 5 }"),
    ("d13: global of the code around a function", ":global g; :global f do={ :set g 1 }"),
    ("d15: local of the code around a function", ":local a; :global f do={ :set a 1 }"),
    ("d30: lease variable", ":set leaseBound 1"),
    ("d32: inside a declaration value", ":local a [:set b 1]"),
    ("d34: local of an outer function", ":global f do={ :local x; :local g do={ :set x 1 } }"),
    ("d38: inside :retry", ":retry command={ :set q 1 } delay=1 max=1"),
    ("h25: global from an earlier line", ":global g 1\n:set g 2"),
    ("h26: global declared empty on an earlier line", ":global g\n:set g 2"),
    ("case matters", ':local "A"; :set a 1'),
]


class TestSetNeedsADeclarationInScope:
    @pytest.mark.parametrize("text", [t for _, t in ACCEPTED_SETS], ids=[n for n, _ in ACCEPTED_SETS])
    def test_accepts(self, text: str) -> None:
        assert rules(text) == []

    @pytest.mark.parametrize("text", [t for _, t in REJECTED_SETS], ids=[n for n, _ in REJECTED_SETS])
    def test_rejects(self, text: str) -> None:
        assert "vars/set-undeclared" in rules(text)

    def test_does_not_check_the_base_of_an_array_element_which_is_only_read(self) -> None:
        # probe d18
        assert rules(":set ($nope->0) 5") == ["vars/undeclared-read"]

    def test_explains_the_line_and_function_rules_in_the_message(self) -> None:
        (line,) = analyze(":global g 1\n:set g 2").findings
        assert "each line of an imported file is its own scope" in line.message
        (fn,) = analyze(":local a; :global f do={ :set a 1 }").findings
        assert "A function cannot set variables of the code around it" in fn.message

    def test_lets_the_whole_file_share_one_scope_in_script_mode(self) -> None:
        assert rules(":global g 1\n:set g 2", scope="script") == []
        assert "vars/set-undeclared" in rules(":local a\n:global f do={ :set a 1 }", scope="script")


class TestReadingAVariable:
    def test_stays_quiet_about_declared_variables(self) -> None:
        assert rules(":local a 1; :put $a") == []
        assert rules('{\n:local a 1\n:put $a\n:put "v=$a"\n:put ($a + 1)\n}') == []
        assert rules(":foreach i in={1;2} do={ :put $i }") == []
        assert rules(":global g 1\n:put $g") == []

    def test_warns_once_at_the_first_read_about_a_variable_that_is_never_declared(self) -> None:
        (finding,) = analyze(':put $nope\n:put $nope\n:put "x $nope"').findings
        assert (finding.rule, finding.severity, finding.start, finding.end) == ("vars/undeclared-read", "warning", 5, 10)
        assert "2 more times" in finding.message

    def test_warns_about_a_local_read_on_a_later_line_of_an_imported_file(self) -> None:
        # probe q1
        findings = analyze(":local a 1\n:put $a\n:put $a").findings
        assert [f.rule for f in findings] == ["vars/local-out-of-scope"]
        assert "1 more time" in findings[0].message

    def test_does_not_warn_when_the_local_is_in_the_same_block_or_a_block_around_it(self) -> None:
        assert rules("{\n  :local a 1\n  :if (true) do={ :put $a }\n}") == []

    def test_treats_a_global_as_readable_from_anywhere_in_the_file(self) -> None:
        # probes q2 and q3
        assert rules(":global g 5\n:global f do={ :put $g }") == []
        assert rules(":global g 5\n:put $g") == []

    def test_does_not_check_reads_inside_a_function_where_a_name_may_be_an_argument(self) -> None:
        # probes q5, q7, q8
        assert rules(":global f do={ :put $a; :put $1; :put $anything }") == []

    def test_exempts_positional_names_and_the_configured_context_variables(self) -> None:
        assert rules(":put $1") == []
        assert rules(":if ($leaseBound = 1) do={ :put $leaseActIP }") == []
        assert rules(":put $custom", context_variables=["custom"]) == []
        assert rules(":put $custom") == ["vars/undeclared-read"]

    def test_shares_one_scope_in_script_mode(self) -> None:
        assert rules(":local a 1\n:put $a", scope="script") == []

    def test_sees_a_variable_named_with_quotes(self) -> None:
        assert rules('{ :local "my var" 1; :put $"my var" }') == []
        assert rules(':put $"my var"') == ["vars/undeclared-read"]

    def test_declares_a_name_only_after_its_own_value_is_read(self) -> None:
        assert rules(":local a $a") == ["vars/undeclared-read"]


class TestVariableNames:
    @pytest.mark.parametrize(
        ("text", "offset"),
        [
            (":local a_b", 8),
            (":local a-b", 8),
            (":local a.b", 8),
            (":global a:b", 9),
            (":foreach a_b in={1} do={ }", 10),
            (":foreach a,b_c in={1} do={ }", 12),
            (":for a-b from=1 to=2 do={ }", 6),
            (":local a,b", 8),
        ],
    )
    def test_rejects_at_the_offending_character(self, text: str, offset: int) -> None:
        finding = next(f for f in analyze(text).findings if f.rule == "vars/invalid-name")
        assert finding.start == offset

    def test_rejects_a_dollar_where_a_name_is_declared(self) -> None:
        assert "vars/invalid-name" in rules(":local $a")

    @pytest.mark.parametrize("text", [':local "a_b"', ":local 1a", ":local A1", ":foreach a,b in={1} do={ }", ':set "a-b" 1'])
    def test_accepts(self, text: str) -> None:
        assert "vars/invalid-name" not in rules(text)

    def test_warns_about_keywords_as_names_because_the_documentation_reserves_them(self) -> None:
        findings = analyze(":local and 1; :local or 2; :local in 3").findings
        assert len([f for f in findings if f.rule == "vars/keyword-name"]) == 3
        assert findings[0].severity == "warning"


class TestSeverityOverrides:
    def test_can_turn_a_rule_off_or_change_its_level(self) -> None:
        assert rules(":put $nope", severities={"vars/undeclared-read": "off"}) == []
        assert analyze(":put $nope", severities={"vars/undeclared-read": "error"}).findings[0].severity == "error"
