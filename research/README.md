# Research harness

How the facts in [docs/grammar.md](../docs/grammar.md) and [docs/ambiguities.md](../docs/ambiguities.md) were gathered. This is
Python research tooling, not part of the server. The TypeScript conformance runner under `tools/` replaces it for day-to-day use;
the recorded verdicts it checks come from here.

## What is here

| Path | Purpose |
|---|---|
| `suites/suite*.py` | The probes. Each entry is `(id, mode, snippet, note)`. |
| `results/suite*.txt` | What RouterOS 7.21.4 answered, one line per probe. |
| `results/command-tree-summary.json` | Size of the command tree read from `/console/inspect`. |
| `tools/probe.py` | Runs a suite against a router and prints one line per probe. |
| `tools/walk.py` | Reads the command tree with `/console/inspect` (read only). |
| `tools/h2t.py` | Turns a Confluence page into text, used to read the documentation. |

## Probe modes

| Mode | What it does | Changes the router? |
|---|---|---|
| `check` | Uploads the snippet as `lspprobe.rsc` and runs `/import file-name=lspprobe.rsc verbose=yes dry-run`. Reports errors with line and column. | No. Nothing is executed. |
| `eval` | Runs a single-line pure expression on the console. | No. |
| `run` | A real `/import` of a benign snippet (`:put`, `:local`, read-only `print`). | No configuration; it may create and then remove a global variable. |

`:parse` is not a usable oracle: it compiles lazily, so a bad script is accepted until the result is used.

## Re-running

```bash
python -m venv .venv && .venv/Scripts/python -m pip install paramiko
# the harness reads the router address and login from an inventory file of the
# mikrotik-mcp project; point MIKROTIK_INVENTORY_FILE at yours and adjust probe.py
.venv/Scripts/python tools/probe.py suites/suite1_lexical.py RouterA
```

The harness never contains credentials; it reads them from the inventory at run time. Probe files are removed from the router at
the end of each run.

## Documentation text

The Scripting page itself is not copied here (it is MikroTik's content). `tools/h2t.py` converts a downloaded copy for reading.
