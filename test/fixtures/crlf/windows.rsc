# Windows line endings with continuations
/ip dhcp-server network
add address=192.168.88.0/24 dns-server=192.168.88.1 gateway=192.168.88.1 \
    comment="default lan"
/ip pool
add name=dhcp ranges=192.168.88.10-192.168.88.254
:put "line one \
    continued"
:if (true) do={
  :put 1
} else={
  :put 2
}
