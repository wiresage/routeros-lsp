# Suite 3: literals, escape sequences, operators. All pure expressions (nothing touches configuration).
NL = chr(10)
BS = chr(92)
PROBES = []

PROBES.append("LITERAL TYPES: :put [:typeof <literal>] (docs list the types but not how to write them)")
LITS = [
    ("0xFF", "hex number"), ("0XFF", "hex, capital X"), ("0xff", "hex lowercase"), ("-5", "negative"), ("1.5", "decimal"),
    ("1e3", "exponent"), ("1_000", "underscore"), ("0b101", "binary"), ("0o7", "octal"), ("007", "leading zeros"),
    ("9223372036854775807", "int64 max"), ("9223372036854775808", "int64 max + 1"),
    ("10s", "time: seconds"), ("1d2h3m", "time: d h m"), ("00:10:00", "time: clock form"), ("1w", "time: week"),
    ("2735w21:41:43", "time: docs :timestamp output"), ("1h30", "time: odd mix"), ("100ms", "time: ms"),
    ("*1A", "internal id"), ("*g", "internal id, bad digit"), ("*", "lone star"),
    ("1.1.1.1", "ip"), ("1.1.1.1/32", "ip-prefix"), ("1.1.1.0/24", "ip-prefix"), ("256.1.1.1", "bad ip"), ("1.1.1", "three octets"),
    ("1.1.1.1.1", "five octets"), ("::1", "ip6"), ("2001:db8::/32", "ip6-prefix"), ("fe80::1", "ip6 link-local"),
    ("true", "bool"), ("false", "bool"), ("yes", "yes"), ("no", "no"), ("nil", "nil"), ("TRUE", "bool capitals"),
    ('"x"', "string"), ("abc", "bare word"), ("a.b", "bare word with dot"), ("a-b", "bare word with hyphen"), ("abc123", "bare word"),
    ("{1;2}", "array"), ("{a=1}", "keyed array"), ("(1,2)", "comma list in parens"), ("{}", "empty array"), ("()", "empty parens"),
]
for i, (lit, note) in enumerate(LITS):
    PROBES.append(("L%d" % i, "eval", ":put [:typeof %s]" % lit, note))

PROBES.append("LITERAL VALUES where the form is ambiguous: :put (<literal>)")
for i, (lit, note) in enumerate([("0xFF", ""), ("1e3", ""), ("007", ""), ("1d2h3m", ""), ("00:10:00", ""), ("10/2", "docs: 'mistaken as an IP address'"),
                                  ("(10)/2", "docs fix"), ("10 / 2", "docs fix"), ("(10 / 2)", ""), ("(10/2)", ""), ("1.1.1.1/32", ""), ("1.1.1.1 / 32", ""),
                                  ("(1.1.1.1)/32", ""), ("3/2", ""), ("3/2/1", "")]):
    PROBES.append(("V%d" % i, "eval", ":put (%s)" % lit, note))

PROBES.append("ESCAPE SEQUENCES: :put [:convert \"<esc>\" to=hex]  (docs: \\\" \\\\ \\n \\r \\t \\$ \\? \\_ \\a \\b \\f \\v and \\xx two hex digits, capitals)")
ESC = [BS + '"', BS + BS, BS + "n", BS + "r", BS + "t", BS + "$", BS + "?", BS + "_", BS + "a", BS + "b", BS + "f", BS + "v",
       BS + "48", BS + "4F", BS + "4f", BS + "4", BS + "FF", BS + "00", BS + "x41", BS + "q", BS + "e", BS + "0", BS + "u0041", BS + "'", BS + "/", BS + "#"]
for i, e in enumerate(ESC):
    PROBES.append(("E%d" % i, "eval", ':put [:convert "%s" to=hex]' % e, "escape " + e))

PROBES.append("ARITHMETIC AND PRECEDENCE (docs: operators listed, NO precedence or associativity stated)")
EXPR = [
    ("(1+2*3)", "+ vs *"), ("(2*3+1)", "* then +"), ("(10-2-3)", "left assoc?"), ("(100/10/5)", "division assoc"), ("(2*3%4)", "* %"), ("(7%4*2)", "% *"),
    ("(-2*3)", "unary minus"), ("(1+-1)", "binary then unary"), ("(1 - -1)", ""), ("(5 % 3)", "modulo"), ("(10 / 4)", "int division"), ("(7 / 2)", ""), ("(-7 / 2)", ""),
    ("(2-1-1)", ""), ("(1+2+3*4)", ""), ("(8/4/2)", ""),
]
for i, (x, note) in enumerate(EXPR):
    PROBES.append(("A%d" % i, "eval", ":put " + x, note))

