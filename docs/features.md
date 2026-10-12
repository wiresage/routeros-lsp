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

## What is checked against what

- Syntax and variable rules follow RouterOS 7.21.4 as measured with `/import dry-run`; see [ambiguities.md](ambiguities.md).
- The command database is generated from a RouterOS 7.21.4 CHR. Menus of packages a CHR does not have and parameters that exist only
  on some hardware are missing from it. Generate a database from your own router to cover them.
- Parameter values are not checked: RouterOS itself checks most of them only when a command runs.
- The properties used in a `where` expression are not checked.

## Not yet

Go to definition, references, rename, signature help, semantic tokens, code actions, formatting, several RouterOS versions at once,
and following `/import` into other files. The plan is in [proposal.md](proposal.md).
