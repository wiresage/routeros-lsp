# Ambiguity and conflict register

Per your instruction, nothing here was decided by guessing. Each row says what the documentation says, what RouterOS 7.21.4
does (probe ids refer to `research/results/suite*.txt`, run through `/import ... dry-run` or the console), and a proposed default
that is yours to accept or change. "Doc" = the Scripting page. "Device" = observed behaviour, not documentation.

Kinds: **GAP** the docs are silent. **CONFLICT** the device contradicts the docs. **INTERNAL** the docs contradict themselves.

## Lexical

| Id | Kind | Docs | Device evidence | Proposed default |
|---|---|---|---|---|
| L-01 | CONFLICT | Comment runs to end of line; example shows `; # comment`. | `:put 1 # c` is an error (c1, c3, c8); after `;` or at line start it works (c2, c11). | Error, message cites the docs. |
| L-02 | GAP | `#` is not a comment inside a string. | `a#b`, `name=abc#def` are fine (c5, c6). | No diagnostic. |
| L-03 | CONFLICT | A backslash outside a string is illegal. | `:put \ 1` and backslash, space, newline are accepted (j3, j4); comment after `\` is an error (c10). | Error for comment after `\`; warning for the rest. |
| L-04 | GAP | Backslash joins strings. | Backslash, newline and the next line's leading whitespace vanish (j5, j6, x10). | Model it. |
| L-05 | GAP | Silent. | Raw newline inside a string is accepted (j7). | Accept. |
| L-06 | GAP | Silent about BOM. | BOM gives `expected command name` (j10). | Error. |
| L-07 | GAP | Silent about encoding. | Non-ASCII fine in strings and comments (u1, u2); not in names (u3). | Accept in strings and comments. |
| L-09 | INTERNAL | No space between `<param>=`; example lists `from= 1` as correct. | Space before `=` fails, after works (w1-w7). | Error before `=` only. |
| L-10 | GAP | "Whitespace required only where tokens would merge", no token list. | `($a and$b)`, `$aand$b` compile (w11, w12). | No diagnostic. |
| L-11 | GAP | `;` or newline ends a command, "sometimes not required". | `:put 1 :put 2` fails (t1). | Error. |
| L-12 | CONFLICT | `[]` holds one command line. | Several accepted (t10); `( )` rejects `;` (t12). | Warning. |
| L-13 | GAP | Silent. | Stray `}` accepted (g20, g22). | Error. |
| L-15 | GAP | Silent. | Single quotes are not strings (g5, v9). | Error. |
| L-16 | GAP | "Unquoted value" undefined. | Cannot contain space, `"`, `$`, a second `=`; may contain `# / : ,` (g2-g21). | Implement as observed. |

## Variables and scopes

| Id | Kind | Docs | Device evidence | Proposed default |
|---|---|---|---|---|
| V-01 | CONFLICT | Using an undeclared variable is a compile error. | Reading gives nothing (v1-v4); `:set` of an undeclared name is a syntax error (v5-v7). | Error for `:set`; warning for reads. |
| V-02 | GAP | Terminal example shows a syntax error on read. | Not reproduced over SSH exec; interactive terminal untested. | Open. |
| V-03 | GAP | Each terminal line is a scope; files not mentioned. | In an import each top-level command is its own scope (s1-s4). | Model as observed; warn on later use. |
| V-04 | GAP | Inner `:global` needs redeclaring. | At the next top-level line it is visible without (s7); same-block case matches docs (s8, s9). | Follow docs inside a block. |
| V-05 | GAP | Function args are `$a`, `$1`. | Work, never flagged (f1-f4). | No diagnostics inside function bodies for them. |
| V-07 | GAP | "Letters and digits". | ASCII only, digit-first allowed, `_` needs quotes (i1-i8, u3). | As observed. |
| V-08 | CONFLICT | `and or in` cannot be names. | Accepted, as are `true nil not do if global` (i9-i17). | Warning. |
| V-09 | CONFLICT | Default type is `nil`. | `:typeof` says `nothing`; `nil` is a bare string (v3, L35). | Follow device in hover text. |
| V-10 | GAP | Built-in properties are reserved. | Not a compile error (f10). | Needs the command database. |
| V-11 | GAP | Silent. | Interpolated name ends at the first non-alphanumeric (i24). | As observed. |
| V-14 | GAP | Lease and hotspot variables exempt. | No list. | Configurable list. |

## Types, escapes, operators

