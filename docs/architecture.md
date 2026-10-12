# Architecture

```
text --> parser --> syntax tree --> binder --> checker --> findings --> LSP diagnostics
                        |                          ^
                        |            command database (data/*.json.gz)
                        +--> completion, hover, symbols, folding
```

Everything is TypeScript on Node 20 or newer. The only libraries are `vscode-languageserver` and
`vscode-languageserver-textdocument`, bundled into `lib/cli.mjs` by esbuild, so the package has no runtime dependencies. The
command database is read from `data/` at run time.

## Stages

| Stage | Where | Input and output |
|---|---|---|
| Parser | `src/syntax/parser.ts` | Text to a tree (`ast.ts`) and syntax diagnostics. Hand-written, scannerless and recursive descent, because RouterOS lexes by context: `#` is a comment only where a command starts, a word is whatever a command argument allows, and `{ }` is a block or an array depending on where it stands. It recovers from errors, so the rest of the file is still analysed. |
| Binder | `src/binder/` | Tree to scopes, declarations and variable references, with the scope rules RouterOS applies (line scopes in an imported file, function bodies that see nothing of the code around them). |
| Variable checks | `src/checker/variables.ts` | Binder output to findings: `:set` of an undeclared name, reads of variables that do not exist where they are read, invalid names. |
| Command checks | `src/checker/commands.ts` | Tree and command database to findings. Tracks the menu path through the file as RouterOS does, resolves every word of a command line (menu, command, parameter, with abbreviations), and records what each one resolved to for hover and completion. |
| Analysis | `src/analyze.ts` | Runs the stages, applies the severity settings and returns the tree, the binder result and the findings. |
| Features | `src/features/` | Diagnostics, completion, hover, document symbols and folding ranges on top of an analysis. |
| Server | `src/server.ts`, `src/cli.ts` | LSP wiring over stdio. A failure inside one feature is logged and answered with an empty result. |

## Rules and their sources

Every diagnostic is a rule in `src/rules.ts` with an id, a default severity and a source (`doc`, `doc-example`, `device`,
`open`). The source is shown in the message when the rule is not the documented language, so a quirk of RouterOS 7.21.4 is
never presented as the specification. [rules.md](rules.md) lists them. When the documentation and the device disagree the
device decides what is an error (a script that fails to compile is an error), and the documentation decides what is merely
reported as a warning.

## Evidence

The behaviour the stages implement was measured, not remembered:

- `research/suites/` holds probe scripts. `research/tools/probe.py` runs them against a router with
  `/import ... dry-run`, which reports every error with line and column and executes nothing. The answers are in
  `research/results/`.
- `research/tools/build_corpus.py` turns the recorded answers into `test/conformance/cases.json`. The conformance test replays
  every case and fails on a disagreement unless the case is in `known-gaps.json` with a reason.
- `test/fixtures/` holds realistic scripts and real `/export` output, each judged by the router. The server must report
  nothing on any of them.
- [ambiguities.md](ambiguities.md) is the register of every point where the documentation is silent or differs from the router.

## The command database

`tools/gen_schema.py` walks `/console/inspect` for menus, commands, parameters, descriptions, types and values, and compiles
probe lines to learn which parameters are required and how many unnamed arguments a command takes. The result is
`data/routeros-<version>.json.gz`. Keys are short (`c` children, `a` arguments, `r` required, `u` unnamed count, `d`
description, `t` type, `e` values, `x` values are complete); the types are in `src/schema/schema.ts`.

## Adding a rule

1. Find out what RouterOS does: add a probe to a suite in `research/suites/`, run it, keep the result.
2. Register the row in [ambiguities.md](ambiguities.md) if the documentation is silent or wrong.
3. Add the rule to `src/rules.ts`, implement it in the parser or a checker, and run `UPDATE_DOCS=1 npm test` to refresh
   [rules.md](rules.md).
4. Add tests, and rebuild the corpus with `python research/tools/build_corpus.py`.
