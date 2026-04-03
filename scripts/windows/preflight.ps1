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
        # Do not use python -c with a multiline string: PowerShell may corrupt quotes when passing args.
        $tmp = Join-Path $env:TEMP ("fxbot_preflight_mt5_{0}.py" -f [guid]::NewGuid().ToString('N'))
        $py = @'
import sys
try:
    import MetaTrader5 as mt5
    print("OK: MetaTrader5 import")
except Exception as ex:
    print("FAIL MetaTrader5:", ex)
    sys.exit(1)
'@
        Set-Content -LiteralPath $tmp -Value $py -Encoding UTF8
        & $venvPy $tmp
        $mt5Exit = $LASTEXITCODE
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        if ($mt5Exit -ne 0) { $ok = $false }
    }
} else {
    Write-Host '[SKIP] Not Windows - MetaTrader5 Python package is Windows-only'
}

if (-not $ok) {
    exit 1
}
Write-Host '=== Done ==='
