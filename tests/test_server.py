from __future__ import annotations

import io
import os
import subprocess
import sys
from typing import Any

import pytest

from routeros_lsp import __version__
from routeros_lsp import server as server_module
from routeros_lsp.server import MalformedMessage, read_message
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

    @pytest.mark.parametrize(
        "notification",
        [
            pytest.param({"settings": None}, id="null-settings"),
            pytest.param({}, id="no-settings"),
            pytest.param({"settings": {}}, id="empty-settings"),
            pytest.param({"settings": {"routeros": {}}}, id="empty-section"),
        ],
    )
    def test_a_notification_without_settings_keeps_the_settings_in_force(self, notification: dict[str, Any]) -> None:
        # Many clients send this after startup to say "something changed, ask me". There is nothing in it to apply, and applying
        # it would throw away the initializationOptions the user configured.
        options = {"severities": {"schema/unexpected-argument": "off", "syntax/trailing-comment": "off"}}
        with in_process(options) as c:
            assert c.open(URI, ":put 1 # c\n") == []
            c.notify("workspace/didChangeConfiguration", notification)
            assert c.change(URI, ":put 2 # c\n", 2) == []

    def test_a_notification_with_settings_still_replaces_the_ones_in_force(self) -> None:
        options = {"severities": {"schema/unexpected-argument": "off", "syntax/trailing-comment": "off"}}
        with in_process(options) as c:
            assert c.open(URI, ":put 1 # c\n") == []
            restored = c.configure({"severities": {"syntax/trailing-comment": "off"}}, URI)
            assert [d["code"] for d in restored] == ["schema/unexpected-argument"]

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


