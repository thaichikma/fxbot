#Requires -Version 5.1
<#
.SYNOPSIS
  Chạy FXBot (python -m src.main) từ thư mục gốc repo, dùng venv .venv.
.DESCRIPTION
  Dùng cho chạy tay hoặc làm hành động của Scheduled Task (At log on).
.PARAMETER ProjectRoot
  Đường dẫn thư mục gốc chứa src/, config/, .venv/
#>
param(
    [Parameter(Mandatory = $false)]
    [string] $ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Không tìm thấy $venvPython — tạo venv: python -m venv .venv && pip install -r requirements.txt"
}

# UTF-8 log/console an toàn hơn với loguru/Unicode
$env:PYTHONUTF8 = "1"

& $venvPython -m src.main
