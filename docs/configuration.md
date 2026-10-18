# Configuration

The server reads its settings from `initializationOptions` in the `initialize` request and from `settings` in
`workspace/didChangeConfiguration`. The object can be given bare or nested under a `routeros` key. A change takes effect at
once and every open document is checked again. Anything it does not recognise is reported on the client's log and ignored. A notification that carries no settings (`null`, an empty object or an empty `routeros` section) is ignored, and the settings in force stay as they are, because many clients send one after startup just to say that something changed.

| Setting | Values | Default | What it does |
|---|---|---|---|
| `severities` | object of rule id to `error`, `warning`, `information`, `hint` or `off` | `{}` | Changes the severity of a rule or turns it off. The rules are listed in [rules.md](rules.md). |
| `scope` | `import` or `script` | `import` | How variable scope is judged. See below. |
| `contextVariables` | array of names | `[]` | Variables RouterOS provides to the script, so they are not reported as undeclared. The DHCP lease script variables `leaseBound`, `leaseServerName`, `leaseActMAC` and `leaseActIP` are always included. |
| `schema` | `bundled`, `off` or the path of a file | `bundled` | The command database used to check menus, commands and parameters and to complete them. |

## Scope: `import` or `script`

In a file that is imported with `/import`, or pasted into the terminal, every **line** is a scope of its own. Commands
separated by `;` on the same line share it; a block or a backslash join keeps its commands on one line. A `:local` on one line
is therefore gone on the next, and `:set` of it is a syntax error (see V-15 to V-17 in [ambiguities.md](ambiguities.md)).
This is the default.

The source of a `/system script`, a scheduler or a netwatch is one scope for the whole text. Set `scope` to `script` for files
that are used that way.

## Severities

`schema/unknown-command` and `schema/unknown-parameter` are warnings by default because the bundled database is generated
from a RouterOS CHR: menus of packages that a CHR does not have (wireless, LTE ...) and parameters that only some hardware has
are not in it. If you generate the database from your own router (below) you can make them errors:

```json
{ "severities": { "schema/unknown-command": "error", "schema/unknown-parameter": "error" } }
```

## A command database from your own router

```bash
pip install paramiko
ROUTEROS_PASSWORD=... python tools/gen_schema.py --host 192.0.2.1 --user admin --out my-router.json.gz
```

Nothing is executed and nothing is changed on the router; the tool reads `/console/inspect` and compiles probe lines with
`/import ... dry-run`. It takes a few minutes. Then:

```json
{ "schema": "/path/to/my-router.json.gz" }
```

## Command line

`routeros-lsp check` takes the same settings as options: `--scope import|script`, `--schema bundled|off|FILE`,
`--severity RULE=LEVEL` (repeatable) and `--context-variable NAME` (repeatable). They go through the same validation as the
editor settings; a wrong one is an error with exit status 2 instead of a log line.

## Claude Code

The plugin in [`plugin/`](../plugin) starts the server for `.rsc` files. Settings go into its `.lsp.json`:

```json
{
  "routeros": {
    "command": "routeros-lsp",
    "args": ["--stdio"],
    "extensionToLanguage": { ".rsc": "routeros" },
    "initializationOptions": {
      "scope": "script",
      "severities": { "vars/undeclared-read": "off" }
    }
  }
}
```

## Other editors

Any LSP client can start `routeros-lsp --stdio` for the language id `routeros`. The server writes nothing but protocol messages
to stdout; log output goes to the client through `window/logMessage`.
