#Requires -Version 5.1
<#
.SYNOPSIS
  Quick environment check before running FXBot on Windows (venv, .env, MetaTrader5).
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

Write-Host '=== FXBot preflight ==='
Write-Host "ProjectRoot: $ProjectRoot"

$venvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    Write-Host "[OK] venv: $venvPy"
    & $venvPy --version
} else {
    Write-Host '[FAIL] No .venv - run: python -m venv .venv ; pip install -r requirements.txt'
    $ok = $false
}

$envFile = Join-Path $ProjectRoot ".env"
if (Test-Path $envFile) {
    Write-Host '[OK] .env exists'
} else {
    Write-Host '[WARN] No .env - copy from .env.example'
}

if ($env:OS -like "*Windows*") {
    if (Test-Path $venvPy) {
        $code = @'
import sys
try:
    import MetaTrader5 as mt5
    print("[OK] import MetaTrader5")
except Exception as ex:
    print("[FAIL] MetaTrader5:", ex)
    sys.exit(1)
'@
        & $venvPy -c $code
        if ($LASTEXITCODE -ne 0) { $ok = $false }
    }
} else {
    Write-Host '[SKIP] Not Windows - MetaTrader5 Python package is Windows-only'
}

if (-not $ok) {
    exit 1
}
Write-Host '=== Done ==='
