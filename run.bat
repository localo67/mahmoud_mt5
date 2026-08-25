@echo off
REM Lancement du bot MT5 AI — Windows
cd /d "%~dp0"

if not exist ".env" (
    echo Fichier .env introuvable. Copie .env.example vers .env et remplis-le.
    pause
    exit /b 1
)

if not exist "venv\" (
    python -m venv venv
)

call venv\Scripts\activate
pip install -q -r requirements.txt

echo Demarrage du bot...
python bot.py
pause
