/tool netwatch
add down-script=":log warning \"gateway down\"\r\
    \n/system script run notify-down" host=192.168.88.1 interval=30s \
    up-script=":log info \"gateway up\"\r\
    \n/system script run notify-up" timeout=2s
add host=1.1.1.1 interval=1m comment="wan probe" disabled=yes
