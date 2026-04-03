#Requires -Version 5.1
<#
.SYNOPSIS
  Kiểm tra nhanh môi trường Windows trước khi chạy FXBot production.
#>
param(
    [Parameter(Mandatory = $false)]
    [string] $ProjectRoot = ""
)

$ErrorActionPreference = "Continue"
$ok = $true

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

Write-Host "=== FXBot preflight ===" 
Write-Host "ProjectRoot: $ProjectRoot"

$venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    Write-Host "[OK] venv: $venvPy"
    & $venvPy --version
} else {
    Write-Host "[FAIL] Chưa có .venv — python -m venv .venv && pip install -r requirements.txt"
    $ok = $false
}

$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Write-Host "[OK] .env tồn tại"
} else {
    Write-Host "[WARN] Chưa có .env — copy từ .env.example"
}

if ($env:OS -like "*Windows*") {
    if (Test-Path $venvPy) {
        $code = @"
import sys
try:
    import MetaTrader5 as mt5
    print('[OK] import MetaTrader5')
except Exception as e:
    print('[FAIL] MetaTrader5:', e)
    sys.exit(1)
"@
        & $venvPy -c $code
        if ($LASTEXITCODE -ne 0) { $ok = $false }
    }
} else {
    Write-Host "[SKIP] Không phải Windows — MT5 chỉ trên Windows"
}

if (-not $ok) {
    exit 1
}
Write-Host "=== Xong ==="
