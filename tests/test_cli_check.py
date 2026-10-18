from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from routeros_lsp import __version__, cli_check
from routeros_lsp.cli_check import run
from tests.lsp_client import ROOT

CLEAN = "/ip address\nadd address=1.1.1.1/32 interface=ether1\n"
#: an error on line 1 (the "#" is read as an argument), a warning on line 2 (a menu a CHR does not know), a warning on line 3
MIXED = ":put 1 # c\n/nonsense\n:put $x\n"
WARNINGS_ONLY = "/nonsense\n"


class Result:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code = code
        self.out = out
        self.err = err


def check(*args: str, stdin: bytes = b"") -> Result:
    out, err = io.StringIO(), io.StringIO()
    code = run(list(args), io.BytesIO(stdin), out, err)
    return Result(code, out.getvalue(), err.getvalue())


def write(directory: Path, name: str, text: str) -> str:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return str(path)


class TestExitStatus:
    def test_a_clean_file_exits_zero_and_prints_no_findings(self, tmp_path: Path) -> None:
        result = check(write(tmp_path, "ok.rsc", CLEAN))
        assert (result.code, result.out) == (0, "")
        assert "Checked 1 file: no findings." in result.err

    def test_an_error_exits_one(self, tmp_path: Path) -> None:
        result = check(write(tmp_path, "bad.rsc", MIXED))
        assert result.code == 1

    def test_warnings_alone_do_not_fail_unless_strict(self, tmp_path: Path) -> None:
        path = write(tmp_path, "w.rsc", WARNINGS_ONLY)
        assert check(path).code == 0
        assert check("--strict", path).code == 1

    def test_unreadable_files_exit_two_but_the_others_are_still_checked(self, tmp_path: Path) -> None:
        bad = write(tmp_path, "bad.rsc", MIXED)
        result = check(str(tmp_path / "missing.rsc"), bad)
        assert result.code == 2
        assert "missing.rsc" in result.err
        assert "[schema/unexpected-argument]" in result.out

    def test_a_file_the_analysis_fails_on_is_reported_and_the_others_are_still_checked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = cli_check.analyze

        def flaky(text: str, **options: Any) -> Any:
            if "EXPLODE" in text:
                raise RecursionError("maximum recursion depth exceeded")
            return real(text, **options)

        monkeypatch.setattr(cli_check, "analyze", flaky)
        boom = write(tmp_path, "a-boom.rsc", ":put EXPLODE\n")
        bad = write(tmp_path, "b-bad.rsc", MIXED)
        result = check(boom, bad)
        # exit status 2 is "could not check", which a CI job can tell from 1, "found problems"
        assert result.code == 2
        assert "a-boom.rsc" in result.err and "RecursionError" in result.err
        assert "[schema/unexpected-argument]" in result.out
        assert "Checked 1 file" in result.err

    def test_a_file_that_is_not_utf8_is_reported_not_crashed_on(self, tmp_path: Path) -> None:
        path = tmp_path / "latin1.rsc"
        path.write_bytes(b':put "caf\xe9"\n')
        result = check(str(path))
        assert result.code == 2
        assert "not valid UTF-8" in result.err

    def test_no_paths_is_a_usage_error(self) -> None:
        result = check()
        assert result.code == 2
        assert "no files given" in result.err


class TestOutput:
    def test_text_lines_have_path_line_column_severity_message_and_rule(self, tmp_path: Path) -> None:
        path = write(tmp_path, "m.rsc", MIXED)
        lines = check(path).out.splitlines()
        assert len(lines) == 3
        assert lines[0].startswith(f"{path}:1:8: error: ")
        assert lines[0].endswith("[schema/unexpected-argument]")
        assert lines[1].startswith(f"{path}:2:2: warning: ")
        assert lines[1].endswith("[schema/unknown-command]")
        assert lines[2].startswith(f"{path}:3:6: warning: ")
        assert lines[2].endswith("[vars/undeclared-read]")

    def test_the_summary_goes_to_stderr_so_stdout_can_be_piped(self, tmp_path: Path) -> None:
        result = check(write(tmp_path, "m.rsc", MIXED))
        assert "Checked 1 file: 1 error, 2 warnings." in result.err
        assert "Checked" not in result.out

    def test_messages_say_when_a_rule_rests_on_router_behaviour(self, tmp_path: Path) -> None:
        out = check(write(tmp_path, "m.rsc", MIXED)).out
        assert "(RouterOS behaviour that the documentation does not describe)" in out

    def test_json_is_an_array_with_one_object_per_finding(self, tmp_path: Path) -> None:
        path = write(tmp_path, "m.rsc", MIXED)
        found: list[dict[str, Any]] = json.loads(check("--format", "json", path).out)
        assert [f["rule"] for f in found] == ["schema/unexpected-argument", "schema/unknown-command", "vars/undeclared-read"]
        first = found[0]
        assert (first["path"], first["line"], first["column"], first["endLine"], first["endColumn"]) == (path, 1, 8, 1, 9)
        assert first["severity"] == "error"
        assert first["source"] == "device"

    def test_json_for_a_clean_file_is_an_empty_array(self, tmp_path: Path) -> None:
        assert json.loads(check("--format", "json", write(tmp_path, "ok.rsc", CLEAN)).out) == []


