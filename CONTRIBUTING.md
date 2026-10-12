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

## Where things go

| You want to | Change |
|---|---|
| Fix how text is tokenized or parsed | `src/syntax/`, with a test in `test/syntax/` |
| Add or change a diagnostic | a rule in `src/checker/rules/`, registered in the rule table, with a test |
| Change the command database | regenerate it with the schema tool; never edit `data/*.json.gz` by hand |
| Add a behaviour fact about RouterOS | a probe in `research/suites/`, its recorded verdict in `test/conformance/`, and a row in `docs/ambiguities.md` if the documentation is silent or wrong |
| Add an LSP feature | `src/features/`, with a protocol test in `test/protocol/` |

## Rules for diagnostics

Every rule has an id (`area/name`), a severity and a **source**:

| Source | Meaning |
|---|---|
| `doc` | The documentation states it. The message names the section. |
| `doc-example` | Not stated, but shown by a documentation example. |
| `device` | Observed on a router, not documented. |
| `open` | The documentation is silent or contradictory. Off or a hint by default. |

Do not present a `device` or `open` behaviour as if the documentation specified it. When the documentation and a router
disagree, add a row to `docs/ambiguities.md`; the project policy is that the device wins for errors that make a script fail,
and the documentation wins for what the device merely tolerates, reported as a warning.

## Testing

- `npm test` runs everything that needs no router.
- Conformance cases are recorded router verdicts in `test/conformance/`. A case the implementation does not match yet goes in
  the known-gaps list with a reason; it must not be deleted.
- Real `/export` output must produce no diagnostics.
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
