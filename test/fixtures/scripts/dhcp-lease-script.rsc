# Runs as a DHCP lease script; the lease variables come from the server
:if ($leaseBound = 1) do={
  :local host [/ip dhcp-server lease get [find where active-address=$leaseActIP] host-name]
  :log info ("lease up: " . $leaseActMAC . " " . $leaseActIP . " " . $host)
  /ip firewall address-list add list=active-leases address=$leaseActIP timeout=1d comment=$leaseActMAC
} else={
  :log info ("lease down: " . $leaseActMAC)
  /ip firewall address-list remove [find where list=active-leases and comment=$leaseActMAC]
}
