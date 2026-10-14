# routeros-lsp

A [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) server for MikroTik RouterOS scripts (`.rsc` files).

It gives editors and AI coding agents immediate feedback while they write RouterOS scripts: syntax errors, unknown menus,
commands and parameters, variable scope mistakes, and completion and hover from the RouterOS command list. It follows the
[RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting), and where the
documentation is silent or a real router behaves differently, the behaviour was measured on a router and written down in
[docs/ambiguities.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/ambiguities.md) instead of guessed.

[![PyPI](https://img.shields.io/pypi/v/routeros-lsp)](https://pypi.org/project/routeros-lsp/)
[![Python](https://img.shields.io/pypi/pyversions/routeros-lsp)](https://pypi.org/project/routeros-lsp/)
[![CI](https://github.com/wiresage/routeros-lsp/actions/workflows/ci.yml/badge.svg)](https://github.com/wiresage/routeros-lsp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/wiresage/routeros-lsp/blob/master/LICENSE)

## What it reports

| Area | Examples |
|---|---|
| Syntax | Unterminated strings, bad escapes, unbalanced brackets, two values with no space between them, a `#` comment after a command (RouterOS reads it as an argument and rejects the line), a line break inside `( )`, whitespace before `=`. |
| Variables | `:set` of a variable that is not declared in scope, a local used on a later line of an imported file (where it is empty), undeclared variables, invalid names. |
| Menus and commands | An unknown menu, command or parameter with a "did you mean", an ambiguous abbreviation, a parameter given twice, too many unnamed arguments, a missing required parameter. The menu path is tracked as RouterOS does, so relative commands after `/ip address` are checked in that menu. |

Hover and completion use the same command list: menus and commands, parameters (required ones first), values after `name=`, and
the variables in scope after `$`. There is also a symbol outline and folding. [docs/features.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/features.md) has the
details and the limits; [docs/rules.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/rules.md) lists every rule with its default severity.

A finding is labelled when it rests on RouterOS behaviour that the documentation does not describe, so a quirk of one version
is never presented as the language specification.

## Install and use

Python 3.10 or newer, no other dependencies:

```bash
pipx install routeros-lsp      # or: uv tool install routeros-lsp
routeros-lsp --version
```

To try the unreleased `master`, install straight from the repository:

```bash
pipx install git+https://github.com/wiresage/routeros-lsp.git
```

The server speaks LSP over stdio:

```bash
routeros-lsp --stdio
```

`uvx routeros-lsp --stdio` runs it without installing anything.

### Claude Code

[`plugin/`](https://github.com/wiresage/routeros-lsp/tree/master/plugin) is a Claude Code plugin that starts the server for `.rsc` files (language id `routeros`). It expects the
`routeros-lsp` command on your `PATH`. Settings go into its `.lsp.json`; see [docs/configuration.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/configuration.md).

### Other editors

Start `routeros-lsp --stdio` for the language id `routeros` from any LSP client.

## The command list

Menus, commands and parameters come from a database generated from a RouterOS 7.21.4 CHR with `/console/inspect`
(`src/routeros_lsp/data/routeros-7.21.4.json.gz`). A CHR has no wireless, LTE or switch-chip packages and some parameters exist only on some
hardware, so unknown-name findings are warnings by default. To cover your own hardware, generate the database from your router
(nothing is executed or changed on it) and point the `schema` setting at it:

```bash
pip install paramiko
ROUTEROS_PASSWORD=... python tools/gen_schema.py --host 192.0.2.1 --user admin --out my-router.json.gz
```

## Develop

```bash
python -m venv .venv && . .venv/bin/activate     # on Windows: .venv/Scripts/activate
pip install -e ".[dev]"
ruff check . && mypy && pytest
```

The tests need no router. Releases are cut by the pipeline in [docs/releasing.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/releasing.md). See [CONTRIBUTING.md](https://github.com/wiresage/routeros-lsp/blob/master/CONTRIBUTING.md), [AGENTS.md](https://github.com/wiresage/routeros-lsp/blob/master/AGENTS.md) and
[docs/architecture.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/architecture.md).

## How the language was pinned down

- [docs/grammar.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/grammar.md): the grammar derived from the documentation, each rule tagged as documented, shown by an
  example, observed on a device, or open.
- [docs/ambiguities.md](https://github.com/wiresage/routeros-lsp/blob/master/docs/ambiguities.md): every gap and conflict, with evidence from RouterOS 7.21.4 and the default used.
- [research/](https://github.com/wiresage/routeros-lsp/tree/master/research): the probes that produced that evidence. RouterOS can check a script without running it
  (`/import file.rsc verbose=yes dry-run`), which is the test oracle for this project; `tests/conformance/` replays more than
  800 recorded answers.

## License

[MIT](https://github.com/wiresage/routeros-lsp/blob/master/LICENSE)
