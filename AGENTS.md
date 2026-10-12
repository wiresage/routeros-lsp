# AGENTS.md

Instructions for AI coding agents working in this repository. Humans should also read [CONTRIBUTING.md](CONTRIBUTING.md).

## Project overview

`routeros-lsp` is a Language Server Protocol server for MikroTik RouterOS scripts (`.rsc`). It reports syntax errors, unknown
commands and parameters, and offers completions, so that editors and AI agents get immediate feedback on what they write.

- TypeScript, Node.js 20 or newer, ESM. The only libraries are `vscode-languageserver` and `vscode-languageserver-textdocument`;
  they are bundled into `lib/cli.mjs`, so the published package has no runtime dependencies.
- The language is defined by the [RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting),
  summarised in [docs/grammar.md](docs/grammar.md). Where the documentation is silent or a real router disagrees, the case is in
  [docs/ambiguities.md](docs/ambiguities.md). **Read those two files before touching the lexer, parser or any diagnostic.**
- Status: the research, the project scaffold and the plan exist; the server is being built (see [docs/proposal.md](docs/proposal.md)).

## Setup and commands

```bash
npm install
npm run typecheck     # tsc --noEmit
npm run lint          # eslint
npm test              # vitest, needs no router
npm run build         # esbuild bundle to lib/cli.mjs
node lib/cli.mjs --version
```

Run all of typecheck, lint and test before every commit.

## Architecture

```
text -> syntax (scannerless recursive-descent parser, error recovery) -> tree
     -> binder (scopes, symbols, menu-path state) -> checker (rules) -> diagnostics
     schema (generated command database) -> completion, hover, command checks
```

```
src/cli.ts        entry point: --stdio, --version, --help
src/syntax/       parser and tree
src/binder/       scopes and symbols
src/checker/      diagnostic rules (one file per rule group)
src/schema/       loader and queries for the generated command database
src/features/     completion, hover, symbols, folding, ...
src/server.ts     LSP wiring
data/             generated command databases, one per RouterOS version
research/         the Python probes that gathered the evidence in docs/
test/             unit tests, conformance (recorded router verdicts), protocol (stdio) tests
tools/            schema generator and conformance runner
```

Directories appear as the corresponding code lands; do not assume one exists without checking.

## Conventions

- Strict TypeScript. Relative imports use the `.js` extension (`import { x } from './x.js'`).
- **stdout belongs to the protocol.** Nothing but LSP messages may be written to it, not even a stray `console.log`. Log to stderr.
- Every diagnostic rule has an id (`area/name`), a default severity and a **source**: `doc`, `doc-example`, `device` or `open`.
  Messages for `doc` rules name the documentation section. Never present a `device` or `open` behaviour as the specification.
- Positions: the parser works in UTF-16 string offsets, which is what LSP uses. Router error columns are 1-based.
- Do not hand-edit anything under `data/`; regenerate it with the schema tool.
- Keep functions small and comments rare; explain why, not what. No em dashes in prose.

## Testing

- Unit tests live next to the stage they test under `test/`. Use fixtures in `test/fixtures/` for `.rsc` input.
- Conformance: `test/conformance/cases.json` holds recorded router verdicts (`/import ... dry-run`). A mismatch is either a bug or an
  entry in the known-gaps list with a reason. Never delete a case to make the suite pass.
- A router is not required to run the tests. The research tooling in `research/` needs one and is only for adding evidence.
- A bug fix needs a test that fails without the fix.

## Commits and pull requests

- Conventional Commits. Branches are `<type>/issue-<number>-<short-description>`, with a literal `#` instead of the number when
  there is no issue; quote them in the shell.
- Open pull requests against `main`. Do not push to `main` or merge, unless the maintainer asked you to.
- CI and package publishing are not set up yet; do not add workflows or publish steps without being asked.
