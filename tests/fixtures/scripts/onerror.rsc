:onerror e in={ /ip address add address=1.1.1.1/32 interface=nonexistent } do={ :log error $e }
:do { :error "boom" } on-error={ :put "caught" }
:onerror err in={ :retry command={ /tool fetch url=https://example.com/x.txt mode=https } delay=2s max=3 } do={ :log warning "fetch failed: $err" }
:local res [:do { :return 1 } on-error={ :return 0 }]
:execute script={ :log info "async" } file=job.txt
:global safe do={
  :do { /system identity get name } on-error={ :return "unknown" }
}
