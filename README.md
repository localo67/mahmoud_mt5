# MT5 XAUUSD Bot

Bot personnel pour MetaTrader 5. Il surveille **l'or** (`XAUUSD`) et peut
ouvrir **au plus un trade par jour** pendant la seance de New York, selon une
regle fixe (casse du range d'ouverture). L'IA Telegram ne decide pas les
achats/ventes.

Le mode `live` (argent reel) est refuse. Utilise un **compte demo**.

---

## Tester en demo (Windows)

MetaTrader 5 ne fonctionne **pas** sur Linux. Il te faut un PC Windows.

1. Installe [MetaTrader 5](https://www.metatrader5.com/) et ouvre un **compte demo**.
2. Dans MT5 : Outils → Options → Expert Advisors → coche **Autoriser le trading algorithmique**.
3. Laisse le terminal MT5 **ouvert et connecte**.
4. Copie le projet, puis :

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

5. Remplis `.env` : Telegram, OpenRouter, `TRADING_MODE=demo`, login / mot de passe / serveur MT5.
6. Lance :

```powershell
python bot.py --arm-demo
```

Sans `--arm-demo`, le bot se connecte mais **n'envoie aucun ordre**.
Telegram (`/auto`, `/reset`) ne peut pas armer le trading.

Arret : `Ctrl+C`. Au prochain lancement, le bot est **desarme** jusqu'a ce que tu remettes `--arm-demo`.

---

## A quoi s'attendre

Ce n'est **pas** du scalping rapide. Beaucoup de jours : **zero trade**.

Un ordre n'est possible que si tout ceci est vrai en meme temps :

- jour de semaine, seance New York (9h–17h heure de New York)
- les 30 premieres minutes ont un haut et un bas
- une bougie M5 **suivante** casse clairement ce haut ou ce bas
- pas de position deja ouverte, spread pas trop large, limites de perte OK

Sinon tu verras dans les logs `WAIT`, `NO_SIGNAL` ou `OUTSIDE_SESSION`. C'est normal.

---

## Autres modes (tu peux les ignorer)

| Mode | Role |
| --- | --- |
| `off` | Defaut sur Linux : tests et Telegram, sans MT5 |
| `shadow` | Connecte a MT5, calcule, **n'envoie jamais** d'ordre |
| `demo` | Ordres reels sur compte fictif, si `--arm-demo` |
| `live` | Refuse |

---

## Linux (developpeur)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```

`run.sh` force `TRADING_MODE=off`. Voir [docs/runtime.md](docs/runtime.md).
