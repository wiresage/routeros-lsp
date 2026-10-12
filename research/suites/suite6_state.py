# Suite 6: menu-path state inside blocks, and abbreviations.
NL = chr(10)
PROBES = []

PROBES.append("PATH STATE AND BLOCKS (real import, read-only commands)")
for pid, snip, note in [
    ("b1", "/ip address" + NL + "{" + NL + "print count-only" + NL + "}" + NL, "relative command inside a block after a path line"),
    ("b2", "{" + NL + "/ip address" + NL + "print count-only" + NL + "}" + NL + "print count-only" + NL, "path set inside a block: does it leak after the block?"),
    ("b3", "/ip address" + NL + ":put [print count-only]" + NL, "relative command inside [] after a path line"),
    ("b4", "/ip address" + NL + ":foreach i in={1} do={ print count-only }" + NL, "relative command in a do={} block"),
    ("b5", "/ip route" + NL + "/ip address; print count-only" + NL, "absolute path replaces the current one"),
    ("b6", "/ip address" + NL + ".." + NL + "address print count-only" + NL, ".. goes up one level"),
    ("b7", "/ip address" + NL + "/" + NL + "ip address print count-only" + NL, "bare / returns to the root"),
    ("b8", "/ip address" + NL + ":global gp 1" + NL + "print count-only" + NL, "a global command between path line and command"),
]:
    PROBES.append((pid, "run", snip, note))

PROBES.append("ABBREVIATIONS (docs silent; the console accepts unambiguous prefixes)")
for pid, snip, note in [
    ("ab1", "/ip a print", "ambiguous menu prefix (address, arp, accounting...)"),
    ("ab2", "/ip ad pr", "unambiguous prefixes"),
    ("ab3", "/ip address add addr=1.1.1.1/32 inter=ether1", "abbreviated parameter names"),
    ("ab4", "/ip address add a=1.1.1.1/32 interface=ether1", "one-letter parameter prefix (address? arp?)"),
    ("ab5", "/ip address pri", "abbreviated command"),
    ("ab6", "/ip address p", "one-letter command prefix"),
    ("ab7", ":pu 1", "abbreviated global command"),
    ("ab8", ":lo x", "ambiguous global prefix (local, log, lock)"),
    ("ab9", "/ip address print det", "abbreviated flag"),
    ("ab10", "/ip address print cou", "abbreviated count-only"),
    ("ab11", "/ip addr add address=1.1.1.1/32 interface=ether1 comm=x", "abbreviated comment"),
]:
    PROBES.append((pid, "check", snip, note))
