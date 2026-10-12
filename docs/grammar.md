# RouterOS script grammar, derived from the documentation

Source of truth: <https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting>
(read completely on 2026-10-11; 41,782 characters of text, 1,280 lines after conversion).
Nothing below is copied from the page; it is a derived summary with section references.

How to read the tags. Every rule carries one:

| Tag | Meaning |
|---|---|
| **[D]** | Stated in the documentation. |
| **[X]** | Not stated, but shown by a documentation example. |
| **[V]** | Not in the documentation. Observed on RouterOS 7.21.4 by the conformance probes (`research/`). |
| **[?]** | Open: the documentation is silent or contradicts itself, or the device disagrees with it. See [ambiguities.md](ambiguities.md), the id in brackets. |

Rules tagged **[V]** and **[?]** are not part of the specified language. The server must not
silently promote them to "the grammar".

## 1. Files and physical lines

- A script is a sequence of command lines, run one by one until the end or a runtime error. [D] *Line structure*
- A physical line ends with LF, CR LF or CR. [D] *Physical Line*
- `.rsc` is the extension `export` writes and `import` reads; files may be written by hand. [D] *import*
- Encoding, byte order mark, maximum line length: not stated. [?] P-03, L-06, L-07

## 2. Lexical structure

### 2.1 Comments
- A comment starts with `#` and ends at the end of the physical line. [D]
- There are no multi-line comments. [D]
- A `#` inside a string is not a comment. [D]
- Documented example places a comment after `;`. [X] `#` is read as a comment only at the start of a command: after `;`, a line break,
  `{` or `[`, and at the start of a line that follows a backslash join. Anywhere else it is an ordinary character, so a comment
  after arguments turns into extra arguments and the line fails. [V] L-01, L-18
- A `#` inside an unquoted word or value (`a#b`) is part of the word. [V] L-02

### 2.2 Line joining
- A backslash at the end of a physical line joins it to the next one. [D]
- A joined line cannot carry a comment; a backslash does not continue a comment. [D]
- A backslash does not continue a token except inside a string literal. [D]
- A backslash is illegal elsewhere outside a string. [D] (the device accepts some of these, L-03)
- Inside a string the backslash and the newline are removed together with the leading
  whitespace of the next line. [V] L-04

### 2.3 Whitespace
- Whitespace separates tokens and is required only where concatenation would read as a different token. [D]
  The documentation never lists the tokens, so the exact rule is open. [?] L-10
  Observed: two values written with nothing between them are an error outside `( )`, also after a closing bracket (`}else=`). [V] L-19
