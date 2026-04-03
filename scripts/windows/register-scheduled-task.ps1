#Requires -Version 5.1
#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Đăng ký Scheduled Task chạy FXBot khi user đăng nhập Windows.
.NOTES
  MT5 thường cần desktop session — trigger AtLogOn phù hợp hơn AtStartup không user.
#>
param(
    [Parameter(Mandatory = $false)]
    [string] $ProjectRoot = "",
    [string] $TaskName = "FXBot-MT5"
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

$runScript = Join-Path $PSScriptRoot "run-fxbot.ps1"
if (-not (Test-Path $runScript)) {
    Write-Error "Thiếu file: $runScript"
}

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -ProjectRoot `"$ProjectRoot`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Đã đăng ký task '$TaskName' (At log on -> $runScript)"
Write-Host "Gỡ: .\\unregister-scheduled-task.ps1"
