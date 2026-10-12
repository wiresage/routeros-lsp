:local name "ether1"
:local n 5
:put "plain"
:put "interface $name has index $n"
:put "sum is $(2 + 3) and name is $[/system identity get name]"
:put "escaped dollar \$name and quote \" and backslash \\"
:put "tab\tseparated\tvalues\r\nnext line"
:put "hex \41\42\43 and underscore\_space"
:put "bell \a backspace \b formfeed \f vertical \v"
:put ("concat " . $name . " " . $n)
:local "my var" 7
:put $"my var"
:put "line one \
    continued"
:put [:pick "abcdef" 1 4]
:put [:find "abcdef" "cd"]
:put [:tostr 255]
:put [:tonum "42"]
:put [:len "häagen"]