- No whitespace between `<parameter>` and `=`, and between `from= to= step= in= do= else=` and their `=`. [D]
  Whitespace after the `=` is accepted (the documentation's own "correct" example has it). [X] L-09

### 2.4 Delimiters and keywords
- Delimiters: `( ) [ ] { } : ; $ /`. [D]
- Keywords, not usable as variable or function names: `and`, `or`, `in`. [D] The device accepts them as names. [?] V-08

### 2.5 Statement terminators
- A command line ends at `;` or NEWLINE. [D]
- A single command inside `()`, `[]` or `{}` needs no terminator. [D]
- Two commands on one line need a separator. [V] L-11
- A line break inside `( )` is an error; inside `[ ]` and `{ }` it separates commands. [V] L-17

### 2.6 Strings
- Double-quoted. Escape sequences: `\"` `\\` `\n` `\r` `\t` `\$` `\_` (space) `\a` `\b` `\f` `\v`, and `\` plus two
  hexadecimal digits written with capital letters. [D] *Constant Escape Sequences*
- `\?` is documented as removed since v7.1rc2. [D] The device still accepts it. [?] E-02
- `\f` is documented as 0xFF. [D] The device produces 0x0C. [?] E-01
- Anything else after a backslash is a syntax error; lowercase hex and single-digit hex are errors. [V] E-03, E-04
- `$name`, `$(expression)` and `$[command]` inside a string are substituted; `\$` gives a literal dollar. [D] *Concatenation Operators*
  The nested expression or command can contain its own double-quoted strings. [V]
- A raw newline inside a string is accepted. [V] L-05
- Single quotes are not string delimiters. [V] L-15
- A `$` in a string must be followed by a name, `(` or `[`; a regular expression anchor needs `\$`. [V] L-23

### 2.7 Numbers, times, addresses and other literals
The documentation lists the types (`num`, `bool`, `str`, `ip`, `ip-prefix`, `ip6`, `ip6-prefix`, `id`, `time`,
`array`, `nil`) and says only that `num` is a 64-bit signed integer with possible hexadecimal input,
and that `id` is a hexadecimal value prefixed with `*`. The spelling of every other literal is not
specified. [?] T-01. Observed spellings [V]: `0xFF`, `*1A`, `10s`, `1d2h3m`, `00:10:00`, `1.1.1.1`,
`1.1.1.1/32`, `::1`, `2001:db8::/32`, `true`, `false`, `yes`, `no`.

### 2.8 Identifiers and variable names
- Letters and digits. Any other character requires double quotes around the name. [D] *Variables*
- Case-sensitive. [D]
- `$"my-var"` refers to a quoted name. [D]
- In practice: ASCII letters and digits only, may start with a digit, `_` and `-` need quotes. [V] V-07, V-18

## 3. Operators

| Group | Operators | Source |
|---|---|---|
| Arithmetic | `+ - * / %` and unary `-` | [D] |
| Relational | `< > = <= >= !=` | [D] |
| Logical | `!`, `&&` / `and`, `\|\|` / `or`, `in` | [D] |
| Bitwise | `~ \| ^ & << >>` | [D] documented "only on IP and IPv6 address types" (works on integers too, O-03) |
| Concatenation | `.` for strings, `,` for arrays | [D] |
| Other | `[]` command substitution, `()` grouping, `$` substitution, `~` regular-expression match, `->` array element | [D] |

- Precedence and associativity are not specified. [?] O-01
- For division the dividend must be in parentheses or surrounded by spaces so it is not read as an IP address. [D]
- Bare names inside `( )` act as variable references (`(-a)`, `(a&&b)` in the documentation's examples). [X] O-07
- Inside `( )` operands may stand next to each other; an empty group, a missing operand and two binary operators are errors. [V] O-10

## 4. Command lines

```
[prefix] [path] command [uparam] [param=[value]] .. [param=[value]]
```
(documentation notation) [D] *Command-line*

- `prefix` is `:` (a global command) or `/` (a menu path); it "may not be required". [D] When it is not required is not defined. [?] C-01
- A command line inside another starts and ends with `[` `]`. [D] It "can contain only a single command line". [D] (the device accepts several, L-12)
- Named parameters are `name=value`. Some parameters are bare flags with no value (`count-only`, `dry-run`). [X]
- `!name` unsets a parameter (`set 0 !port`). [D] Support depends on the menu. [?] C-08
- An unnamed parameter must be given when the command requires it. [D] A parameter that is normally unnamed can also be given by name (`value=`). [V] C-04
- A menu path can use spaces or slashes (`/ip route get`, `/interface/print`, `system/script/run`). [X] They are equivalent. [V] P-01
- The current menu path set by one line applies to following lines, also inside blocks. [V] P-02 (documentation lists `/` and `..` but never says this)
- Names can be abbreviated to any unambiguous prefix. [V] C-10
- A command line cannot start with a string, `=`, `!`, `,`, `~` or `*`, and command and menu words are lowercase. [V] L-22
- Which lines change the current menu path, and where the change carries on, is described in section 4.4. [V] P-05, P-06

### 4.1 Global commands
Every global command "should start with `:`", otherwise it is treated as a variable. [D] The device accepts several without the colon. [?] C-01
The documentation's table lists 49; the device has 9 more root commands. [?] C-02

Documented commands and their informal syntax: `:global`, `:local`, `:set`, `:beep`, `:break`, `:continue`, `:convert`, `:delay`,
`:environment`, `:error`, `:execute`, `:exit`, `:find`, `:grep`, `:jobname`, `:len`, `:log`, `:onerror`, `:parse`, `:pick`,
`:put`, `:range`, `:resolve`, `:retry`, `:typeof`, `:rndnum`, `:rndstr`, `:serialize`, `:deserialize`, `:time`,
`:timestamp`, `:toarray`, `:tobool`, `:toid`, `:toip`, `:toip6`, `:tonum`, `:tostr`, `:totime`, `:tonsec`, `:tocrlf`, `:tolf`,
`:nothing`, plus `:return` (described under Functions) and the loop and conditional commands below.
The notation (`<x>`, `[x]`, `[num]`, `[arg]`) is informal and carries no machine-readable types. [?] C-07

### 4.2 Control flow
| Form | Source |
|---|---|
| `:if (<condition>) do={...} else={...}` | [D] |
| `:do { ... } while=( <condition> )` and `:while ( <condition> ) do={ ... }` | [D] |
| `:for <var> from=<int> to=<int> step=<int> do={ ... }` | [D] |
| `:foreach <var> in=<array> do={ ... }`, also `:foreach k,v in=...` | [D] |
| `:onerror <var> in={...} do={...}`; the `in=` word is omitted in the documentation's own example | [D][X] |
| `:retry command=<expr> delay=<num> max=<num>` inside `:onerror` | [D] |
| `do { ... } on-error={ ... }` for `import` | [D] |

`else=` must follow on the same logical line. [V] C-12

### 4.3 Menu commands
`add`, `remove`, `enable`, `disable`, `set`, `get`, `print`, `export`, `edit`, `find`. [D] The documented `print` parameters
are a closed list of "the most common" ones. [D] The grammar of the `where` expression is not specified. [?] C-13

### 4.4 Menu path state

- A line that is nothing but a path (`/ip address`, `address`, `..`, `/`) changes the current path. A full command (`/ip address print`) does not. [V] P-05
- The path is resolved while the file is compiled, in source order. It carries on from the top level, a bare `{ }`, a statement-level
  `[ ]` and a path block (`/ip { route }`). The bodies of `:if`, `:do`, `:while`, `:for`, `:foreach`, `:onerror`, `:retry`,
  `:execute` and functions, and every command argument, start from the path in effect but do not change it. [V] P-05
- A relative word is looked up only in the current menu. Inside a menu a global command needs the colon (`:put`). [V] P-06
- A command substitution that is an argument runs in the menu of the command it belongs to: `/ip address remove [find]`. [V] C-14

## 5. Variables and scopes

- Two kinds: `global` (accessible from all scripts of the current user) and `local` (the current scope). [D]
- A variable declared in a block is visible in that block and the blocks inside it, after the declaration. [D]
- A `:global` declared in an inner block is not visible outside it unless the outer scope declares it again with `:global name`. [D]
- "Every variable ... must be declared before usage ... Undeclared variables ... result in a compilation error." [D]
  On the device only `:set` of an undeclared name is an error; reading one gives nothing. [?] V-01
- `:set name` with no value removes the variable. [D]
- Each line written in the terminal is its own local scope. [D] For an imported file the same holds for each line: commands separated
  by `;` on one line share a scope. [V] V-03, V-16
- `:set name` needs `name` declared earlier in the same or an enclosing block (`:local`, `:global`, the variable of `:for`, `:foreach`
  or `:onerror`). A function body sees none of the declarations around it. Quoted names and array elements are not checked. [V] V-15
- Reading a variable that does not exist gives an empty value. A global is found by name from anywhere; an outer local is not visible
  inside a function body. [V] V-17
- Built-in properties are reserved variable names. [D] They cannot be enumerated from this page. [?] V-10
- Variables set by the environment (DHCP lease scripts, hotspot on-login) are exempt. [D] Their names are not listed. [?] V-14

### 5.1 Functions
- `:global f do={ ... }` defines a function; `$f a=1 "x"` or `[$f a=1]` calls it. [D]
- Arguments arrive as `$a` (named) or `$1`, `$2`, ... (unnamed). [D] The "declared before use" rule is not applied to them. [X] V-05
- `:return` gives a value. [D]
- A function that calls another function must declare that name with `:global`. [D]
- `:parse` turns a string into a function. [D]

## 6. Arrays

- `{1;2;3}`, `{a=1;b=2}`, `(1,2)`; element access `$a->"key"` or `$a->0`; `:set ($a->"x") 5`. [D][X]
- Keys that contain anything other than lowercase letters must be quoted. [D] The device accepts unquoted keys with capitals, hyphens
  and underscores. [?] A-01
- `{ ... }` is also the block and scope delimiter. The rule that tells the two apart is not given. [?] A-01

## 7. A working EBNF

This is a formalisation of the documented rules only. Productions marked `(* V *)` or `(* ? *)` are listed so the parser can
carry them as explicit, switchable behaviour instead of burying them in code.

```ebnf
script        = { separator | statement } ;
separator     = ";" | newline ;
statement     = comment | command-line ;
comment       = "#" { any-char-except-eol } eol ;          (* only where a statement can start: V, L-01 *)

command-line  = [ prefix ] [ path ] command { argument } ;
prefix        = ":" | "/" ;                                  (* optional colon: ?, C-01 *)
path          = word { ( "/" | space ) word } ;              (* equivalence of "/" and space: V, P-01 *)
command       = word ;
argument      = flag | named | unnamed | unset ;
flag          = word ;                                       (* bare flag such as count-only *)
named         = word "=" [ space ] value ;                   (* no space before "=": D *)
unset         = "!" word ;
unnamed       = value ;

value         = string | literal | variable | subst | group | brace | expr-paren ;
string        = '"' { char | escape | interp } '"' ;
escape        = "\" ( '"' | "\" | "n" | "r" | "t" | "$" | "_" | "a" | "b" | "f" | "v" | hex hex ) ;
interp        = "$" name | "$(" expr ")" | "$[" command-line "]" ;
variable      = "$" ( name | string ) ;
subst         = "[" command-line "]" ;
group         = "(" expr ")" ;
brace         = "{" { separator | statement | pair | value } "}" ;   (* block or array: ?, A-01 *)
pair          = ( word | string ) "=" value ;

expr          = unary { binary-op unary } ;                  (* precedence: ?, O-01 *)
unary         = [ "!" | "-" | "~" ] primary ;
primary       = value | name ;                               (* bare name = variable inside "(": X, O-07 *)
binary-op     = "+" | "-" | "*" | "/" | "%" | "<" | ">" | "=" | "<=" | ">=" | "!="
              | "&&" | "and" | "||" | "or" | "in" | "&" | "|" | "^" | "<<" | ">>"
              | "." | "," | "~" | "->" ;

name          = letter-or-digit { letter-or-digit } ;
word          = ( letter-or-digit | "-" | "." | ... ) { ... } ;   (* the character set of a bare word is not documented: V, L-16 *)
```

## 8. Not covered by the documentation page

These are needed for the features asked for and have to come from elsewhere:

1. The set of menus, commands, parameters, value types and enumerations (for "unknown command or parameter" and completion).
2. The spelling of every literal type.
3. The contextual variables of lease scripts, hotspot scripts and similar.
4. The `where` expression language.

Item 1 is available from the device itself (`/console/inspect`); see [proposal.md](proposal.md).
