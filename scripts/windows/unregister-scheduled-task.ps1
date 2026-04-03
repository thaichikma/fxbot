#Requires -Version 5.1
#Requires -RunAsAdministrator
param(
    [string] $TaskName = "FXBot-MT5"
)

$ErrorActionPreference = "Stop"

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Đã gỡ task '$TaskName'."
