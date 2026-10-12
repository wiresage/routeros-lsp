# 2026-10-12 20:02:00 by RouterOS 7.21.4
# system id = redacted
#
/interface ethernet
set [ find default-name=ether1 ] disable-running-check=no
set [ find default-name=ether2 ] disable-running-check=no name=ether34
/interface vlan
add comment="VoIP VLAN" interface=ether1 name=vlan40-voip vlan-id=40
/ip address
add address=10.40.0.1/24 comment="VoIP gateway" interface=vlan40-voip \
    network=10.40.0.0
/ip dhcp-client
add interface=ether1
/ip firewall filter
add action=drop chain=forward comment=\
    "Block 203.0.113.0/24 (added via safe mode)" src-address=203.0.113.0/24
/system identity
set name=RouterA-NL
