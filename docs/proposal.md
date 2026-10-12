# routeros-lsp: proposed architecture and feature list

Status: in progress. The maintainer asked to go ahead after seeing this plan and did not answer the questions in section 5, so the defaults proposed there are in effect (MIT with copyright WireSage, TypeScript on Node 20 or newer, package and binary `routeros-lsp`, language id `routeros`, extension `.rsc`, plugin in `plugin/`, conformance corpus committed). Each can be changed.
Research: the whole Scripting page, the typescript-language-server repo, the Claude Code `typescript-lsp` plugin and its
plugin reference, and about 330 conformance probes run on RouterOS 7.21.4 (`research/`).

## 1. What the research settled

1. The documentation specifies the language only loosely: no precedence table, no literal spellings, no command catalogue.
   [ambiguities.md](ambiguities.md) lists more than 70 gaps and conflicts, each with device evidence and a proposed default.
2. RouterOS can check a `.rsc` file itself: `/import file.rsc verbose=yes dry-run` reports every error with line and column, flags
   unknown commands and parameters (`bad command name`, `expected end of command`) and missing required arguments, executes nothing.
   It is the test oracle for the whole project.
3. The command database can be generated from the device: `/console/inspect` returns menus, commands, arguments, argument
   descriptions and enum values. A full walk of a CHR gave 427 menus, 4,004 commands, 25,726 arguments: 0.79 MB, 51 KB gzipped.
4. A Claude Code LSP plugin is a small manifest (`command`, `args`, `extensionToLanguage`) around an installed server; the server
   speaks LSP over stdio and must never write anything else to stdout.
5. Prior art is thin: highlighting extensions and two small tree-sitter grammars; no language server found.

## 2. Architecture

Language and runtime: TypeScript on Node.js, ESM, `vscode-languageserver` and `vscode-languageserver-textdocument`
(the same stack as typescript-language-server). Node 20 or newer; typescript-language-server requires 22.22.2, which this
machine (22.14) would not meet. Hand-written scannerless parser: the grammar is context sensitive, so a separate lexer would have
to be told the context anyway, and zero native dependencies keeps the plugin install trivial.

```
text -> parser (scannerless, recursive descent, error recovery)
     -> syntax tree -> binder (scopes, declarations) -> checkers (variables, menu path and commands) -> diagnostics
                                   |                        ^
                          schema (generated command database) ----> completion, hover, signature help
```

Repository layout:

```
routeros-lsp/
  AGENTS.md  README.md  CONTRIBUTING.md  LICENSE
  package.json  tsconfig.json  vitest.config.ts  eslint.config.js
  src/  cli.ts  server.ts  config.ts  rules.ts  analyze.ts
        syntax/  binder/  checker/  schema/  features/
  data/            generated command database per RouterOS version (committed, gzipped)
  tools/           gen_schema.py (walks /console/inspect and compiles probe lines)
  test/            unit, fixtures (.rsc with expected diagnostics), conformance (recorded verdicts), protocol (stdio e2e)
  docs/            grammar.md  ambiguities.md  architecture.md  configuration.md  features.md
  plugin/          Claude Code plugin: .lsp.json  (separate repo is an option)
```

Design rules that follow from the research:

- Every rule has an id, a source tag (`doc`, `doc-example`, `device`, `open`) and a default severity, and its message cites the
  documentation section. Nothing from the `device` or `open` classes is presented as the language specification.
- Where the docs and the device disagree: the device-verified behaviour wins for errors that make a script fail (L-01), and the
  docs win for anything the device merely tolerates (V-08, O-03), reported as a warning. This is the one policy decision I need from you.
- Menu path is state tracked while the file is compiled, in source order; only a path-only line changes it (P-02, P-05, P-06).
- The server is quiet on stdout; logs go to stderr or a file.
- Settings: RouterOS version, severity per rule, extra contextual variable names, strict mode for open items.

## 3. Feature list

**v0.1 (first usable release)**
- Syntax diagnostics: unbalanced `()` `[]` `{}`, unterminated strings, bad escapes, missing separators, comment and line-join rules,
  whitespace around `=`, `else=` placement, BOM, single quotes, unknown `:`-command syntax.
- Semantic diagnostics from the docs: `:set` of an undeclared variable, variable scope across top-level lines and blocks, keyword
  used as a name, hyphenated names without quotes, `/` between literals without spaces.
- Command-database diagnostics: unknown menu or command, unknown or duplicate parameter, missing required parameter, ambiguous
  abbreviation, `!param` on menus that reject it.
- Completion: global commands, menu paths, parameter names, enum values, variables in scope, flags.
- Hover: command and parameter descriptions from the schema, variable declaration.
- Document symbols and folding ranges.

**v0.2**
- Go to definition, references and rename for variables and functions.
- Signature help for global commands and menu commands.
- Semantic tokens; code actions (add `;` before a comment, uppercase hex escape, quote a name, move `else=` onto the line).
- Schema for several RouterOS versions, selectable in settings.

**v0.3**
- `/import`-aware multi-file analysis, `where` clause checking, contextual variable packs (lease, hotspot), optional live
  validation against a device through dry-run.

Out of scope for now: formatting (the docs specify none), CI, releasing and publishing packages, a VS Code extension.

## 4. Testing plan

1. Unit tests per stage (vitest).
2. Every code block of the Scripting page becomes a fixture with its documented outcome.
3. Conformance: the 330 probes become recorded verdicts; `--live` re-runs them against a router.
4. False-positive guard: real `/export` output (also `verbose`) must produce no diagnostics; the router's own export already passes dry-run.
5. Fuzzing the parser for crashes; stdio protocol tests that start the server and drive it like a client.

## 5. Decisions (defaults in effect)

1. Repository: public, `wiresage/routeros-lsp`, MIT.
2. Runtime: TypeScript on Node 20+ as above, or another language.
3. Names: package and binary `routeros-lsp`, language id `routeros`, extension `.rsc`. The npm names `routeros-lsp` and `@wiresage/routeros-lsp` are free.
4. The docs-versus-device policy in section 2.
5. Approve `/console/inspect` as the source of the command database, and which RouterOS versions to cover. CHRs lack wireless, LTE and other
   hardware packages, so those menus would show as unknown unless you can supply an export from a real device.
6. The Claude Code plugin in this repo (`plugin/`) or a separate one.
7. Whether the conformance corpus (device behaviour facts, no MikroTik text) is committed.
8. Rulings on any open item in [ambiguities.md](ambiguities.md) you already have an opinion about.
