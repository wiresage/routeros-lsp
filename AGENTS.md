# AGENTS.md

Instructions for AI coding agents working in this repository. Humans should also read [CONTRIBUTING.md](CONTRIBUTING.md).

## Project overview

`routeros-lsp` is a Language Server Protocol server for MikroTik RouterOS scripts (`.rsc`). It reports syntax errors, variable
scope mistakes, unknown menus, commands and parameters, and offers completion and hover, so that editors and AI agents get
immediate feedback on what they write.

- TypeScript, Node.js 20 or newer, ESM. The only libraries are `vscode-languageserver` and `vscode-languageserver-textdocument`;
  they are bundled into `lib/cli.mjs`, so the published package has no runtime dependencies.
- The language is defined by the [RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting),
  summarised in [docs/grammar.md](docs/grammar.md). Where the documentation is silent or a real router disagrees, the case is in
  [docs/ambiguities.md](docs/ambiguities.md). **Read those two files before touching the parser, a checker or any diagnostic.**
- RouterOS itself is the test oracle: `/import file.rsc verbose=yes dry-run` reports every error with line and column and executes
  nothing. Behaviour is measured with it, not recalled.

## Commands

```bash
npm install
npm run typecheck     # tsc --noEmit
npm run lint          # eslint
npm test              # vitest, needs no router
npm run build         # esbuild bundle to lib/cli.mjs
node lib/cli.mjs --version
```

Run typecheck, lint and test before every commit. After changing `src/rules.ts` run `UPDATE_DOCS=1 npm test` to refresh
`docs/rules.md`.

## Architecture

```
text -> parser -> syntax tree -> binder -> checkers -> findings -> LSP diagnostics
                       |                      ^
                       |        command database (data/*.json.gz)
                       +-> completion, hover, symbols, folding
```

```
src/cli.ts            entry point: --stdio, --version, --help
src/server.ts         LSP wiring; a failing feature is logged and answered with an empty result
src/analyze.ts        runs the stages and applies severity settings
src/rules.ts          every diagnostic rule: id, default severity, source, summary
src/config.ts         settings (severities, scope, contextVariables, schema)
src/syntax/           parser (scannerless, recursive descent, error recovery), tree types, walker
src/binder/           scopes, declarations, references, lookups by offset
src/checker/          variables.ts and commands.ts, the rule implementations
src/schema/           loader and name matching for the command database
src/features/         diagnostics, completion, hover, symbols, folding
data/                 generated command database, one file per RouterOS version
research/             Python probes and recorded router answers that back the rules
tools/gen_schema.py   generates the command database from a router
test/                 unit, conformance, fixtures, protocol tests
plugin/               Claude Code plugin (.lsp.json)
docs/                 grammar, ambiguity register, rules, architecture, configuration, features
```

[docs/architecture.md](docs/architecture.md) describes each stage.

## Conventions

- Strict TypeScript. Relative imports use the `.js` extension (`import { x } from './x.js'`).
- **stdout belongs to the protocol.** Nothing but LSP messages may be written to it, not even a stray `console.log`. Log through the
  connection (`connection.console`) or to stderr.
- Every diagnostic is a rule in `src/rules.ts` with an id (`area/name`), a default severity and a **source**: `doc`, `doc-example`,
  `device` or `open`. Never present a `device` or `open` behaviour as the specification; the message says where the rule comes from.
- Prefer a missed error to a false one. A diagnostic on valid input is the worst failure of a language server, so when unsure a
  checker stays quiet or reports a warning. When RouterOS and the documentation disagree, the router decides what is an error and the
  documentation decides what is a warning.
- Positions are UTF-16 string offsets, which is what LSP uses. Router error columns are 1-based.
- Do not hand-edit `data/` or `docs/rules.md`; regenerate them.
- Keep functions small and comments rare; explain why, not what. No em dashes in prose.

## Testing

- `test/syntax`, `test/checker`, `test/features`: unit tests per stage. `test/features/helpers.ts` marks the caret with `|`.
- `test/conformance`: `cases.json` holds the router's answers to every probe (built by `python research/tools/build_corpus.py`). A
  case that the implementation does not match goes in `known-gaps.json` with a reason, and the test fails when a listed case starts
  passing, so the list cannot rot. Never delete a case to make the suite pass.
- `test/fixtures`: realistic scripts and real `/export` output that RouterOS accepts (`verdicts.json` records its answer). The server
  must report nothing on any of them.
- `test/protocol`: the server on a stream pair, and the built binary over real stdio.
- A router is not needed to run the tests. Probing needs one: `research/tools/probe.py` runs a suite, `research/tools/check_files.py`
  checks files, `tools/gen_schema.py` builds the command database. They read the router address from an inventory file or flags and
  never contain credentials.
- A bug fix needs a test that fails without the fix.

## Commits and pull requests

- Conventional Commits. Branches are `<type>/issue-<number>-<short-description>`, with a literal `#` instead of the number when
  there is no issue; quote them in the shell.
- Open pull requests against `main`. Do not push to `main` or merge, unless the maintainer asked you to.
- CI and package publishing are not set up yet; do not add workflows or publish steps without being asked.
