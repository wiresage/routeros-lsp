from __future__ import annotations

import os
import subprocess
import sys

import pytest

from routeros_lsp import __version__
from tests.lsp_client import ROOT, LspClient, in_process, spawned

URI = "file:///work/test.rsc"


@pytest.fixture
def client() -> LspClient:
    with in_process() as c:
        yield c


class TestOverAPipePair:
    def test_initialize_result(self) -> None:
        with in_process() as c:
            result = c.initialize_result
        assert result["serverInfo"] == {"name": "routeros-lsp", "version": __version__}
        assert result["capabilities"] == {
            "textDocumentSync": {"openClose": True, "change": 2},
            "documentSymbolProvider": True,
            "foldingRangeProvider": True,
            "hoverProvider": True,
            "completionProvider": {"triggerCharacters": ["$", ":", "/", "=", " "]},
        }

    def test_publishes_diagnostics_when_a_document_opens(self, client: LspClient) -> None:
        diagnostics = client.open(URI, ":put 1 # trailing\n/ip address print\n")
        assert len(diagnostics) == 1
        assert diagnostics[0]["code"] == "schema/unexpected-argument"
        assert diagnostics[0]["source"] == "routeros-lsp"
        assert diagnostics[0]["severity"] == 1
        assert diagnostics[0]["range"] == {"start": {"line": 0, "character": 7}, "end": {"line": 0, "character": 8}}
        assert client.published(URI)[0]["version"] == 1

    def test_labels_rules_that_are_not_the_documented_language(self, client: LspClient) -> None:
        (diagnostic,) = client.open(URI, ':put "a"\n}\n')
        assert diagnostic["code"] == "syntax/stray-closer"
        assert diagnostic["severity"] == 2
        assert "the documentation does not specify this" in diagnostic["message"]

    def test_clears_diagnostics_once_fixed_and_on_close(self, client: LspClient) -> None:
        assert [d["code"] for d in client.open(URI, ':put "unterminated\n')] == ["syntax/unterminated-string"]
        assert client.change(URI, ':put "fixed"\n', 2) == []
        assert "syntax/missing-closer" in [d["code"] for d in client.change(URI, ":put (\n", 3)]
        assert client.close(URI) == []

    def test_applies_severities_from_configuration_and_revalidates(self, client: LspClient) -> None:
        assert client.open(URI, ":put 1 # c\n")[0]["severity"] == 1
        warned = client.configure({"routeros": {"severities": {"schema/unexpected-argument": "warning"}}}, URI)
        assert warned[0]["severity"] == 2
        off = client.configure({"severities": {"schema/unexpected-argument": "off", "syntax/trailing-comment": "off"}}, URI)
        assert off == []

    def test_reads_settings_from_initialization_options(self) -> None:
        with in_process({"severities": {"schema/unexpected-argument": "hint"}}) as c:
            assert c.open(URI, ":put 1 # c\n")[0]["severity"] == 4

    def test_scope_setting_changes_variable_diagnostics(self) -> None:
        text = ":global g 1\n:set g 2\n"
        with in_process() as c:
            assert [d["code"] for d in c.open(URI, text)] == ["vars/set-undeclared"]
        with in_process({"scope": "script"}) as c:
            assert c.open(URI, text) == []

    def test_schema_can_be_turned_off(self) -> None:
        with in_process({"schema": "off"}) as c:
            assert c.open(URI, "/nonsense\n") == []

    def test_a_missing_schema_file_falls_back_to_the_bundled_one_and_says_so(self) -> None:
        with in_process({"schema": "no/such/file.json"}) as c:
            assert [d["code"] for d in c.open(URI, "/nonsense\n")] == ["schema/unknown-command"]
            assert any("cannot read the command database" in log["message"] for log in c.logs)

    def test_returns_a_symbol_outline(self, client: LspClient) -> None:
        text = "\n".join(
            [
                "/ip firewall filter",
                "add chain=input",
                "add chain=forward",
                "/system script",
                ":global hello do={",
                "  :local inner 1",
                "  :put $inner",
                "}",
                ":global counter 0",
                "",
            ]
        )
        client.open(URI, text)
        symbols = client.symbols(URI)
        assert [(s["name"], s["kind"], s["detail"]) for s in symbols] == [
            ("/ip firewall filter", 3, "2 commands"),
            ("/system script", 3, "2 commands"),
            ("hello", 12, "global"),
            ("counter", 13, "global"),
        ]
        assert [c["name"] for c in symbols[2]["children"]] == ["inner"]

    def test_returns_folding_ranges(self, client: LspClient) -> None:
        client.open(URI, "\n".join(["# one", "# two", ":if (true) do={", "  :put 1", "}", ':put "a', 'b"', ""]))
        assert client.folding(URI) == [
            {"startLine": 0, "endLine": 1, "kind": "comment"},
            {"startLine": 2, "endLine": 3},
            {"startLine": 5, "endLine": 6},
        ]

    def test_hover_and_completion(self, client: LspClient) -> None:
        client.open(URI, "/ip address add address=1.1.1.1/32 interface=ether1\n/ip address \n")
        hover = client.hover(URI, 0, 2)
        assert hover is not None and "**/ip** menu" in hover["contents"]["value"]
        labels = [i["label"] for i in client.completion(URI, 1, 12)]
        assert {"add", "print", "set", "remove"} <= set(labels)

    def test_requests_for_unknown_documents_get_empty_answers(self, client: LspClient) -> None:
        assert client.symbols("file:///nope.rsc") == []
        assert client.folding("file:///nope.rsc") == []
        assert client.hover("file:///nope.rsc", 0, 0) is None
        assert client.completion("file:///nope.rsc", 0, 0) == []


