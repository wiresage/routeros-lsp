:global greet do={
  :local who $1
  :if ([:typeof $who] = "nothing") do={ :set who "world" }
  :return ("hello " . $who)
}

:global add do={ :return ($a + $b) }
:global fact do={
  :global fact
  :if ($1 <= 1) do={ :return 1 }
  :return ($1 * [$fact ($1 - 1)])
}

:put [$greet "router"]
:put [$greet]
:put [$add a=2 b=3]
:put [$fact 5]

{
  :local compiled [:parse ":put \"parsed\""]
  $compiled
}

:global withDefault do={
  :local level "info"
  :if (!any $level) do={ :set level "info" }
  :log info $1
}
$withDefault "from function"
