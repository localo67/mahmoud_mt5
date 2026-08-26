$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Dossier projet: $Root"

if (-not (Test-Path (Join-Path $Root ".venv"))) {
    Write-Host "Creation du venv..."
    if (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv .venv
    } else {
        py -3 -m venv .venv
    }
}

$Activate = Join-Path $Root ".venv\Scripts\Activate.ps1"
. $Activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$EnvExample = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Fichier .env cree. Remplis MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, TRADING_MODE=demo"
} else {
    Write-Host ".env existe deja, non ecrase."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
Write-Host "Setup OK. Edite .env puis lance .\scripts\windows\01-test-connexion.ps1"
