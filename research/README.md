# Research harness

How the facts in [docs/grammar.md](../docs/grammar.md) and [docs/ambiguities.md](../docs/ambiguities.md) were gathered. This is
Python research tooling, not part of the server. The recorded answers it produced are replayed by `tests/conformance/`, which needs
no router.

## What is here

| Path | Purpose |
|---|---|
| `suites/suite*.py` | The probes. Each entry is `(id, mode, snippet, note)`. Suites 1 to 6 cover lexical rules, variables, values, commands and state; 7 to 11 layout, adjacency, bare-word characters, expressions and closing brackets; 12 and 13 odd statement starts and undeclared reads; 14 and 15 declarations and what a read returns; 16 and 17 menu path state; 18 and 19 bare words and `find`. |
| `results/suite*.txt` | What RouterOS 7.21.4 answered, one line per probe. |
| `results/command-tree-summary.json` | Size of the command tree read from `/console/inspect`. |
| `tools/probe.py` | Runs a suite against a router and prints one line per probe. |
| `tools/build_corpus.py` | Turns the `check` probes and their answers into `tests/conformance/cases.json`. |
| `tools/check_files.py` | Compiles local `.rsc` files with `dry-run` and prints a verdict for each (used for `tests/fixtures/verdicts.json`). |
| `tools/differential.py` | Generates command lines from the command database (valid, abbreviated, repeated, with an unknown parameter, with a flag) and records what the router says about each. |
| `tools/walk.py` | Reads the command tree with `/console/inspect` (read only). The command database itself is made by `../tools/gen_schema.py`. |
| `tools/h2t.py` | Turns a Confluence page into text, used to read the documentation. |

## Probe modes

| Mode | What it does | Changes the router? |
|---|---|---|
| `check` | Uploads the snippet as `lspprobe.rsc` and runs `/import file-name=lspprobe.rsc verbose=yes dry-run`. Reports errors with line and column. | No. Nothing is executed. |
| `eval` | Runs a single-line pure expression on the console. | No. |
| `run` | A real `/import` of a benign snippet (`:put`, `:local`, read-only `print`). | No configuration; it may create and then remove a global variable. |

`:parse` is not a usable oracle: it compiles lazily, so a bad script is accepted until the result is used.

`/import dry-run` stops reporting after 100 errors in one file. Tools that compile many lines (`gen_schema.py`,
`differential.py`) resume at the line where the limit was reached.

## Re-running

```bash
python -m venv .venv && .venv/Scripts/python -m pip install paramiko
# the harness reads the router address and login from an inventory file of the
# mikrotik-mcp project; set MIKROTIK_INVENTORY_FILE to yours and adjust probe.py
MIKROTIK_INVENTORY_FILE=/path/to/inventory.yml .venv/Scripts/python tools/probe.py suites/suite1_lexical.py RouterA
```

After adding a suite, register it in `tools/build_corpus.py` and run `python research/tools/build_corpus.py`. Then run the tests
and put every case the server does not match yet into `tests/conformance/known-gaps.json` with a reason.

The differential run compares the checker with the router on thousands of generated lines:

```bash
MIKROTIK_INVENTORY_FILE=... python research/tools/differential.py src/routeros_lsp/data/routeros-7.21.4.json.gz answers.json
```

The harness never contains credentials; it reads them from the inventory at run time. Probe files are removed from the router at
the end of each run.

## Documentation text

The Scripting page itself is not copied here (it is MikroTik's content). `tools/h2t.py` converts a downloaded copy for reading.
