# Features

What the server does today, and what it does not.

## Diagnostics

Pushed with `textDocument/publishDiagnostics` when a document opens or changes. Each diagnostic carries its rule id as `code`
and `routeros-lsp` as `source`. The complete list is in [rules.md](rules.md).

| Area | Reports |
|---|---|
| Syntax | Unterminated strings, invalid escapes, bad `$` in strings, unbalanced `( ) [ ] { }`, stray closers, two values with no space between them, whitespace before `=`, a `#` that is not a comment, two commands on a line without `;`, characters RouterOS rejects (non-ASCII outside strings, `?`, `'`), line breaks inside `( )`, empty or incomplete expressions, a byte order mark. |
| Variables | `:set` of a name that is not declared in scope, reads of variables that are declared nowhere or whose scope has ended (including a local used on a later line of an imported file), invalid variable names, keywords used as names. |
| Menus and commands | Unknown menu or command (with "did you mean"), ambiguous abbreviations, unknown or repeated parameters, too many unnamed arguments, missing required parameters. Menu path state is tracked the way RouterOS does it, so relative commands after `/ip address` are checked in that menu. |

Hardware-dependent findings (`schema/unknown-command`, `schema/unknown-parameter`) are warnings by default; see
[configuration.md](configuration.md).

## Editing

| Request | Provides |
|---|---|
| `textDocument/completion` | Menus and commands at the start of a line (global commands after `:`), parameters of the command being written (required ones first, flags without `=`), known values after `name=`, variables in scope after `$`, also inside strings. |
| `textDocument/hover` | Description of a menu, command or parameter from the command database, with type, values and required parameters; where a variable was declared. |
| `textDocument/documentSymbol` | Functions (`:global name do={ }`), variables declared with `:global` and `:local`, and the menu path headers that divide an export into sections. |
| `textDocument/foldingRange` | Blocks, commands continued with a backslash, multi-line strings, runs of comment lines. |

## Command line

`routeros-lsp check PATH...` runs the same analysis on files (a directory means every `.rsc` file below it, `-` means standard
input) and prints `path:line:column: severity: message [rule]`, or JSON with `--format json` (plain ASCII, other characters are escaped). Columns count characters, from 1.
The exit status is 0 when there is nothing to fix, 1 when errors were found (`--strict`: also warnings) and 2 when a file cannot be
read or analysed, or an option is wrong. `--scope`, `--schema`, `--severity RULE=LEVEL` and `--context-variable NAME` are the settings from
[configuration.md](configuration.md).

## What is checked against what

- Syntax and variable rules follow RouterOS 7.21.4 as measured with `/import dry-run`; see [ambiguities.md](ambiguities.md).
- The command database is generated from a RouterOS 7.21.4 CHR. Menus of packages a CHR does not have and parameters that exist only
  on some hardware are missing from it. Generate a database from your own router to cover them.
- Parameter values are not checked, although RouterOS rejects some of them when it compiles (a bad value for a yes/no or enumerated
  parameter, a malformed item number). The server accepts what the router rejects here; it does not report what the router accepts.
- A flag written with a value (`print detail=yes`) is reported only for commands that take no unnamed arguments, because the database
  cannot tell a flag from a parameter for the others.
- The properties used in a `where` expression are not checked.
- Checked against the router: the checker agreed with RouterOS 7.21.4 on 16,900 command lines generated from the database
  (research/tools/differential.py) without reporting a single one that the router accepts. It misses about 780 that the router
  rejects, almost all of the kinds above.

## Not yet

Go to definition, references, rename, signature help, semantic tokens, code actions, formatting, several RouterOS versions at once,
and following `/import` into other files. The plan is in [proposal.md](proposal.md).
