# Basic input/forward firewall, written the way exports are
/ip firewall address-list
add address=192.168.88.0/24 list=lan
add address=10.0.0.0/8 comment="rfc1918 a" list=bogons
add address=172.16.0.0/12 comment="rfc1918 b" list=bogons
/ip firewall filter
add action=accept chain=input comment="accept established,related,untracked" \
    connection-state=established,related,untracked
add action=drop chain=input comment="drop invalid" connection-state=invalid
add action=accept chain=input comment="accept ICMP" protocol=icmp
add action=accept chain=input comment="accept from lan" in-interface-list=LAN
add action=drop chain=input comment="drop all not from lan" \
    in-interface-list=!LAN
add action=fasttrack-connection chain=forward connection-state=established,related
add action=drop chain=forward comment="drop invalid" connection-state=invalid
add action=drop chain=forward comment="drop from bogons" src-address-list=bogons \
    in-interface-list=WAN
/ip firewall nat
add action=masquerade chain=srcnat comment="masquerade" out-interface-list=WAN
