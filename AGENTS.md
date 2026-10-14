# AGENTS.md

Instructions for AI coding agents working in this repository. Humans should also read [CONTRIBUTING.md](CONTRIBUTING.md).

## Project overview

`routeros-lsp` is a Language Server Protocol server for MikroTik RouterOS scripts (`.rsc`). It reports syntax errors, variable
scope mistakes, unknown menus, commands and parameters, and offers completion and hover, so that editors and AI agents get
immediate feedback on what they write.

- Python 3.10 or newer, **no runtime dependencies**. The JSON-RPC framing and the LSP handling are written by hand in
  `server.py`; the package is published to PyPI as `routeros-lsp`.
- The language is defined by the [RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting),
  summarised in [docs/grammar.md](docs/grammar.md). Where the documentation is silent or a real router disagrees, the case is in
  [docs/ambiguities.md](docs/ambiguities.md). **Read those two files before touching the parser, a checker or any diagnostic.**
- RouterOS itself is the test oracle: `/import file.rsc verbose=yes dry-run` reports every error with line and column and executes
  nothing. Behaviour is measured with it, not recalled.

## Commands

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .   # lint and formatting
mypy                                    # strict, on src
pytest                                  # needs no router
routeros-lsp --version
python -m build && twine check dist/*   # what the release pipeline builds
```

Run ruff, mypy and pytest before every commit. After changing `src/routeros_lsp/rules.py` run
`UPDATE_DOCS=1 pytest tests/test_docs.py` to refresh `docs/rules.md`.

## Architecture

```
text -> parser -> syntax tree -> binder -> checkers -> findings -> LSP diagnostics
                       |                      ^
                       |        command database (routeros_lsp/data/*.json.gz)
                       +-> completion, hover, symbols, folding
```

```
src/routeros_lsp/cli.py        entry point: --stdio, --version, --help
src/routeros_lsp/server.py     JSON-RPC over stdio and the LSP handlers; a failing feature is logged and answered with an empty result
src/routeros_lsp/analyze.py    runs the stages and applies severity settings
src/routeros_lsp/rules.py      every diagnostic rule: id, default severity, source, summary
src/routeros_lsp/config.py     settings (severities, scope, contextVariables, schema)
src/routeros_lsp/document.py   text, revisions and the UTF-16 position conversion LSP needs
src/routeros_lsp/syntax/       parser (scannerless, recursive descent, error recovery), tree types, walker
src/routeros_lsp/binder/       scopes, declarations, references, lookups by offset
src/routeros_lsp/checker/      variables.py and commands.py, the rule implementations
src/routeros_lsp/schema/       loader and name matching for the command database
src/routeros_lsp/features/     diagnostics, completion, hover, symbols, folding
src/routeros_lsp/data/         generated command database, one file per RouterOS version
research/                      Python probes and recorded router answers that back the rules
tools/gen_schema.py            generates the command database from a router
tests/                         unit, conformance, fixtures, fuzz and protocol tests
plugin/                        Claude Code plugin (.lsp.json)
docs/                          grammar, ambiguity register, rules, architecture, configuration, features, releasing
.github/workflows/             ci.yml (pull requests), publish.yml (release to PyPI), claude.yml
```

[docs/architecture.md](docs/architecture.md) describes each stage.

## Conventions

- Fully typed (`mypy --strict` on `src`), formatted with `ruff format`, line length 130. Syntax tree nodes are slotted dataclasses
  compared by identity; narrow them with `isinstance`, not with `kind` strings and `type: ignore`.
- **stdout belongs to the protocol.** Nothing but LSP messages may be written to it, not even a stray `print`. `cli.py` points
  `sys.stdout` at stderr while the server runs. Log through `window/logMessage` or to stderr.
- Every diagnostic is a rule in `rules.py` with an id (`area/name`), a default severity and a **source**: `doc`, `doc-example`,
  `device` or `open`. Never present a `device` or `open` behaviour as the specification; the message says where the rule comes from.
- Prefer a missed error to a false one. A diagnostic on valid input is the worst failure of a language server, so when unsure a
  checker stays quiet or reports a warning. When RouterOS and the documentation disagree, the router decides what is an error and the
  documentation decides what is a warning.
- Offsets inside the analysis are Python string indexes; `Document` converts them to the UTF-16 positions LSP uses. Router error
  columns are 1-based.
- Do not hand-edit `src/routeros_lsp/data/` or `docs/rules.md`; regenerate them.
- The version in `pyproject.toml` is a placeholder (`0.0.0`); the release pipeline computes the real one. Do not bump it by hand.
- Keep functions small and comments rare; explain why, not what. No em dashes in prose.

## Testing

- `tests/test_parser.py`, `test_variables.py`, `test_commands.py`, `test_completion.py`, `test_hover.py`: unit tests per stage.
  `tests/helpers.py` marks the caret with `|`.
- `tests/test_conformance.py`: `tests/conformance/cases.json` holds the router's answers to every probe (built by
  `python research/tools/build_corpus.py`). A case that the implementation does not match goes in `known-gaps.json` with a reason,
  and the test fails when a listed case starts passing, so the list cannot rot. Never delete a case to make the suite pass.
- `tests/test_fixtures.py`: realistic scripts and real `/export` output that RouterOS accepts (`verdicts.json` records its answer).
  The server must report nothing on any of them.
- `tests/test_fuzz.py`: seeded mutations of the corpus; the parser must not raise and its tree must be consistent.
- `tests/test_server.py`: the server on a pipe pair, and the real command over stdio.
- A router is not needed to run the tests. Probing needs one: `research/tools/probe.py` runs a suite, `research/tools/check_files.py`
  checks files, `tools/gen_schema.py` builds the command database. They read the router address from an inventory file or flags and
  never contain credentials.
- A bug fix needs a test that fails without the fix.

## Commits and pull requests

- Conventional Commits; they decide the next version (see [docs/releasing.md](docs/releasing.md)). Branches are
  `<type>/issue-<number>-<short-description>`, with a literal `#` instead of the number when there is no issue; quote them in the
  shell.
- Open pull requests against `master`. Do not push to `master` or merge, unless the maintainer asked you to.
- Merging a change to `src/**` or `pyproject.toml` into `master` publishes a release to PyPI. Treat those merges accordingly.