| Id | Kind | Docs | Device evidence | Proposed default |
|---|---|---|---|---|
| T-01 | GAP | Types listed, literal spellings not. | See docs/grammar.md section 2.7 (L0-L46). `1.5` is an IP; no float. | As observed. |
| T-03 | GAP | Use spaces or parentheses around `/`. | `(10/2)` prints nothing; `10 / 2` is 5 (V5-V9). | Warning. |
| E-01 | INTERNAL | `\f` is 0xFF. | 0x0C (E10). | Docs erratum. |
| E-02 | CONFLICT | `\?` removed in 7.1rc2. | Accepted (E6). | No diagnostic. |
| E-03 | GAP | Hex escapes use capitals. | Lowercase and one-digit hex are errors (E14, E15). | Error. |
| E-04 | GAP | Silent about other escapes. | `\q \e \0 \x41 A \' \/ \#` are errors (E18-E25). | Error. |
| O-01 | GAP | No precedence table. | Usual: `* / %` over `+ -` over `.` over `=`; `&&` over `\|\|`; `!` over `&&`; left associative (A0-A15, R0-R22). | Implement as observed, flag chained relational. |
| O-02 | GAP | Only `!` is NOT. | `not` is not an operator (R9). | Info. |
| O-03 | CONFLICT | Bitwise only on IP types. | Works on integers (O14-O17). | No diagnostic. |
| O-04 | GAP | Silent. | `<` on strings is a runtime error (R16). | Info. |
| O-07 | GAP | Examples use `(a&&b)` without `$`. | Bare names in `( )` are variables (B0-B8). | Treat as variable references. |
| O-08 | GAP | `->` shown in parentheses. | `$a->k` outside parentheses is an error (d3). | Error. |
| O-09 | GAP | `$[]` and `$()` shown inside strings. | Syntax error outside strings (d1, d2). | Error. |

## Arrays, commands, paths, files

| Id | Kind | Docs | Device evidence | Proposed default |
|---|---|---|---|---|
| A-01 | CONFLICT | Quote keys that are not lowercase. | `{A=1}`, `{a-b=1}`, `{a_b=1}` accepted (a6-a10); `{ a=1 }` as a statement and `{}` as an argument fail (a3, a21). | Hint only. Block-or-array decided by context. |
| C-01 | CONFLICT | Global commands must start with `:`. | `put`, `local`, `global`, `typeof`, `do {} on-error`, `if` work without it (p1-p12). | Accept; optional hint. |
| C-02 | GAP | Table of 49 global commands. | 9 more root commands; `break`/`continue` only inside loops (p19). | Use the device-generated database. |
| C-03 | INTERNAL | `:resolve` text says `server-port`, example `port=`. | `port=` fails, `server-port` works (p28, p29). | Docs erratum. |
| C-07 | GAP | Informal syntax notation. | n/a | Need generated schema. |
| C-08 | CONFLICT | `!param` unsets any parameter. | `/ip address set 0 !comment` fails (r7, r8). | Per-menu data needed. |
| C-10 | GAP | Silent. | Any unambiguous prefix works for menus, commands, parameters, flags; ambiguous fails (ab1-ab11). | Resolve prefixes; error if ambiguous. |
| C-11 | GAP | Silent. | Lowercase only (m17, m18). | Error. |
| C-12 | GAP | Silent. | `else=` on the next line or after `;` fails (k1, k4); after `\` works (k2). | Error. |
| C-13 | GAP | `where` expressions not specified. | Property names not validated at compile (q6, q7). | Warning from the schema. |
| C-15 | GAP | Silent. | Value types are only checked at run time (r4). | No error. |
| P-01 | GAP | Mixed path styles in examples. | Space, slash, mixed and relative all work (m1-m6, m19, m20). | Accept all. |
| P-02 | GAP | `/` and `..` listed; path state not described. | Path persists across lines, `;`, into `{}`, `[]`, `do={}`, and after a block ends (b1-b8, n1-n5). | Track path as global state. |
| P-03 | GAP | `.rsc` format barely described. | BOM fails; CRLF, LF, CR fine; real exports use CRLF-style joins `\` (k9-k11). | Document and warn. |
| P-04 | GAP | `import` described briefly. | Statements run one by one; dry-run reports every error. | Use dry-run as the test oracle. |

## Documentation errata (no server decision needed)

`\f` value (E-01); `:resolve` example (C-03); `from= 1` versus the whitespace rule (L-09); "do not define globals in local scopes"
versus the later example; policy list omits `romon`, `winbox`, `api` that the defaults and example use; typos (`reslove`, `[code]`
markup, "specifues").

## Not probed

Interactive terminal behaviour (V-02), RouterOS versions other than 7.21.4, packages missing from a CHR (wireless, LTE), and the
contextual variables of lease and hotspot scripts.
