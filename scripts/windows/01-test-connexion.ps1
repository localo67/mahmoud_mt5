$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Activate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
    Write-Error "Lance d'abord .\scripts\windows\00-setup.ps1"
    exit 1
}
. $Activate

if (-not $env:TRADING_MODE) {
    $env:TRADING_MODE = "demo"
}

Write-Host "Test connexion MT5 (mode=$env:TRADING_MODE). Terminal MT5 ouvert ?"
python scripts/windows-smoke.py
exit $LASTEXITCODE
