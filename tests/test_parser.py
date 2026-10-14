from __future__ import annotations

from typing import cast

import pytest

from routeros_lsp.syntax.ast import Binary, Brace, Expr, Group, Named, Statement, StringLit, Variable, Word
from routeros_lsp.syntax.parser import parse


def statements(text: str) -> list[Statement]:
    return parse(text).script.statements


def first(text: str) -> Statement:
    found = statements(text)
    assert found, f"no statement in {text!r}"
    return found[0]


def rules(text: str) -> list[str]:
    return [d.rule for d in parse(text).diagnostics]


def group(text: str) -> Group:
    for element in first(text).elements:
        if isinstance(element, Group):
            return element
    raise AssertionError("no group")


def show(e: Expr) -> str:
    """Renders an expression with explicit grouping, to compare precedence."""
    if isinstance(e, Binary):
        return f"({show(e.left)} {e.op} {show(e.right)})"
    if e.kind == "unary":
        return f"{e.op}{show(e.operand)}"  # type: ignore[union-attr]
    if isinstance(e, Word):
        return e.text
    if isinstance(e, Variable):
        return f"${e.name}"
    if isinstance(e, StringLit):
        return f'"{e.value}"'
    if e.kind == "missing":
        return "?"
    return e.kind


class TestStatementsAndElements:
    def test_splits_prefix_path_words_and_arguments(self) -> None:
        s = first("/ip address add address=10.0.0.1/24 interface=ether1")
        assert s.prefix == "/"
        assert [e.kind for e in s.elements] == ["word", "word", "word", "named", "named"]
        named = cast(Named, s.elements[3])
        assert isinstance(named.name, Word) and named.name.text == "address"
        assert isinstance(named.value, Word) and named.value.text == "10.0.0.1/24"

    def test_reads_the_global_command_prefix_with_or_without_a_space(self) -> None:
        assert first(":put 1").prefix == ":"
        element = first(": put 1").elements[0]
        assert isinstance(element, Word) and element.text == "put"
        assert first("put 1").prefix is None

    def test_separates_statements_on_newlines_semicolons_and_all_three_line_endings(self) -> None:
        assert len(statements(":put 1;:put 2\n:put 3\r\n:put 4\r:put 5")) == 5

    def test_keeps_the_menu_path_across_lines_as_separate_statements(self) -> None:
        listed = statements("/ip address\nadd address=1.1.1.1/32\nprint")
        assert [s.prefix for s in listed] == ["/", None, None]

    def test_allows_an_omitted_value_and_a_space_after_the_equals_sign(self) -> None:
        a, b = statements("/system identity set name=\n/ip address add comment= x")
        assert cast(Named, a.elements[3]).value is None
        value = cast(Named, b.elements[3]).value
        assert value is not None and value.kind == "word"

    def test_joins_lines_that_end_in_a_backslash_with_crlf_as_well(self) -> None:
        assert len(statements(":put \\\n  1")) == 1
        assert len(statements(":put \\\r\n  1")) == 1
        assert len(statements(":put \\ \n  1")) == 1

    def test_treats_hash_only_as_a_comment_at_the_start_of_a_command(self) -> None:
        assert len(statements("# one\n:put 1; # two\n{ # three\n}")) == 2
        assert rules(":put a#b") == []
        assert rules(":put 1 # comment") == ["syntax/trailing-comment"]

    def test_parses_an_empty_file_and_a_file_of_only_comments(self) -> None:
        assert statements("") == []
        assert statements("# only a comment") == []


