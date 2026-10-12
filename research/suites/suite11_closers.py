# Suite 11: is whitespace required after a closing bracket?
# Each entry: (id, mode, snippet, note)
PROBES = [
    "NO SPACE AFTER A CLOSING BRACKET",
    ("k20", "check", ":if (true) do={:put 1}else={:put 2}", "}else= with no space"),
    ("k21", "check", ":if (true)do={:put 1}", ")do= with no space"),
    ("k22", "check", ":foreach i in={1;2}do={:put $i}", "}do= with no space"),
    ("k23", "check", ":put [:len \"a\"]", "baseline substitution"),
    ("k24", "check", ":if ([:len \"a\"]>0)do={}", "]) then do="),
    ("k25", "check", ":do {:put 1}while=(false)", "}while= with no space"),
    ("k26", "check", ":do {:put 1}on-error={}", "}on-error= with no space"),
    ("k27", "check", ":put (1)", "baseline group"),
    ("k28", "check", ":local a {1;2}; :put ($a)", "baseline"),
    ("k29", "check", "/ip address {print}", "path block with no spaces inside"),
    ("k30", "check", ":if (true) do={:put 1}  else={:put 2}", "two spaces before else"),
    ("k31", "check", ":foreach i in=[:toarray \"1,2\"]do={:put $i}", "]do= with no space"),
    ("k32", "check", ":if (true) do={:put 1} else={:put 2}:put 3", "command glued after the else block"),
]
