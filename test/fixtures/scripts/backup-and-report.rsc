# Nightly backup and e-mail report
:global reportRecipient "ops@example.com"
:global backupPrefix "nightly"

:local sysName [/system identity get name]
:local stamp ([/system clock get date] . "-" . [/system clock get time])
:local fileName ($backupPrefix . "-" . $sysName)

:do {
  /system backup save name=$fileName
  /export compact file=$fileName
  :log info "backup written: $fileName"
} on-error={
  :log error ("backup failed for " . $sysName)
}

:local free [/system resource get free-memory]
:local total [/system resource get total-memory]
:local pct (($total - $free) * 100 / $total)

:if ($pct > 90) do={
  :log warning "memory usage is $pct%"
} else={
  :log info "memory usage is $pct%"
}

/tool e-mail send to=$reportRecipient subject="Backup $sysName" \
    body="Backup $fileName finished at $stamp. Memory used: $pct%"
