# routeros-lsp

A [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) server for MikroTik RouterOS scripts (`.rsc` files).

It gives editors and AI coding agents immediate feedback while they write RouterOS scripts: syntax errors, unknown menus,
commands and parameters, variable scope mistakes, and completion and hover from the RouterOS command list. It follows the
[RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting), and where the
documentation is silent or a real router behaves differently, the behaviour was measured on a router and written down in
[docs/ambiguities.md](docs/ambiguities.md) instead of guessed.

> **Status: version 0.1, in development, not published to npm yet.** Build it from source as described below.

## What it reports

| Area | Examples |
|---|---|
| Syntax | Unterminated strings, bad escapes, unbalanced brackets, two values with no space between them, a `#` comment after a command (RouterOS reads it as an argument and rejects the line), a line break inside `( )`, whitespace before `=`. |
| Variables | `:set` of a variable that is not declared in scope, a local used on a later line of an imported file (where it is empty), undeclared variables, invalid names. |
| Menus and commands | An unknown menu, command or parameter with a "did you mean", an ambiguous abbreviation, a parameter given twice, too many unnamed arguments, a missing required parameter. The menu path is tracked as RouterOS does, so relative commands after `/ip address` are checked in that menu. |

Hover and completion use the same command list: menus and commands, parameters (required ones first), values after `name=`, and
the variables in scope after `$`. There is also a symbol outline and folding. [docs/features.md](docs/features.md) has the
details and the limits; [docs/rules.md](docs/rules.md) lists every rule with its default severity.

A finding is labelled when it rests on RouterOS behaviour that the documentation does not describe, so a quirk of one version
is never presented as the language specification.

## Install and use

Build it from source (Node.js 20 or newer):

```bash
git clone https://github.com/wiresage/routeros-lsp.git
cd routeros-lsp
npm install
npm run build
node lib/cli.mjs --version
```

The server speaks LSP over stdio:

```bash
node lib/cli.mjs --stdio
```

Link it as `routeros-lsp` if you want that name on your `PATH`:

```bash
npm link
```

### Claude Code

[`plugin/`](plugin) is a Claude Code plugin that starts the server for `.rsc` files (language id `routeros`). It expects the
`routeros-lsp` command on your `PATH`. Settings go into its `.lsp.json`; see [docs/configuration.md](docs/configuration.md).

### Other editors

Start `routeros-lsp --stdio` for the language id `routeros` from any LSP client.

## The command list

Menus, commands and parameters come from a database generated from a RouterOS 7.21.4 CHR with `/console/inspect`
(`data/routeros-7.21.4.json.gz`). A CHR has no wireless, LTE or switch-chip packages and some parameters exist only on some
hardware, so unknown-name findings are warnings by default. To cover your own hardware, generate the database from your router
(nothing is executed or changed on it) and point the `schema` setting at it:

```bash
pip install paramiko
ROUTEROS_PASSWORD=... python tools/gen_schema.py --host 192.0.2.1 --user admin --out my-router.json.gz
```

## Develop

```bash
npm install
npm run typecheck
npm run lint
npm test
npm run build      # bundles the server into lib/cli.mjs
```

The tests need no router. See [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and
[docs/architecture.md](docs/architecture.md).

## How the language was pinned down

- [docs/grammar.md](docs/grammar.md): the grammar derived from the documentation, each rule tagged as documented, shown by an
  example, observed on a device, or open.
- [docs/ambiguities.md](docs/ambiguities.md): every gap and conflict, with evidence from RouterOS 7.21.4 and the default used.
- [research/](research/): the probes that produced that evidence. RouterOS can check a script without running it
  (`/import file.rsc verbose=yes dry-run`), which is the test oracle for this project; `test/conformance/` replays more than
  700 recorded answers.

## License

[MIT](LICENSE)