class TestPositions:
    def test_incremental_edits_use_utf16_columns(self, client: LspClient) -> None:
        # `x` is the tenth code point but starts at UTF-16 column 10, because the emoji before it is two code units wide
        text = ':put "\U0001f600" x\n'
        assert [d["code"] for d in client.open(URI, text)] == ["schema/unexpected-argument"]
        delete_x = {"range": {"start": {"line": 0, "character": 10}, "end": {"line": 0, "character": 11}}, "text": ""}
        assert client.edit(URI, [delete_x], 2) == []

    def test_diagnostic_columns_count_utf16_units(self, client: LspClient) -> None:
        # the `#` is the tenth code point (offset 9) but sits at UTF-16 column 10
        (diagnostic,) = client.open(URI, ':put "\U0001f600" # c\n')
        assert diagnostic["range"]["start"] == {"line": 0, "character": 10}

    def test_edits_that_cross_lines_and_use_crlf(self, client: LspClient) -> None:
        client.open(URI, ":put 1\r\n:put 2\r\n")
        diagnostics = client.edit(
            URI,
            [
                {"range": {"start": {"line": 0, "character": 6}, "end": {"line": 1, "character": 0}}, "text": " # c\n"},
            ],
            2,
        )
        assert [d["code"] for d in diagnostics] == ["schema/unexpected-argument"]
        assert diagnostics[0]["range"]["start"] == {"line": 0, "character": 7}

    def test_a_burst_of_edits_ends_with_the_diagnostics_of_the_last_text(self, client: LspClient) -> None:
        client.open(URI, ":put 1\n")
        texts = {version: f":put {version}\n" for version in range(2, 40)}
        texts[100] = ":put 1 # last\n"
        for version, text in texts.items():
            params = {"textDocument": {"uri": URI, "version": version}, "contentChanges": [{"text": text}]}
            client.notify("textDocument/didChange", params)
        final = client.wait_for_version(URI, 100)
        assert [d["code"] for d in final] == ["schema/unexpected-argument"]
        # nothing about an older text is published after the newest one
        assert client.published(URI)[-1]["version"] == 100


class TestProtocolManners:
    def test_unknown_requests_are_answered_with_an_error(self, client: LspClient) -> None:
        response = client.request_raw("textDocument/rename", {})
        assert response["error"]["code"] == -32601

    def test_unknown_notifications_and_cancellations_are_ignored(self, client: LspClient) -> None:
        client.notify("$/cancelRequest", {"id": 1})
        client.notify("workspace/somethingNew", {})
        assert client.open(URI, ":put 1\n") == []

    def test_requests_before_initialize_are_refused(self) -> None:
        with in_process(initialize=False) as c:
            assert c.request_raw("textDocument/hover", {})["error"]["code"] == -32002
            c.initialize()

    def test_requests_after_shutdown_are_refused(self) -> None:
        with in_process() as c:
            c.request("shutdown")
            assert c.request_raw("textDocument/hover", {})["error"]["code"] == -32600
            c.notify("exit")


class TestRealStdio:
    def test_the_command_speaks_lsp_and_writes_nothing_else_to_stdout(self) -> None:
        with spawned() as (c, process):
            diagnostics = c.open("file:///e2e.rsc", '/ip address add address=1.1.1.1/32 comment="x" # note\n')
            assert [d["code"] for d in diagnostics] == ["schema/unexpected-argument"]
            # a stray write to stdout would have broken the framing and been recorded by the reader
            assert c.errors == []
            c.shutdown()
            assert process.wait(timeout=10) == 0

    def test_a_clean_file_is_clean(self) -> None:
        with spawned() as (c, process):
            assert c.open("file:///clean.rsc", "/ip address\nadd address=1.1.1.1/32 interface=ether1\n") == []
            c.shutdown()
            assert process.wait(timeout=10) == 0

    def test_exit_without_shutdown_is_a_failure(self) -> None:
        with spawned() as (c, process):
            c.notify("exit")
            assert process.wait(timeout=10) == 1

    def test_closing_stdin_ends_the_server(self) -> None:
        with spawned() as (_, process):
            assert process.stdin is not None
            process.stdin.close()
            assert process.wait(timeout=10) == 1


class TestCommandLine:
    @staticmethod
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "routeros_lsp", *args], capture_output=True, text=True, env=env, timeout=30)

    def test_prints_its_version_and_usage(self) -> None:
        assert self.run("--version").stdout.strip() == __version__
        assert "--stdio" in self.run("--help").stdout

    def test_refuses_to_run_without_a_transport(self) -> None:
        result = self.run()
        assert result.returncode == 2
        assert "use --stdio" in result.stderr