class TestPositions:
    def test_lines_are_counted_for_lf_crlf_and_cr(self, tmp_path: Path) -> None:
        for name, newline in [("lf.rsc", "\n"), ("crlf.rsc", "\r\n"), ("cr.rsc", "\r")]:
            path = write(tmp_path, name, newline.join([":put 1", ":put 2", ":put 3 # c", ""]))
            assert check(path).out.startswith(f"{path}:3:8: "), name

    def test_columns_count_characters_not_utf16_units(self, tmp_path: Path) -> None:
        path = write(tmp_path, "emoji.rsc", ':put "\U0001f600" # c\n')
        assert check(path).out.startswith(f"{path}:1:10: ")

    def test_a_byte_order_mark_is_reported_not_swallowed(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.rsc"
        path.write_bytes(b"\xef\xbb\xbf" + CLEAN.encode())
        assert "[syntax/bom]" in check(str(path)).out


class TestPaths:
    def test_a_directory_is_searched_for_rsc_files_in_order(self, tmp_path: Path) -> None:
        write(tmp_path, "b.rsc", WARNINGS_ONLY)
        write(tmp_path, "sub/a.rsc", WARNINGS_ONLY)
        write(tmp_path, "notes.txt", WARNINGS_ONLY)
        result = check(str(tmp_path))
        assert len(result.out.splitlines()) == 2
        assert "Checked 2 files" in result.err
        assert result.out.index("b.rsc") < result.out.index(os.path.join("sub", "a.rsc"))

    def test_dash_reads_standard_input(self) -> None:
        result = check("-", stdin=MIXED.encode())
        assert result.code == 1
        assert result.out.startswith("<stdin>:1:8: error: ")

    def test_an_empty_directory_checks_nothing_and_succeeds(self, tmp_path: Path) -> None:
        result = check(str(tmp_path))
        assert result.code == 0
        assert "Checked 0 files" in result.err


class TestSettings:
    def test_severity_can_be_changed_per_rule(self, tmp_path: Path) -> None:
        path = write(tmp_path, "w.rsc", WARNINGS_ONLY)
        assert check("--severity", "schema/unknown-command=error", path).code == 1
        mixed = write(tmp_path, "m.rsc", MIXED)
        assert check("--severity", "schema/unexpected-argument=off", mixed).code == 0

    def test_scope_script_lets_a_file_share_one_scope(self, tmp_path: Path) -> None:
        path = write(tmp_path, "g.rsc", ":global g 1\n:set g 2\n")
        assert "[vars/set-undeclared]" in check(path).out
        assert check("--scope", "script", path).out == ""

    def test_context_variables_are_not_reported_as_undeclared(self, tmp_path: Path) -> None:
        path = write(tmp_path, "c.rsc", ":put $custom\n")
        assert "[vars/undeclared-read]" in check(path).out
        assert check("--context-variable", "custom", path).out == ""

    def test_schema_off_turns_the_command_checks_off(self, tmp_path: Path) -> None:
        path = write(tmp_path, "n.rsc", "/nonsense\n")
        assert check("--schema", "off", path).out == ""

    def test_a_schema_file_that_cannot_be_read_falls_back_and_says_so(self, tmp_path: Path) -> None:
        path = write(tmp_path, "n.rsc", "/nonsense\n")
        result = check("--schema", str(tmp_path / "nope.json"), path)
        assert "cannot read the command database" in result.err
        assert "[schema/unknown-command]" in result.out

    @pytest.mark.parametrize("bad", ["schema/unknown-command", "no/such-rule=error", "schema/unknown-command=loud"])
    def test_a_bad_severity_is_a_usage_error(self, bad: str, tmp_path: Path) -> None:
        result = check("--severity", bad, write(tmp_path, "ok.rsc", CLEAN))
        assert result.code == 2
        assert result.out == ""


class TestHelp:
    def test_help_describes_the_exit_status(self) -> None:
        result = check("--help")
        assert result.code == 0
        assert "Exit status" in result.out
        assert "--strict" in result.out

    def test_an_unknown_option_is_a_usage_error(self) -> None:
        result = check("--no-such-option")
        assert result.code == 2
        assert "unrecognized arguments" in result.err or "no-such-option" in result.err


class TestRealCommand:
    def run(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        return subprocess.run(
            [sys.executable, "-m", "routeros_lsp", "check", *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )

    def test_the_subcommand_is_wired_up_end_to_end(self) -> None:
        result = self.run("-", stdin=MIXED)
        assert result.returncode == 1
        assert result.stdout.splitlines()[0].startswith("<stdin>:1:8: error: ")
        assert "Checked 1 file" in result.stderr

    def test_the_server_flags_still_work(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        done = subprocess.run(
            [sys.executable, "-m", "routeros_lsp", "--version"], capture_output=True, text=True, env=env, timeout=60
        )
        assert done.stdout.strip() == __version__

    def test_unencodable_output_does_not_crash(self) -> None:
        # a non-ASCII command name is echoed in the message; a console that cannot encode it must not make the command fail
        result = self.run("-", stdin=":put \U0001f600\n")
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr
