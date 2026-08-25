#!/bin/bash
# Lancement du bot MT5 AI — Linux/Mac
set -e

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
    echo "Fichier .env introuvable. Copie .env.example vers .env et remplis-le."
    exit 1
fi

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo "Demarrage du bot..."
python bot.py
