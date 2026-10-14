{
:local now [/system clock get time]
:local uptime [/system resource get uptime]
:if ($uptime > 1d) do={ :put "up more than a day" }
:local window 1h30m
:put ($window + 15m)
:put [:totime "00:10:00"]
:put [:timestamp]
:local t 2d3h4m5s
:put [:tostr $t]
:delay 500ms
:put (24h / 4)
:put ($uptime + 1w)
}
