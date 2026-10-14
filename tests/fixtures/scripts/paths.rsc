/ip address
add address=192.168.1.1/24 interface=ether1 comment="mgmt"
print
/ip route
add dst-address=0.0.0.0/0 gateway=192.168.1.254
..
/ip firewall filter
add chain=input action=accept protocol=icmp
/ip/dns/set servers=1.1.1.1,9.9.9.9 allow-remote-requests=yes
/system/identity/set name=lab
/ip firewall { filter print; nat print }
/ip { address print; route print }
/interface print where name~"^ether[0-9]+\$"
/
/system clock print