class TestStrings:
    @staticmethod
    def string(text: str) -> StringLit:
        element = first(f":put {text}").elements[1]
        assert isinstance(element, StringLit)
        return element

    def test_decodes_escapes(self) -> None:
        assert self.string(r'"a\tb\n\"\\\$\_\41"').value == 'a\tb\n"\\$ A'

    def test_records_interpolation_parts(self) -> None:
        s = self.string('"x $name $(1+2) $[:len "a"]"')
        assert [p.kind for p in s.parts] == ["text", "variable", "text", "expression", "text", "command"]
        assert s.value == "x   "

    def test_removes_a_backslash_line_join_and_the_next_line_indentation(self) -> None:
        assert self.string('"a\\\n    b"').value == "ab"

    def test_accepts_a_raw_line_break_and_non_ascii_text_inside_a_string(self) -> None:
        assert rules(':put "one\ntwo é"') == []

    def test_reports_an_unterminated_string_at_its_opening_quote(self) -> None:
        (d,) = parse(':put "abc').diagnostics
        assert (d.rule, d.start, d.end) == ("syntax/unterminated-string", 5, 6)

    @pytest.mark.parametrize(
        ("inside", "rule"),
        [
            ("\\q", "syntax/invalid-escape"),
            ("\\4f", "syntax/invalid-escape"),
            ("\\4", "syntax/invalid-escape"),
            ("$ ", "syntax/bad-interpolation"),
            ("$-", "syntax/bad-interpolation"),
        ],
    )
    def test_rejects_bad_escapes_and_interpolations(self, inside: str, rule: str) -> None:
        assert rule in rules(f':put "a{inside}b"')

    def test_accepts_every_documented_escape(self) -> None:
        assert rules(r':put "\" \\ \n \r \t \$ \_ \a \b \f \v \? \0A \FF"') == []


class TestVariables:
    def test_reads_plain_and_quoted_names(self) -> None:
        els = first(':put $a $"b c" $1').elements
        a, b, one = els[1], els[2], els[3]
        assert isinstance(a, Variable) and (a.name, a.quoted) == ("a", False)
        assert isinstance(b, Variable) and (b.name, b.quoted) == ("b c", True)
        assert isinstance(one, Variable) and one.name == "1"

    def test_ends_a_name_at_the_first_character_that_is_not_a_letter_or_digit(self) -> None:
        assert rules(":put $a_b") == ["syntax/adjacent-tokens"]
        assert rules(":put $a-b") == ["syntax/adjacent-tokens"]

    def test_rejects_a_bare_dollar_and_dollar_paren_outside_a_string(self) -> None:
        assert rules(":put $") == ["syntax/bare-dollar"]
        assert rules(":put $(1+2)") == ["syntax/dollar-expression-outside-string"]
        assert rules(':put $[:len "a"]') == ["syntax/dollar-expression-outside-string"]


class TestExpressions:
    def test_uses_the_observed_precedence(self) -> None:
        assert show(group(":put (1 + 2 * 3)").exprs[0]) == "(1 + (2 * 3))"
        assert show(group(":put (1 - 2 - 3)").exprs[0]) == "((1 - 2) - 3)"
        assert show(group(":put (a = 1 && b = 2 || c)").exprs[0]) == "(((a = 1) && (b = 2)) || c)"
        assert show(group(':put ("a" . "b" = "ab")').exprs[0]) == '(("a" . "b") = "ab")'
        assert show(group(":put (!$a && $b)").exprs[0]) == "(!$a && $b)"

    def test_reads_word_operators_and_the_arrow(self) -> None:
        e = group(":put ($a and $b or $c->0)").exprs[0]
        assert isinstance(e, Binary) and e.op == "or"
        assert show(e) == "(($a and $b) or ($c -> 0))"

    def test_keeps_addresses_prefixes_and_times_as_single_words(self) -> None:
        assert show(group(":put (10.0.0.0/8)").exprs[0]) == "10.0.0.0/8"
        assert show(group(":put (1d2h3m)").exprs[0]) == "1d2h3m"
        assert show(group(":put (00:10:00)").exprs[0]) == "00:10:00"
        assert show(group(":put (::1)").exprs[0]) == "::1"

    def test_accepts_operands_next_to_each_other(self) -> None:
        assert len(group(":put ($a $b)").exprs) == 2
        assert rules(":put ($aand$b)") == []

    @pytest.mark.parametrize(
        ("text", "rule"),
        [
            (":put ()", "syntax/empty-expression"),
            (":put (5 -)", "syntax/expected-operand"),
            (":put (1 + + 2)", "syntax/expected-operand"),
            (":put (* 2)", "syntax/expected-operand"),
            (":put (1 == 2)", "syntax/expected-operand"),
            (":put (1 ; 2)", "syntax/unexpected-token"),
            (":put (1\n+ 2)", "syntax/newline-in-parens"),
        ],
    )
    def test_rejects(self, text: str, rule: str) -> None:
        assert rule in rules(text)

    def test_accepts_a_backslash_join_inside_parentheses(self) -> None:
        assert rules(":put (1 \\\n + 2)") == []


