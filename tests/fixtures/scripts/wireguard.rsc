/interface wireguard
add listen-port=13231 mtu=1420 name=wg0
/interface wireguard peers
add allowed-address=10.10.10.2/32 endpoint-address=203.0.113.10 endpoint-port=13231 \
    interface=wg0 name=peer1 public-key="Z2VuZXJhdGVkLXRlc3Qta2V5LW5vdC1yZWFsLWtleS0wMDE="
/ip address
add address=10.10.10.1/24 interface=wg0 network=10.10.10.0
/ip firewall filter
add action=accept chain=input comment="allow wireguard" dst-port=13231 protocol=udp
/ipv6 address
add address=2001:db8:10::1/64 advertise=no interface=wg0
/ipv6 firewall address-list
add address=2001:db8::/32 list=documentation
add address=::1/128 list=loopback
