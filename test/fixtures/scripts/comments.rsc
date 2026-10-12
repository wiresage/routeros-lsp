# top comment
:put 1; # comment after semicolon
:put 2 ;# no space before the hash
{
  # comment inside a block
  :put 3
  :put 4; # after statement in block
}
:if (true) do={
  # comment in do block
  :put 5
} else={
  :put 6
}
#### banner ####
# comment with "quotes" and $dollars and (parens [ { unbalanced
:put "string with # hash"
/system identity set name=abc#def
