{
:for i from=1 to=10 step=3 do={ :put $i }
:for i from=10 to=1 step=-2 do={ :put $i }
:local n 0
:while ($n < 5) do={
  :set n ($n + 1)
  :if ($n = 2) do={ :continue }
  :if ($n = 4) do={ :break }
  :put $n
}
:local tries 0
:do {
  :set tries ($tries + 1)
} while=($tries < 3)
:foreach i in=[/interface find where type=ether] do={
  :put [/interface get $i name]
}
:foreach i in={1; 2; 3} do={ :put ($i * $i) }
}
