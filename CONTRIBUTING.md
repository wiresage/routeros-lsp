# Contributing

Thanks for helping. This project has one unusual rule: **the language is defined by evidence, not by memory or habit.** Before
changing how a piece of RouterOS syntax is handled, find out what the documentation says and what a router does, and record it.

## Setup

Node.js 20 or newer.

```bash
git clone https://github.com/wiresage/routeros-lsp.git
cd routeros-lsp
npm install
npm run typecheck && npm run lint && npm test
```

No router is needed for the tests.

## Where things go

| You want to | Change |
|---|---|
| Fix how text is tokenized or parsed | `src/syntax/parser.ts`, with a test in `test/syntax/` |
| Fix variable scope or name rules | `src/binder/binder.ts` or `src/checker/variables.ts`, with a test in `test/checker/` |
| Fix how menus, commands and parameters are checked | `src/checker/commands.ts`, with a test in `test/checker/commands.test.ts` (it uses the small schema in `test/fixtures/mini-schema.json`) |
| Add or change a diagnostic | `src/rules.ts` plus the stage that reports it; then `UPDATE_DOCS=1 npm test` |
| Change the command database | regenerate it with `tools/gen_schema.py`; never edit `data/*.json.gz` by hand |
| Add a behaviour fact about RouterOS | a probe in `research/suites/`, its recorded answer in `research/results/`, a row in `docs/ambiguities.md` if the documentation is silent or wrong, then `python research/tools/build_corpus.py` |
| Add an LSP feature | `src/features/`, wired in `src/server.ts`, with unit tests and a protocol test in `test/protocol/` |

## Rules for diagnostics

Every rule has an id (`area/name`), a default severity and a **source**:

| Source | Meaning |
|---|---|
| `doc` | The documentation states it. |
| `doc-example` | Not stated, but shown by a documentation example. |
| `device` | Observed on a router, not documented. |
| `open` | The documentation is silent or contradictory. |

Do not present a `device` or `open` behaviour as if the documentation specified it. When the documentation and a router disagree,
add a row to `docs/ambiguities.md`; the project policy is that the router decides what is an error (a script that fails to compile)
and the documentation decides what is merely reported as a warning.

A diagnostic on valid input is worse than a missed error. If you are not sure RouterOS rejects something, report it as a warning or
not at all.

## Measuring RouterOS

You need a router (a CHR in a VM or container is enough). Probe suites are Python files that list snippets; `research/tools/probe.py`
uploads each one and runs `/import file.rsc verbose=yes dry-run`, which reports every error with its line and column and executes
nothing. See [research/README.md](research/README.md). Probes must not change the router's configuration.

## Testing

- `npm test` runs everything that needs no router.
- Conformance cases are recorded router answers in `test/conformance/`. A case the implementation does not match yet goes in the
  known-gaps list with a reason; it must not be deleted, and the test fails when a listed case starts to pass.
- Real `/export` output and the scripts in `test/fixtures/` must produce no diagnostics. Add a file there, record its verdict with
  `research/tools/check_files.py`, and the test picks it up.
- A bug fix needs a test that fails without it.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/): `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`, `build`.
- Branches: `<type>/issue-<number>-<short-description>`; use a literal `#` instead of the number when there is no issue
  (`fix/issue-#-escape-handling`). Quote such names in the shell.
- Open pull requests against `main`. Keep each one to a single concern.
- The server must never write anything but LSP messages to stdout.

## Reporting problems

Open an issue. For a wrong diagnostic, include the smallest script that shows it and, if you can, what
`/import file.rsc verbose=yes dry-run` says on your router and which RouterOS version it is.
