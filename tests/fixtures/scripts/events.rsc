/system scheduler
add interval=1h name=hourly on-event="/system script run hourly-job" \
    policy=ftp,reboot,read,write,policy,test,password,sniff,sensitive,romon \
    start-date=jan/01/2026 start-time=00:00:00
add name=at-boot on-event=":delay 30s\r\
    \n/system script run boot-job" policy=read,write start-time=startup
/system script
add dont-require-permissions=no name=hourly-job owner=admin policy=\
    ftp,reboot,read,write,policy,test,password,sniff,sensitive,romon source=\
    ":log info \"hourly job\"\r\
    \n:local free [/system resource get free-hdd-space]\r\
    \n:if (\$free < 1000000) do={ :log warning \"disk low\" }"
add dont-require-permissions=no name=boot-job owner=admin policy=read,write source=":log info boot"
