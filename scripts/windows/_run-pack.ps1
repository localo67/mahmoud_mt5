param(
    [Parameter(Mandatory = $true)][string]$Pack
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Activate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
    Write-Error "Lance d'abord .\scripts\windows\00-setup.ps1"
    exit 1
}
. $Activate

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Error "Fichier .env manquant. Copie .env.example et remplis les identifiants MT5."
    exit 1
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null

$env:TRADING_MODE = "demo"
$env:STRATEGY_PACK = $Pack
$env:LOG_FILE = Join-Path $Root "logs\$Pack.log"

Write-Host "Pack=$Pack  TRADING_MODE=demo  --headless --arm-demo"
Write-Host "Log: $env:LOG_FILE"
Write-Host "Ctrl+C pour arreter. Un seul script run-*.ps1 a la fois."

python bot.py --headless --arm-demo --pack $Pack
exit $LASTEXITCODE
