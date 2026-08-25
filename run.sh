#!/bin/bash
# Lancement Linux en lecture seule : aucun package ni terminal MT5.
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

export TRADING_MODE=off
echo "Demarrage Linux en TRADING_MODE=off (aucun acces trading MT5)."
echo "Le trading MT5 est supporte uniquement sous Windows natif."
python bot.py
