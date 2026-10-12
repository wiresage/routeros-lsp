# Suite 5: remaining lexical/structural gaps.
NL = chr(10)
BS = chr(92)
PROBES = []

PROBES.append("INTERPOLATION INSIDE STRINGS (docs: $var, $[cmd], $(expr) inside a string; \\$ for a literal dollar)")
for pid, mode, snip, note in [
    ("x1", "run", ':put "n=$[:len "ab"]"' + NL, "nested double quotes inside $[ ] inside a string"),
    ("x2", "run", ':put "a$(1+2)b"' + NL, "$(expr) in a string"),
    ("x3", "run", ':put "$[:len "a"] $[:len "bb"]"' + NL, "two nested substitutions"),
    ("x4", "run", ':put "cost: ' + BS + '$5"' + NL, "escaped dollar"),
    ("x5", "run", ':local x 1; :put "$$x"' + NL, "double dollar"),
    ("x6", "run", ':put "$ x"' + NL, "dollar followed by space"),
    ("x7", "run", ':put "$1"' + NL, "dollar digit with no such variable"),
    ("x8", "run", ':local a {k=7}; :put "v=$($a->"k")"' + NL, "nested quotes inside $( )"),
    ("x9", "run", ':put "tab' + BS + 'there"' + NL, "backslash before an ordinary letter inside a string (device rejects unknown escapes?)"),
    ("x10", "run", ':put "a' + BS + NL + 'b"' + NL, "string join, again, for the exact result"),
]:
    PROBES.append((pid, mode, snip, note))

PROBES.append("$ FORMS OUTSIDE STRINGS")
for pid, mode, snip, note in [
    ("d1", "run", ":put $[:len ab]" + NL, "$[cmd] as an argument"),
    ("d2", "run", ":put $(1+2)" + NL, "$(expr) as an argument"),
    ("d3", "run", ":local a {k=7}; :put $a->k" + NL, "-> without parentheses"),
    ("d4", "run", ':local a {k=7}; :put ($a->"k")' + NL, "-> with parentheses"),
    ("d5", "run", ':local a {k={j=3}}; :put ($a->"k"->"j")' + NL, "chained ->"),
    ("d6", "run", ":local a {5;6;7}; :put ($a->1)" + NL, "numeric index"),
    ("d7", "run", ":local a {5;6;7}; :put ($a->9)" + NL, "index out of range"),
    ("d8", "run", ":local f do={ :return 5 }; :put [$f]" + NL, "call through [$f]"),
    ("d9", "run", ":local f do={ :put 5 }; $f" + NL, "call as a statement"),
    ("d10", "run", ":local f do={ :put 5 }; $f;" + NL, "call with semicolon"),
    ("d11", "run", ":local f do={ :put ($1 + $2) }; $f 3 4" + NL, "positional arguments"),
    ("d12", "check", "$1", "a call statement of a numeric name"),
]:
    PROBES.append((pid, mode, snip, note))

PROBES.append("CONTROL-FLOW LAYOUT PITFALLS")
for pid, snip, note in [
    ("k1", ":if (true) do={ :put 1 }" + NL + "else={ :put 2 }", "else on the next line"),
    ("k2", ":if (true) do={ :put 1 } " + BS + NL + "else={ :put 2 }", "else after a line join"),
    ("k3", ":if (true) do={" + NL + "  :put 1" + NL + "} else={" + NL + "  :put 2" + NL + "}", "the usual brace layout"),
    ("k4", ":if (true) do={ :put 1 }; else={ :put 2 }", "semicolon before else"),
    ("k5", ":foreach i in={1;2} do={" + NL + ":put $i" + NL + "}", "multi-line do block"),
    ("k6", ":if (true) " + NL + "do={ :put 1 }", "do= on the next line"),
    ("k7", ":do { :put 1 }" + NL + "while=(false)", "while= on the next line"),
    ("k8", ":for i from=1 to=3 do={" + NL + "}" + NL + ":put 1", "empty block followed by a command"),
    ("k9", "/ip address" + NL + "add address=1.1.1.1/32 " + BS + NL + "    interface=ether1", "export-style continuation"),
    ("k10", "/ip firewall filter add comment=" + BS + NL + '    "x y" chain=input', "backslash between = and the value (export style)"),
    ("k11", "/ip firewall filter add comment= " + BS + NL + '    "x" chain=input', "space, backslash, newline after ="),
]:
    PROBES.append((pid, "check", snip, note))

PROBES.append("STRINGS AND QUOTING IN COMMAND ARGUMENTS")
for pid, snip, note in [
    ("g1", '/system identity set name="a b"', "quoted value with a space"),
    ("g2", "/system identity set name=a b", "unquoted value with a space"),
    ("g3", '/system identity set name=a"b"', "quote in the middle of a bare word"),
    ("g4", '/system identity set name="a" "b"', "two strings"),
    ("g5", "/system identity set name='a'", "single quotes"),
    ("g6", '/system identity set name=""', "empty string"),
    ("g7", '/system identity set name="unterminated', "unterminated string"),
    ("g8", '/system identity set name="a' + BS + '"b"', "escaped quote inside a string"),
    ("g9", "/system identity set name=a,b", "comma in a bare value"),
    ("g10", "/system identity set name=a;b", "semicolon in a bare value ends the command"),
    ("g11", "/system identity set name=(1+2)", "expression value"),
    ("g12", "/system identity set name=[/system identity get name]", "substitution value"),
    ("g13", "/system identity set name=$x", "variable value"),
    ("g14", "/system identity set name=a$x", "dollar inside a bare word"),
    ("g15", "/system identity set name=a#b", "hash inside a bare value"),
    ("g16", "/system identity set name=a/b", "slash inside a bare value"),
    ("g17", "/system identity set name=a:b", "colon inside a bare value"),
    ("g18", "/system identity set name=a=b", "equals inside a bare value"),
    ("g19", "/system identity set name=a[b", "unbalanced bracket in a bare value"),
    ("g20", "/system identity set name=a}", "stray closing brace"),
    ("g21", "/system identity set name=a)", "stray closing paren"),
    ("g22", "}", "stray closing brace at statement start"),
    ("g23", "{", "unclosed block"),
    ("g24", ":put (", "unclosed paren"),
    ("g25", ":put [", "unclosed bracket"),
]:
    PROBES.append((pid, "check", snip, note))
