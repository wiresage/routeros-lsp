# 2026-10-12 20:02:11 by RouterOS 7.21.4
# system id = redacted
#
/interface ethernet set [ find default-name=ether1 ] disable-running-check=no
/interface ethernet set [ find default-name=ether2 ] disable-running-check=no name=ether34
/ip dhcp-client add interface=ether1
/system identity set name=RouterB-DE
