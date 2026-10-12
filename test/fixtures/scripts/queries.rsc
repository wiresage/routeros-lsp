/ip firewall connection print count-only where protocol=tcp and dst-port=443
/ip address print where interface=ether1 and !disabled
/ip address print where address~"^192\\.168"
/interface print where type=ether or type=vlan
/ip route print where dst-address=0.0.0.0/0 && gateway~"192"
:local ids [/ip address find where interface=ether1]
/ip address set $ids comment="updated"
/ip address remove [find where comment~"temp" and dynamic=no]
/ip dhcp-server lease print where active-address in 192.168.88.0/24
:put [/ip address print as-value where interface=ether1]
:put [/interface print count-only where running]
