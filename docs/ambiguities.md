# Ambiguity and conflict register

Nothing here was decided by guessing. Each row says what the documentation says, what RouterOS 7.21.4
does (probe ids refer to `research/results/suite*.txt`, run through `/import ... dry-run` or the console), and the default the server uses. Defaults can be changed with the severity settings. "Doc" = the Scripting page. "Device" = observed behaviour, not documentation.

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
| L-17 | GAP | Silent about line breaks inside brackets. | A bare line break inside `( )` is an error (z1, z3, z4, z9); a backslash join is fine (e71 to e74). `[ ]` and `{ }` hold commands, so a line break separates them (z2, z5 to z8). | Error. |
| L-18 | GAP | A comment "may be placed after `;`", nothing about the places where `#` is read as a comment. | `#` starts a comment at the start of a command: after `;`, a line break, `{` or `[`, and at column 1 of a line that follows a backslash join (z20 to z30). Anywhere else it is an ordinary word character: `:log info #x` is valid (y16). That is why a trailing comment fails: the words in it are extra arguments (y13, y14), also after `}` (z23, z24). Indented `#` after a join fails (z31). A comment after `;` inside an array literal fails (z33). | Error for a word that starts with `#` after the first word, until the command database can say whether the extra argument is accepted. |
| L-19 | GAP | "Whitespace is required only where concatenation would read as a different token", with no token list. | Two values written with nothing between them are an error for every pair of word, string, variable, group, substitution and block, whatever character joins them (y1 to y11, s1 to s89), and after a closing bracket (`}else=`, `)do=`, `]do=`: k20 to k32). Inside `( )` they are accepted (e1 to e8). | Error outside `( )`. |
| L-20 | GAP | Extends L-16. | A bare word may contain anything except whitespace, `;` `"` `$` `[` `]` `(` `)` `{` `}` `=` `\`, `?`, `'`, a backtick and non-ASCII characters (z80 to z94, u10 to u16). | As observed. |
| L-21 | GAP | Silent. | A lone `:` is accepted and does nothing, `::` is an error (u35 to u38). A lone `/` resets the menu path (z48, z49). | As observed. |
| L-22 | GAP | Silent. | A command line cannot start with a string, `=`, `!`, `,`, `~` or `*`, and its command and menu words are lowercase (u20 to u34, u50, m17, m18). | Error. |
| L-23 | GAP | Documents `\$` for a literal dollar sign. | A `$` inside a string that is followed by anything but a name, `(` or `[` is an error, so a regular expression `"^ether[0-9]+$"` needs `\$` (z115 to z118, found while writing the fixtures). | Error. |

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
| V-15 | GAP | Using an undeclared variable is a compile error. | `:set` of a name that is not declared is the compile error. The name must have been declared earlier in the same or an enclosing block by `:local`, `:global`, or the variable of `:for`, `:foreach` or `:onerror`. A function body sees none of the declarations around it and cannot set its arguments. Quoted names and array elements are not checked (d1 to d38, h25, h26). | Error `vars/set-undeclared`. |
| V-16 | GAP | Each terminal line is a scope; files are not mentioned. | In an imported file the scope is the line. Commands separated by `;` on one line share it, a block or backslash join keeps a command on its line, and the next line starts a new scope (d1, h25, y58 to y61). The source of a `/system script` is one scope. | Setting `scope`, default `import`. |
| V-17 | GAP | Silent about what a read returns. | Run on the device: a local declared on an earlier line reads empty (q1); a global is found by name from anywhere, also inside a function (q2, q3); an outer local is invisible inside a function body (q5) and visible inside `do=` (q6); loop variables are gone after the loop (q12, q13); a name that was never declared reads empty (q10). | Warnings `vars/local-out-of-scope` and `vars/undeclared-read`, once per variable. |
| V-18 | GAP | "Letters and digits". | Also for the variables of `:for` and `:foreach`; the first invalid character is the error position; `:local $a` and `:local a=1` are errors (n1 to n26). | Error `vars/invalid-name`. |

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
| O-10 | GAP | No expression grammar. | In `( )` operands may stand next to each other (e1 to e8). Errors: an empty `()`, an operator with no right operand, two binary operators in a row, a leading `*`, `=` or `,`, `==`, `===`, `=<`, `&&&`, `?`, and `;`, `}` or `]` inside (e13 to e22, e27 to e38). `<>` is accepted. `-`, `!` and `~` are prefix operators. An id such as `*1A` is not accepted unquoted inside an expression (e46). | Implemented as observed (`syntax/empty-expression`, `expected-operand`, `unexpected-token`). |
| O-11 | GAP | Silent. | `$x - 1h` (a variable minus a time literal) fails to compile with "cannot arithmetically negate ip address", while `$x + 1w` and `$x - $w` compile (found writing fixtures). | Not modelled. |

