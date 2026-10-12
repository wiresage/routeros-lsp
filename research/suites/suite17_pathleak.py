# Suite 17: does a path change made inside a construct stay in effect after it?
# Each snippet changes the path to /ip route inside the construct and then runs `add dst-address=0.0.0.0/0 gateway=1.1.1.1`,
# which only /ip route accepts. OK means the change leaked out of the construct.
# Each entry: (id, mode, snippet, note)
NL = chr(10)
ADD = NL + "add dst-address=0.0.0.0/0 gateway=1.1.1.1"
PROBES = [
    "DOES THE PATH CHANGE LEAK OUT?",
    ("l1", "check", "{ /ip route }" + ADD, "bare block"),
    ("l2", "check", ":do { /ip route } on-error={ }" + ADD, ":do body"),
    ("l3", "check", ":foreach i in={1} do={ /ip route }" + ADD, ":foreach body"),
    ("l4", "check", ":while (false) do={ /ip route }" + ADD, ":while body"),
    ("l5", "check", ":if (true) do={ /ip route }" + ADD, ":if body"),
    ("l6", "check", ":if (true) do={ } else={ /ip route }" + ADD, "else body"),
    ("l7", "check", ":for i from=1 to=1 do={ /ip route }" + ADD, ":for body"),
    ("l8", "check", ":put [/ip route]" + ADD, "path-only command in a substitution"),
    ("l9", "check", "[/ip route]" + ADD, "substitution as a statement"),
    ("l10", "check", ":global f do={ /ip route }" + ADD, "function body"),
    ("l11", "check", ":local a { /ip route }" + ADD, "brace argument"),
    ("l12", "check", "/ip { route }" + ADD, "path block"),
    ("l13", "check", "/ip { route { } }" + ADD, "nested path block"),
    ("l14", "check", ":onerror e in={ /ip route } do={ }" + ADD, ":onerror in= body"),
    ("l15", "check", ":onerror e in={ } do={ /ip route }" + ADD, ":onerror do= body"),
    ("l16", "check", ":execute { /ip route }" + ADD, ":execute body"),
    ("l17", "check", ":retry command={ /ip route } delay=1 max=1" + ADD, ":retry body"),
    ("l18", "check", "/ip route" + NL + "{ /ip address }" + NL + "add address=1.1.1.1/32 interface=ether1", "leak back to a different path"),
    ("l19", "check", "/ip" + NL + "{ route }" + ADD, "relative path change inside a bare block"),
    ("l20", "check", "/ip { route; }" + ADD, "path block with a semicolon"),
    ("l21", "check", "/ip route { }" + ADD, "path block that is empty"),
    ("l22", "check", "{ /ip route; add dst-address=0.0.0.0/0 gateway=1.1.1.1 }", "add inside the block after the change"),
    ("l23", "check", ":if (true) do={ /ip route; add dst-address=0.0.0.0/0 gateway=1.1.1.1 }", "add inside if after the change"),
    ("l24", "check", "/ip route" + NL + ":if (true) do={ /ip address; add address=1.1.1.1/32 interface=ether1 }" + NL + "add dst-address=0.0.0.0/0 gateway=1.1.1.1", "path restored after if"),
]
