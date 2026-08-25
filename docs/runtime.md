# Runtimes supportes

## Windows natif : seul runtime MT5

Le terminal MetaTrader 5 et le package Python `MetaTrader5` doivent tourner dans
la meme session Windows. C'est le seul runtime autorise pour connecter le bot a
un compte MT5. Le package est installe automatiquement par `requirements.txt`
uniquement sous Windows.

Les mutations restent bloquees au demarrage. Elles ne sont autorisees que si les
trois conditions suivantes sont reunies :

1. `TRADING_MODE=demo` ;
2. l'API MT5 confirme `ACCOUNT_TRADE_MODE_DEMO` ;
3. l'instance `MT5Client` a ete explicitement armee en memoire avec
   `arm_trading()`.

L'armement n'est ni lu depuis l'environnement ni persiste. Une nouvelle instance
est toujours desarmee. `TRADING_MODE=live` est reconnu mais refuse : le trading
live n'est pas implemente au jalon J0.

La derniere verification du mode, de l'armement et du type de compte est
executee atomiquement avec `order_send`. Tous les appels MT5 de toutes les
instances partagent un executant mono-thread, ferme explicitement par le bot et
par un hook de fin de processus.

Avant toute utilisation demo, un smoke test manuel reste obligatoire sur une
machine Windows avec terminal MT5 ouvert, compte demo verifie et trading
algorithmique active. Ce test ne peut pas etre execute depuis Debian.

## Linux Debian : developpement et tests

Linux ne charge pas le package `MetaTrader5`. L'import du client reste possible
pour les tests par injection d'une API factice. Les usages autorises sont :

- tests unitaires et d'integration sans broker ;
- recherche, analyse hors ligne et backtests ;
- execution du bot en lecture seule avec `TRADING_MODE=off`.

`run.sh` force `TRADING_MODE=off`. Il ne fournit aucun acces trading, meme si une
autre valeur est presente dans le fichier d'environnement.
L'unite `systemd/xauusd-bot.service` force egalement ce mode.

En mode `off`, les identifiants MT5 ne sont pas requis et le bot n'essaie pas
d'initialiser MT5. Les modes `shadow`, `demo` et `live` dependent des lectures
MT5 et exigent donc `MT5_LOGIN`, `MT5_PASSWORD` et `MT5_SERVER`.

Installation de developpement :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Docker : sans MT5

L'image Linux n'installe pas `MetaTrader5`. Le `Dockerfile` et
`docker-compose.yml` imposent le mode `off` par defaut ; Compose le force
explicitement. Docker sert aux composants IA/Telegram en lecture seule et aux
traitements hors ligne, jamais au trading MT5.