## Arrays, commands, paths, files

| Id | Kind | Docs | Device evidence | Proposed default |
|---|---|---|---|---|
| A-01 | CONFLICT | Quote keys that are not lowercase. | `{A=1}`, `{a-b=1}`, `{a_b=1}` accepted (a6-a10); `{ a=1 }` as a statement and `{}` as an argument fail (a3, a21). | Hint only. Block-or-array decided by context. |
| C-01 | CONFLICT | Global commands must start with `:`. | `put`, `local`, `global`, `typeof`, `do {} on-error`, `if` work without it (p1-p12). | Accept; optional hint. |
| C-02 | GAP | Table of 49 global commands. | 9 more root commands; `break`/`continue` only inside loops (p19). | Use the device-generated database. |
| C-03 | INTERNAL | `:resolve` text says `server-port`, example `port=`. | `port=` fails, `server-port` works (p28, p29). | Docs erratum. |
| C-04 | GAP | An unnamed parameter must be given when the command requires it. | A parameter that is normally written unnamed can also be given by name: `:tonum value=10`, `set numbers=0` (p30, r24). The number of unnamed arguments a command takes differs per command and extra ones are an error (p24, r23, y12). | The command database records how many unnamed arguments each command takes. |
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
| P-05 | GAP | P-02 and the documentation do not say which lines change the path. | Only a line that is nothing but a path changes it; a full command does not (s1 to s5, s20). The change happens while the file is compiled, in source order. It carries on from the top level, a bare `{ }`, a statement-level `[ ]` and a path block such as `/ip { route }`, but not out of `do=`, `else=`, `on-error=`, a function body, `:execute`, `:retry` or an argument (l1 to l24). Those bodies and arguments start from the path in effect. | Track as observed. |
| P-06 | GAP | Silent. | A relative word is looked up only inside the current menu; there is no fall-back to the top level (s11, s12). Global commands need the colon inside a menu (`put` fails, `:put` works; s14 to s17), and `..` goes up, also glued to a word (`..add`, s19). | Track as observed. |
| C-14 | GAP | Silent. | In `/ip address remove [find]` the `find` runs in `/ip address`, the menu of the command it is an argument of (r18). | As observed. |
| S-01 | GAP | The documentation has no machine readable list of commands. | The command database is generated from a CHR with `/console/inspect`. A CHR has no wireless, LTE or switch-chip packages, and some parameters exist only on some hardware (`hw-offload` on filter rules, for example). | Unknown names are warnings by default. `tools/gen_schema.py` makes a database from your own router, and the `schema` setting points the server at it. |
| S-02 | GAP | Silent. | Which parameters are required and how many unnamed arguments a command takes are learned by compiling probe lines with `/import dry-run` (`missing value(s) of argument(s) ...`, `expected end of command`). Unnamed arguments are counted up to three. | Used by `schema/missing-required` and `schema/unexpected-argument`. |

## Documentation errata (no server decision needed)

`\f` value (E-01); `:resolve` example (C-03); `from= 1` versus the whitespace rule (L-09); "do not define globals in local scopes"
versus the later example; policy list omits `romon`, `winbox`, `api` that the defaults and example use; typos (`reslove`, `[code]`
markup, "specifues").

## Not probed

Interactive terminal behaviour (V-02), RouterOS versions other than 7.21.4, packages missing from a CHR (wireless, LTE), the
contextual variables of lease and hotspot scripts, the value types of parameters (RouterOS checks them only when a command runs, r4)
and the properties allowed in a `where` expression (C-13).