PROBES.append("LOGICAL AND RELATIONAL")
EXPR = [
    ("(true||false&&false)", "|| vs &&"), ("(false&&false||true)", "&& vs ||"), ("(true&&false||true)", ""), ("(!true=false)", "! vs ="), ("(!false&&false)", ""),
    ("(true and false or true)", "word forms"), ("(true or false and false)", ""), ("(!true)", ""), ("(! true)", "space after !"), ("(not true)", "not as a word"),
    ("(1<2=true)", "relational vs ="), ("(3>2>1)", "chained"), ("(1=1=1)", "chained ="), ("(1<2<3)", ""), ("(1!=2)", ""), ("(1<=1)", ""), ('("a"<"b")', "string compare"),
    ('("10"<"9")', "string vs number compare"), ("(10<9)", ""), ("(1=1&&2=2)", "= vs &&"), ("(1=2||2=2)", ""), ("(1+2=3)", "+ vs ="), ("(1<2&&3<4)", ""),
]
for i, (x, note) in enumerate(EXPR):
    PROBES.append(("R%d" % i, "eval", ":put " + x, note))

PROBES.append("CONCATENATION, ARRAYS, REGEX, BITWISE, IN")
EXPR = [
    ('("a"."b"."c")', "string concat"), ('(1."a")', "number then string"), ("(1 . 2)", "numbers"), ("({1;2},3)", "array , element"), ("(1,2)", ""), ("(1,2,3)", ""),
    ('(1+2 . "x")', ". vs +"), ('("a" . 1 = "a1")', ". vs ="), ('("a" . "b" = "ab")', ""), ('("abc"~"b")', "regex match"), ('("abc"~"^b")', ""), ('("abc"~"B")', "case"),
    ("(~0.0.0.0)", "inversion"), ("(192.168.88.77&255.255.255.0)", "AND"), ("(1&3)", "AND on ints (docs: IP only)"), ("(1|2)", "OR on ints"), ("(1^3)", "XOR on ints"),
    ("(1<<2)", "shift on ints"), ("(~1)", "invert int"), ("(192.168.88.77<<8)", "docs example"), ("(192.168.88.77>>24)", "docs example"),
    ("(1.1.1.1/32 in 1.0.0.0/8)", "docs example"), ("(1.1.1.1 in 1.0.0.0/8)", "address in prefix"), ("(2 in {1;2})", "in with array?"),
    ("(192.168.88.0|0.0.0.255)", "docs example"), ("(1.1.1.1^255.255.0.0)", "docs example"),
]
for i, (x, note) in enumerate(EXPR):
    PROBES.append(("O%d" % i, "eval", ":put " + x, note))

PROBES.append("UNARY MINUS ON A VARIABLE, BARE IDENTIFIERS IN EXPRESSIONS (docs examples use them without $)")
EXPR = [
    ("{ :local a 1; :put (-a) }", "docs: unary negation example, bare a"), ("{ :local a 1; :put (-$a) }", "with $"),
    ("{ :local a true; :local b false; :put (a&&b) }", "docs example, bare a and b"), ("{ :local a true; :local b false; :put ($a&&$b) }", "with $"),
    ("{ :local a true; :local b false; :put (a and b) }", "docs example, word and"), ("{ :local a 1; :put (a+1) }", "bare name in arithmetic"),
    ('{ :put (abc . "d") }', "bare word concatenated"), ("{ :put (abc = abc) }", "bare words compared"),
    ("{ :local a 1; :put (a) }", "bare name alone"), ("{ :local a 1; :put ($a+$a) }", ""), ("{ :local a 1; :put ($a +$a) }", "space before only"),
    ("{ :local a 1; :put ($a+ $a) }", "space after only"), ("{ :local a 5; :put ($a-1) }", "minus after name"), ("{ :local a 5; :put ($a -1) }", "space then -1"),
]
for i, (x, note) in enumerate(EXPR):
    PROBES.append(("B%d" % i, "eval", ":put " + x if not x.startswith("{") else x, note))