class TestContainment:
    def test_a_document_the_analysis_fails_on_does_not_end_the_session(
        self, client: LspClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = server_module.analyze

        def flaky(text: str, **options: Any) -> Any:
            if "BOOM" in text:
                raise RecursionError("maximum recursion depth exceeded")
            return real(text, **options)

        monkeypatch.setattr(server_module, "analyze", flaky)
        other = "file:///other.rsc"
        assert [d["code"] for d in client.open(other, ":put 1 # c\n")] == ["schema/unexpected-argument"]
        # the failing document is answered with no diagnostics, so no stale ones stay on screen, and the failure is logged
        assert client.open(URI, ":put BOOM\n") == []
        assert any("test.rsc" in log["message"] and "RecursionError" in log["message"] for log in client.logs)
        # the session, and the other document, carry on
        assert [d["code"] for d in client.change(other, ":put 2 # d\n", 2)] == ["schema/unexpected-argument"]
        assert client.hover(other, 0, 2) is not None

    def test_the_other_documents_are_still_published_when_a_configuration_change_fails_on_one(
        self, client: LspClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = server_module.analyze

        def flaky(text: str, **options: Any) -> Any:
            if "BOOM" in text and options["severities"]:
                raise ValueError("a bug that only some settings reach")
            return real(text, **options)

        monkeypatch.setattr(server_module, "analyze", flaky)
        other = "file:///other.rsc"
        client.open(URI, ":put BOOM\n")
        assert client.open(other, ":put 1 # c\n")[0]["severity"] == 1
        # both documents are analysed again; the failing one must not stop the other from being republished
        client.notify("workspace/didChangeConfiguration", {"settings": {"severities": {"schema/unexpected-argument": "warning"}}})
        assert client.wait_for_severity(other, 2)

    def test_a_long_operator_chain_is_answered_and_the_session_goes_on(self, client: LspClient) -> None:
        text = ":put (" + "+".join(["$a"] * 20_000) + ")\n"
        assert [d["code"] for d in client.open(URI, text)] == ["vars/undeclared-read"]
        hover = client.hover(URI, 0, 7)
        assert hover is not None and "not declared" in hover["contents"]["value"]
        assert client.change(URI, ":put 1\n", 2) == []


class TestFraming:
    @staticmethod
    def frame(body: bytes) -> bytes:
        return b"Content-Length: %d\r\n\r\n%s" % (len(body), body)

    def test_a_malformed_frame_is_consumed_so_the_next_one_can_be_read(self) -> None:
        stream = io.BytesIO(self.frame(b"{ nope") + self.frame(b'{"jsonrpc": "2.0", "method": "exit"}'))
        with pytest.raises(MalformedMessage) as raised:
            read_message(stream)
        assert raised.value.code == -32700
        assert read_message(stream) == {"jsonrpc": "2.0", "method": "exit"}
        assert read_message(stream) is None

    def test_json_that_is_not_an_object_is_an_invalid_request(self) -> None:
        with pytest.raises(MalformedMessage) as raised:
            read_message(io.BytesIO(self.frame(b"[1]")))
        assert raised.value.code == -32600

    def test_a_truncated_body_is_the_end_of_the_stream(self) -> None:
        assert read_message(io.BytesIO(b"Content-Length: 50\r\n\r\n{}")) is None


class TestProtocolManners:
    def test_unknown_requests_are_answered_with_an_error(self, client: LspClient) -> None:
        response = client.request_raw("textDocument/rename", {})
        assert response["error"]["code"] == -32601

    def test_unknown_notifications_and_cancellations_are_ignored(self, client: LspClient) -> None:
        client.notify("$/cancelRequest", {"id": 1})
        client.notify("workspace/somethingNew", {})
        assert client.open(URI, ":put 1\n") == []

    def test_a_body_that_is_not_json_gets_a_parse_error_and_the_session_goes_on(self, client: LspClient) -> None:
        response = client.send_unusable(b"{ this is not json")
        assert response["id"] is None
        assert response["error"]["code"] == -32700
        # the frame was read to its end, so the next message is understood
        assert [d["code"] for d in client.open(URI, ":put 1 # c\n")] == ["schema/unexpected-argument"]

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            pytest.param(b"\xff\xfe", -32700, id="not-utf-8"),
            pytest.param(b"", -32700, id="empty-body"),
            pytest.param(b"[" * 100_000, -32700, id="nested-too-deep-for-the-json-reader"),
            pytest.param(b'[{"jsonrpc": "2.0", "method": "exit"}]', -32600, id="batch-array"),
            pytest.param(b"42", -32600, id="number"),
            pytest.param(b"null", -32600, id="null"),
        ],
    )
    def test_other_bodies_that_are_not_a_message_are_answered_and_do_not_end_the_session(
        self, client: LspClient, body: bytes, code: int
    ) -> None:
        assert client.send_unusable(body)["error"]["code"] == code
        assert client.hover("file:///nope.rsc", 0, 0) is None

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

    def test_a_malformed_message_does_not_end_the_session(self) -> None:
        with spawned() as (c, process):
            assert c.send_unusable(b"{ this is not json")["error"]["code"] == -32700
            assert c.open("file:///after.rsc", ":put 1 # c\n")[0]["code"] == "schema/unexpected-argument"
            assert c.errors == []
            c.shutdown()
            assert process.wait(timeout=10) == 0

    def test_a_crash_inside_the_server_still_ends_the_process_with_exit_code_1(self) -> None:
        # The reader thread is left blocked in read(), as in a real session. If the exception were allowed to take the interpreter
        # through its normal shutdown, Python would abort with "Fatal Python error: _enter_buffered_busy" and a crash exit code.
        script = (
            "import threading\n"
            "from routeros_lsp import server\n"
            "def run(self):\n"
            "    threading.Thread(target=self._read_loop, daemon=True).start()\n"
            "    raise RuntimeError('simulated bug in the server')\n"
            "server.Server.run = run\n"
            "from routeros_lsp.cli import main\n"
            "main(['--stdio'])\n"
        )
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        process = subprocess.Popen(
            [sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
        try:
            code = process.wait(timeout=30)
            assert process.stderr is not None
            stderr = process.stderr.read().decode("utf-8", "replace")
        finally:
            if process.poll() is None:
                process.kill()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        assert "simulated bug in the server" in stderr
        assert "Fatal Python error" not in stderr
        assert code == 1

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
