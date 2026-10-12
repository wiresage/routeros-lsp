# routeros-lsp

A [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) server for MikroTik RouterOS scripts (`.rsc` files).

It exists to give editors and AI coding agents immediate feedback while they write RouterOS scripts: syntax errors, unknown
commands and parameters, and completions. It is built to follow the
[RouterOS scripting documentation](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting), and every place where that
documentation is silent or disagrees with a real router is written down in [docs/ambiguities.md](docs/ambiguities.md) instead of
being guessed.

> **Status: under development, not released.** The repository currently holds the research that defines the language
> ([grammar](docs/grammar.md), [ambiguity register](docs/ambiguities.md), [plan](docs/proposal.md)) and the project scaffold.
> The server is being built toward its first version. Nothing is published to npm yet.

## Planned features

| Area | What you get |
|---|---|
| Syntax diagnostics | Unbalanced `()` `[]` `{}`, unterminated strings, invalid escapes, missing separators, comment and line-join rules, whitespace around `=`. |
| Semantic diagnostics | Variable scope rules from the documentation, `:set` of an undeclared variable, keywords used as names. |
| Command diagnostics | Unknown menu, command or parameter, missing required parameter, ambiguous abbreviations, from a command database generated from RouterOS itself. |
| Completion and hover | Global commands, menu paths, parameter names, enum values, variables in scope, descriptions. |
| Navigation | Document symbols, folding ranges, go to definition, references, rename for variables and functions. |

The full list, by release, is in [docs/proposal.md](docs/proposal.md).

## Install and use

Not yet available. Once released it will install from npm and run over stdio:

```bash
npm install -g routeros-lsp
routeros-lsp --stdio
```

It will also ship a Claude Code plugin configuration (language `routeros`, extension `.rsc`).

## Develop

Needs Node.js 20 or newer.

```bash
npm install
npm run typecheck
npm run lint
npm test
npm run build      # bundles the server into lib/cli.mjs
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

## How the language was pinned down

- [docs/grammar.md](docs/grammar.md): the grammar derived from the documentation, each rule tagged as documented, shown by an
  example, observed on a device, or open.
- [docs/ambiguities.md](docs/ambiguities.md): every gap and conflict, with evidence from RouterOS 7.21.4 and a proposed default.
- [research/](research/): the probes that produced that evidence. RouterOS can check a script without running it
  (`/import file.rsc verbose=yes dry-run`), which is the test oracle for this project.

## License

[MIT](LICENSE)