class TestBracketsAndRecovery:
    def test_reports_a_missing_closer_at_the_opener_and_keeps_parsing(self) -> None:
        r = parse("{\n:put 1\n:put 2\n")
        assert [(d.rule, d.start, d.end) for d in r.diagnostics] == [("syntax/missing-closer", 0, 1)]
        brace = cast(Brace, r.script.statements[0].elements[0])
        assert len(brace.body) == 2
        assert brace.closed is False

    def test_closes_an_inner_construct_at_the_closer_of_an_outer_one(self) -> None:
        r = parse('{ :put [:len "a" }\n:put 2')
        assert [d.rule for d in r.diagnostics] == ["syntax/missing-closer"]
        assert len(r.script.statements) == 2

    def test_tolerates_a_stray_brace_or_bracket_with_a_warning_and_rejects_a_stray_paren(self) -> None:
        assert rules("}") == ["syntax/stray-closer"]
        assert rules(":put 1 ]") == ["syntax/stray-closer"]
        assert rules(")") == ["syntax/unexpected-closer"]

    def test_marks_a_brace_on_its_own_line_as_a_block_and_a_brace_argument_as_unknown(self) -> None:
        block = cast(Brace, first("{ :put 1 }").elements[0])
        arg = cast(Brace, first(":local a {1;2}").elements[2])
        assert block.role == "block"
        assert arg.role == "unknown"
        value = cast(Named, first(":if (true) do={ }").elements[2]).value
        assert isinstance(value, Brace) and value.role == "block"

    def test_parses_pairs_in_an_array_and_rejects_them_in_a_block(self) -> None:
        assert rules(':local a {a=1; "b c"=2; d={e=3}}') == []
        assert rules("{ a=1 }") == ["syntax/statement-starts-with-pair"]
        assert rules(":if (true) do={ :put 1 }\nelse={ :put 2 }") == ["syntax/statement-starts-with-pair"]

    def test_stays_bounded_on_deeply_nested_input(self) -> None:
        r = parse("(" * 5000)
        assert any(d.rule == "syntax/too-deeply-nested" for d in r.diagnostics)


class TestLayoutRules:
    @pytest.mark.parametrize(
        ("text", "rule"),
        [
            (":put 1 :put 2", "syntax/missing-separator"),
            (":if (true) do={ :put 1 } :put 2", "syntax/missing-separator"),
            ("/ip address add gateway = 3.3.3.3", "syntax/space-before-equals"),
            ("/ip address add gateway =3.3.3.3", "syntax/space-before-equals"),
            ("/system identity set name=a=b", "syntax/unexpected-equals"),
            (':log info a"b"', "syntax/adjacent-tokens"),
            (':log info "a"b', "syntax/adjacent-tokens"),
            (":log info (1)(2)", "syntax/adjacent-tokens"),
            (":log info [:len x][:len y]", "syntax/adjacent-tokens"),
            (":if (true)do={ }", "syntax/adjacent-tokens"),
            (":if (true) do={ }else={ }", "syntax/adjacent-tokens"),
            (":put a?b", "syntax/invalid-character"),
            (":put 'a'", "syntax/invalid-character"),
            (":put é", "syntax/invalid-character"),
            ("﻿:put 1", "syntax/bom"),
            ('"abc"', "syntax/expected-command"),
            (":PUT 1", "syntax/expected-command"),
            ("::", "syntax/expected-command"),
        ],
    )
    def test_flags(self, text: str, rule: str) -> None:
        assert rule in rules(text)

    @pytest.mark.parametrize(
        "text",
        [
            ":put a-b",
            ":put a~b",
            ":put a=b",
            '/ip address print where address~"1"',
            "/ip address print where disabled = no",
            "/ip address print where address = 1.1.1.1/32",
            "/ip address print where !disabled && dynamic",
            ":",
            "/",
            ":put 1;",
            "{;}",
            "[;]",
            "/ip { address print }",
            "/ip address .. route print",
            "$f 1 2",
            ":local a ({})",
        ],
    )
    def test_accepts(self, text: str) -> None:
        assert rules(text) == []

    def test_warns_about_a_backslash_that_does_not_end_the_line_without_an_error(self) -> None:
        assert rules(":put \\ 1") == ["syntax/stray-backslash"]
