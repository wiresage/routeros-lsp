"""Facts read off a RouterOS 7.21.4 CHR by tools/gen_schema.py. They guard the generated file against a bad run, and the
second half guards against false positives that the differential run (research/tools/differential.py, 16,900 generated command
lines judged by a router) and the probe suites turned up."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from routeros_lsp.analyze import analyze
from routeros_lsp.schema.schema import NodeInfo, Schema

DATA = Path(__file__).resolve().parent.parent / "src" / "routeros_lsp" / "data" / "routeros-7.21.4.json.gz"

bundled = Schema.bundled()
assert bundled is not None
schema: Schema = bundled


def at(*path: str) -> NodeInfo:
    node = schema.root
    for name in path:
        nxt = node.get("c", {}).get(name)
        assert nxt is not None, f"/{' '.join(path)} is not in the bundled database"
        node = nxt
    return node


def count(node: NodeInfo) -> tuple[int, int]:
    menus = commands = 0
    stack = [node]
    while stack:
        n = stack.pop()
        if n.get("k"):
            commands += 1
        else:
            menus += 1
        stack.extend(n.get("c", {}).values())
    return menus, commands


class TestTheBundledCommandDatabase:
    def test_is_found_and_describes_routeros_7_21_4(self) -> None:
        assert schema.version == "7.21.4"

    def test_holds_the_whole_command_tree(self) -> None:
        menus, commands = count(schema.root)
        assert menus > 400
        assert commands > 3900

    def test_stays_small_enough_to_ship(self) -> None:
        assert DATA.stat().st_size < 400 * 1024

    def test_knows_the_required_parameters(self) -> None:
        assert at("ip", "address", "add")["r"] == ["address", "interface"]
        assert {"vlan-id", "interface"} <= set(at("interface", "vlan", "add")["r"])
        assert at("put")["r"] == ["message"]
        assert "r" not in at("system", "identity", "set")

    def test_knows_how_many_unnamed_arguments_a_command_takes(self) -> None:
        assert at("ip", "address", "add").get("u", 0) == 0
        assert at("ip", "address", "print").get("u", 0) == 0
        assert at("ip", "address", "set")["u"] == 1
        assert at("put")["u"] == 1
        assert at("local")["u"] == 2
        # a condition is an unnamed group, a script an unnamed block
        assert at("if")["u"] >= 1
        assert at("while")["u"] >= 1
        assert at("execute")["u"] >= 1

    def test_marks_flags_only_where_a_bare_name_is_a_flag(self) -> None:
        arguments: dict[str, Any] = at("ip", "address", "print")["a"]
        for flag in ["detail", "brief", "count-only", "as-value", "without-paging", "terse"]:
            assert arguments[flag].get("f") == 1, flag
        for valued in ["from", "where", "file", "interval", "proplist"]:
            assert "f" not in arguments[valued], valued
        assert "f" not in at("ip", "address", "add")["a"]["comment"]

    def test_keeps_fixed_lists_of_values_and_leaves_out_values_that_belong_to_one_router(self) -> None:
        action = at("ip", "firewall", "filter", "add")["a"]["action"]
        assert {"accept", "drop", "jump"} <= set(action["e"])
        interface = at("ip", "address", "add")["a"]["interface"]
        assert "e" not in interface
        assert "ether1" not in interface.get("t", "")
        assert at("ip", "address", "add")["a"]["disabled"]["e"] == ["no", "yes"]

    def test_describes_menus_commands_and_parameters(self) -> None:
        assert at("ip")["d"]
        assert at("ip", "address", "add")["d"] == "Create a new item"
        address = at("ip", "address", "add")["a"]["address"]
        assert (address["d"], address["t"]) == ("Local IP address", "A.B.C.D (IP address)")


def findings(text: str) -> list[str]:
    return [f"{f.rule}: {f.message}" for f in analyze(text).findings]


class TestValidInputProducesNoFindingsAgainstTheBundledDatabase:
    @pytest.mark.parametrize(
        "text",
        [
            # arrays and blocks in argument position are not command lists (probes f5, a4, z7)
            ":foreach i in={1;2} do={ :put $i }",
            ":foreach k,v in={1;2} do={ :put $k }",
            ":put {1;2;3}",
            ":local a {1;2;3}; :put ($a->1)",
            # a word that only starts a parameter name is a value for a command that takes values
            ':foreach i in=[:toarray "1,2"] do={ :put $i }',
            # a colon can lead into a menu (probe p23)
            ':log info "x"',
            ":ip address print",
            # find takes property conditions without where (probes w1 to w6, r19)
            "/ip address remove [find address=1.1.1.1/32]",
            "/interface ethernet set [find default-name=ether1] disable-running-check=no",
            # loop-only commands inside a loop (probe p20)
            ":foreach i in={1} do={ :break }",
            ":while (true) do={ :continue }",
            # commands that take free-form parameters
            ":do command=0 command=0",
            ":onerror e in={ } do={ }",
            ":retry command={ :put 1 } delay=1 max=1",
            "/ip recursive-print zzz=0",
            # statement-level substitution and colon lines keep the path rules (probes l9, suite 20)
            "[/ip route]\nadd dst-address=0.0.0.0/0 gateway=1.1.1.1",
            ":if (true) do={ /ip route; add dst-address=0.0.0.0/0 gateway=1.1.1.1 }",
            # :local name=x names the parameter
            ":local name=abc; :put $abc",
        ],
    )
    def test_accepts(self, text: str) -> None:
        assert findings(text) == []

    def test_still_reports_the_mistakes_next_to_them(self) -> None:
        assert "'break'" in "\n".join(findings(":break"))
        assert "Declare a variable as" in "\n".join(findings(":local a=1"))
        assert "'address'" in "\n".join(findings("[/ip route]\nprint\nadd address=1.1.1.1/32 interface=ether1"))
        assert "Put" in "\n".join(findings(":put 1 # c"))
