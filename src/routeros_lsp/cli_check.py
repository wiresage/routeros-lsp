"""``routeros-lsp check``: the analysis on files, for a terminal, a pre-commit hook or a CI job.

It is the same analysis the language server runs, so a script that passes here shows no problem in the editor and the other way
round. Nothing is executed and no router is needed.
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TextIO

from .analyze import Finding, analyze, load_schema
from .config import Settings, parse_settings
from .document import Document
from .features.diagnostics import describe
from .rules import RULES, SEVERITIES

PROG = "routeros-lsp check"

DESCRIPTION = """\
Check RouterOS script files (.rsc) and print what the language server would report.

A path can be a file, a directory (every .rsc file below it is checked) or - for standard input.

Exit status: 0 nothing to fix, 1 errors were found (with --strict also warnings), 2 a file could not be read or analysed,
or the command line is wrong.
"""

LEVELS = ("error", "warning", "information", "hint")


@dataclass(frozen=True, slots=True)
class Located:
    """A finding with its position in a file, counted in lines and characters from 1."""

    path: str
    line: int
    column: int
    end_line: int
    end_column: int
    finding: Finding


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", metavar="PATH", help="files, directories or - for standard input")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="text: path:line:col lines (default); json: an array"
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 for warnings as well")
    parser.add_argument(
        "--scope",
        choices=("import", "script"),
        default="import",
        help="how variable scope works: every line of an imported file is a scope (default), or the whole file is one",
    )
    parser.add_argument("--schema", default="bundled", metavar="bundled|off|FILE", help="the command database (default: bundled)")
    parser.add_argument(
        "--severity",
        action="append",
        default=[],
        metavar="RULE=LEVEL",
        help=f"change a rule's severity ({', '.join(SEVERITIES)}); repeatable",
    )
    parser.add_argument(
        "--context-variable", action="append", default=[], metavar="NAME", help="a variable the environment provides; repeatable"
    )
    return parser


def settings_from(args: argparse.Namespace) -> tuple[Settings, list[str]]:
    """The same settings object the language server uses, and the complaints about it."""
    severities: dict[str, str] = {}
    problems: list[str] = []
    for item in args.severity:
        rule, separator, level = item.partition("=")
        if not separator:
            problems.append(f'--severity expects RULE=LEVEL, got "{item}"')
        else:
            severities[rule] = level
    raw: dict[str, Any] = {"severities": severities, "scope": args.scope, "schema": args.schema}
    if args.context_variable:
        raw["contextVariables"] = args.context_variable
    settings = parse_settings(raw, problems.append)
    return settings, problems


def expand(paths: Sequence[str]) -> list[str]:
    """Directories become the .rsc files below them; everything else is kept as given, in order."""
    out: list[str] = []
    for given in paths:
        if given != "-" and Path(given).is_dir():
            out.extend(str(p) for p in sorted(Path(given).rglob("*.rsc")) if p.is_file())
        else:
            out.append(given)
    return out


def locate(path: str, text: str, findings: Sequence[Finding]) -> list[Located]:
    starts = Document(path, text).line_starts()

    def position(offset: int) -> tuple[int, int]:
        line = bisect.bisect_right(starts, offset) - 1
        return line + 1, offset - starts[line] + 1

    located = []
    for finding in findings:
        line, column = position(finding.start)
        end_line, end_column = position(finding.end)
        located.append(Located(path, line, column, end_line, end_column, finding))
    return located


def fails(found: Located, strict: bool) -> bool:
    return found.finding.severity == "error" or (strict and found.finding.severity == "warning")


def as_text(found: Located) -> str:
    f = found.finding
    return f"{found.path}:{found.line}:{found.column}: {f.severity}: {describe(f)} [{f.rule}]"


def as_json(found: Located) -> dict[str, Any]:
    f = found.finding
    return {
        "path": found.path,
        "line": found.line,
        "column": found.column,
        "endLine": found.end_line,
        "endColumn": found.end_column,
        "severity": f.severity,
        "rule": f.rule,
        "source": RULES[f.rule].source,
        "message": describe(f),
    }


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def run(argv: Sequence[str], stdin: BinaryIO, stdout: TextIO, stderr: TextIO) -> int:
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            args = parser.parse_args(argv)
    except SystemExit as stop:  # --help, or a usage error that argparse has already printed
        return stop.code if isinstance(stop.code, int) else 2

    settings, problems = settings_from(args)
    if not args.paths:
        problems.append("no files given; name a file or directory, or use - for standard input")
    if problems:
        for problem in problems:
            stderr.write(f"{PROG}: {problem}\n")
        return 2

    def warn(message: str) -> None:
        stderr.write(f"{PROG}: {message}\n")

    schema = load_schema(settings.schema, warn)
    files = expand(args.paths)
    all_found: list[Located] = []
    failed = 0
    for path in files:
        try:
            raw = stdin.read() if path == "-" else Path(path).read_bytes()
            # not "utf-8-sig": a byte order mark is something the analysis reports
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            reason = "not valid UTF-8" if isinstance(error, UnicodeDecodeError) else error.strerror or str(error)
            stderr.write(f"{PROG}: {'<stdin>' if path == '-' else path}: {reason}\n")
            failed += 1
            continue
        name = "<stdin>" if path == "-" else path
        try:
            result = analyze(
                text,
                severities=settings.severities,
                scope=settings.scope,
                context_variables=settings.context_variables,
                schema=schema,
            )
        except Exception as error:  # a bug in the analysis must not hide the findings in the other files
            stderr.write(
                f"{PROG}: {name}: the analysis failed ({type(error).__name__}: {error}). This is a bug, please report it.\n"
            )
            failed += 1
            continue
        all_found.extend(locate(name, text, result.findings))

    if args.format == "json":
        # Escaped, not raw: stdout is encoded with the locale when it is redirected (cp1252 on Windows), which is not UTF-8 and
        # loses what the code page lacks. Plain ASCII reads the same under every encoding.
        stdout.write(json.dumps([as_json(f) for f in all_found], indent=2) + "\n")
    else:
        for found in all_found:
            stdout.write(as_text(found) + "\n")

    counts = {level: sum(1 for f in all_found if f.finding.severity == level) for level in LEVELS}
    shown = [plural(n, level) for level, n in counts.items() if n]
    checked = plural(len(files) - failed, "file")
    stderr.write(f"Checked {checked}: {', '.join(shown) if shown else 'no findings'}.\n")

    if failed:
        return 2
    return 1 if any(fails(f, args.strict) for f in all_found) else 0
