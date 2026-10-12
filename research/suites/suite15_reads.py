# Suite 15: what a read of a variable returns across top-level commands and function boundaries.
# `run` mode really imports the snippet; every snippet only declares variables with an lspz prefix, prints, and removes them again.
# Each entry: (id, mode, snippet, note)
NL = chr(10)
CLEAN = ":global lspzg; :set lspzg; :global lspzf; :set lspzf; :global lspzh; :set lspzh; :global lspzg3; :set lspzg3; :global lspzf2; :set lspzf2; :global lspzf3; :set lspzf3"
PROBES = [
    "READS ACROSS TOP-LEVEL COMMANDS (output shows the value, or nothing after the =)",
    ("q1", "run", ":local lspzl 3" + NL + ":put (\"local-next-line=\" . [:tostr $lspzl])", "local declared on an earlier top-level command"),
    ("q2", "run", ":global lspzh 4" + NL + ":put (\"global-next-line=\" . [:tostr $lspzh])" + NL + CLEAN, "global declared on an earlier top-level command, no redeclaration"),
    ("q3", "run", ":global lspzg 5" + NL + ":global lspzf do={ :put (\"global-in-function=\" . [:tostr $lspzg]) }" + NL + "$lspzf" + NL + CLEAN, "global read inside a function without redeclaring"),
    ("q4", "run", ":global lspzg3 6" + NL + ":global lspzf3 do={ :global lspzg3; :put (\"global-redeclared=\" . [:tostr $lspzg3]) }" + NL + "$lspzf3" + NL + CLEAN, "global redeclared inside the function"),
    ("q5", "run", "{ :local lspza 7; :global lspzf2 do={ :put (\"outer-local-in-function=\" . [:tostr $lspza]) }; $lspzf2 }" + NL + CLEAN, "outer local read inside a function"),
    ("q6", "run", "{ :local lspzb 8; :if (true) do={ :put (\"outer-local-in-if=\" . [:tostr $lspzb]) } }", "outer local read inside do= of :if"),
    ("q7", "run", ":global lspzg 9; :global lspzf do={ :put (\"arg=\" . [:tostr $a]) }; $lspzf a=1" + NL + CLEAN, "named function argument"),
    ("q8", "run", ":global lspzf do={ :put (\"positional=\" . [:tostr $1]) }; $lspzf 2" + NL + CLEAN, "positional function argument"),
    ("q9", "run", "{ :local lspzc 1; { :local lspzc 2 }; :put (\"shadow=\" . [:tostr $lspzc]) }", "inner declaration of the same name ended"),
    ("q10", "run", ":put (\"undeclared=\" . [:tostr $lspzneverdeclared])", "never declared"),
    ("q11", "run", ":global lspzg 10" + NL + ":global lspzg" + NL + ":put (\"global-redeclared-empty=\" . [:tostr $lspzg])" + NL + CLEAN, "global redeclared without a value keeps the value"),
    ("q12", "run", ":foreach lspzi in={1;2} do={ :put (\"loop=\" . [:tostr $lspzi]) }" + NL + ":put (\"loop-after=\" . [:tostr $lspzi])", "loop variable after the loop"),
    ("q13", "run", ":for lspzj from=1 to=2 do={ :local lspzk $lspzj }" + NL + ":put (\"for-after=\" . [:tostr $lspzj])", "for variable after the loop"),
]
