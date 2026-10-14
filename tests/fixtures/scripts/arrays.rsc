{
:local colors {"red"; "green"; "blue"}
:local ports {http=80; https=443; "ssh-alt"=2222}
:local nested {name="lan"; members={"ether2"; "ether3"}; mtu=1500}

:foreach c in=$colors do={ :put $c }
:foreach k,v in=$ports do={ :put ($k . "=" . $v) }

:put ($ports->"https")
:put ($nested->"members"->0)
:set ($ports->"http") 8080
:set ($nested->"mtu") (($nested->"mtu") + 8)

:local count [:len $colors]
:for i from=0 to=($count - 1) do={
  :put ("color " . $i . ": " . ($colors->$i))
}

:local csv [:toarray "a,b,c"]
:local joined ""
:foreach item in=$csv do={ :set joined ($joined . $item . ";") }
:put $joined
:if ([:typeof $nested] = "array") do={ :put "array" }
:put [:pick $colors 1]
:put [:find $colors "blue"]
}
