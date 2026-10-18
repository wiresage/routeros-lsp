# Architecture

```
text --> parser --> syntax tree --> binder --> checker --> findings --> LSP diagnostics
                        |                          ^
                        |            command database (routeros_lsp/data/*.json.gz)
                        +--> completion, hover, symbols, folding
```

Everything is Python 3.10 or newer with no runtime dependencies: the JSON-RPC framing (`Content-Length` headers over stdio) and the
LSP handling are written by hand in `server.py`. The command database ships inside the package and is read with
`importlib.resources`.

## Stages

| Stage | Where | Input and output |
|---|---|---|
| Parser | `syntax/parser.py` | Text to a tree (`syntax/ast.py`) and syntax diagnostics. Hand-written, scannerless and recursive descent, because RouterOS lexes by context: `#` is a comment only where a command starts, a word is whatever a command argument allows, and `{ }` is a block or an array depending on where it stands. It recovers from errors, so the rest of the file is still analysed. Nesting is limited to 100 levels and the recursion limit is raised for the call, so hostile input ends in a diagnostic, not a crash. |
| Binder | `binder/` | Tree to scopes, declarations and variable references, with the scope rules RouterOS applies (line scopes in an imported file, function bodies that see nothing of the code around them). |
| Variable checks | `checker/variables.py` | Binder output to findings: `:set` of an undeclared name, reads of variables that do not exist where they are read, invalid names. |
| Command checks | `checker/commands.py` | Tree and command database to findings. Tracks the menu path through the file as RouterOS does, resolves every word of a command line (menu, command, parameter, with abbreviations), and records what each one resolved to for hover and completion. |
| Analysis | `analyze.py` | Runs the stages, applies the severity settings and returns the tree, the binder result and the findings. |
| Features | `features/` | Diagnostics, completion, hover, document symbols and folding ranges on top of an analysis. |
| Documents | `document.py` | Holds the text of an open file and converts between Python string offsets and the line and UTF-16 column positions LSP uses. |
| Command line | `cli.py`, `cli_check.py` | `routeros-lsp check` runs the analysis on files, directories or standard input and prints the findings as text or JSON, with an exit status for CI. It builds the same settings object as the server, so the two cannot disagree. |
| Server | `server.py`, `cli.py` | LSP wiring over stdio. A reader thread feeds a queue, so a burst of edits is analysed once, for the newest text. The analysis of a document is cached by its revision and the settings. A failure inside one feature is logged and answered with an empty result, and an analysis that fails on one document is logged and clears that document's diagnostics without touching the others. A frame whose body is not valid JSON, or not a JSON object, is answered with the JSON-RPC error `-32700` or `-32600` and the session goes on. So is a `Content-Length` that is not a plain number of at most 64 MiB (`-32600`), after which the reader looks for the next header. |

All paths above are below `src/routeros_lsp/`.

## Rules and their sources

Every diagnostic is a rule in `rules.py` with an id, a default severity and a source (`doc`, `doc-example`, `device`,
`open`). The source is shown in the message when the rule is not the documented language, so a quirk of RouterOS 7.21.4 is
never presented as the specification. [rules.md](rules.md) lists them. When the documentation and the device disagree the
device decides what is an error (a script that fails to compile is an error), and the documentation decides what is merely
reported as a warning.

## Evidence

The behaviour the stages implement was measured, not remembered:

- `research/suites/` holds probe scripts. `research/tools/probe.py` runs them against a router with
  `/import ... dry-run`, which reports every error with line and column and executes nothing. The answers are in
  `research/results/`.
- `research/tools/build_corpus.py` turns the recorded answers into `tests/conformance/cases.json`. The conformance test replays
  every case and fails on a disagreement unless the case is in `known-gaps.json` with a reason.
- `tests/fixtures/` holds realistic scripts and real `/export` output, each judged by the router. The server must report
  nothing on any of them.
- [ambiguities.md](ambiguities.md) is the register of every point where the documentation is silent or differs from the router.

## The command database

`tools/gen_schema.py` walks `/console/inspect` for menus, commands, parameters, descriptions, types and values, and compiles
probe lines to learn which parameters are required and how many unnamed arguments a command takes. The result is
`src/routeros_lsp/data/routeros-<version>.json.gz`. Keys are short (`c` children, `a` arguments, `r` required, `u` unnamed count,
`d` description, `t` type, `e` values, `x` values are complete, `f` flag); the format is described at the top of
`schema/schema.py`.

## Speed

Analysing a file takes about 0.3 s per 5,000 lines and 1.5 s per 20,000 lines on a laptop, almost all of it in the parser and the
command checker. The server drops intermediate edits, so typing in a large export stays responsive; the editor shows the result
of the last edit when it arrives.

## Adding a rule

1. Find out what RouterOS does: add a probe to a suite in `research/suites/`, run it, keep the result.
2. Register the row in [ambiguities.md](ambiguities.md) if the documentation is silent or wrong.
3. Add the rule to `rules.py`, implement it in the parser or a checker, and run `UPDATE_DOCS=1 pytest tests/test_docs.py` to
   refresh [rules.md](rules.md).
4. Add tests, and rebuild the corpus with `python research/tools/build_corpus.py`.
