# Automatisations Cursor autorisees

Le bot temps reel reste `bot.py` sous superviseur local sur le runtime MT5
valide. Cursor Automations sont des agents cloud : elles **n'executent jamais**
le trading.

## Autorise

1. Revue quotidienne de journaux **assainis** (sans mot de passe, token, login).
2. Comparaison d'un rapport de backtest/CI avec le champion gele.
3. Maintenance hebdomadaire proposant tests, documentation ou dependances.

La CI locale est `scripts/ci-check.sh` : pytest + compileall, aucun secret MT5.

## Interdit

- secret MT5, fichier `.env`, mot de passe broker
- acces Wine / terminal MT5
- outil d'ordre, `order_send`, armement
- modification automatique du risque ou de la strategie
- fusion ou deploiement automatiques

Cursor analyse et propose. Il ne place aucun ordre.
