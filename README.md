# MT5 Demo Bot (packs de strategies)

Bot autonome pour **compte demo** MetaTrader 5. Une strategie a la fois.
Le mode `live` (argent reel) est refuse.

Aucune strategie n'est garantie gagnante. Les logs disent si ca trade, et pourquoi pas.

---

## Windows (ce que tu lances)

MetaTrader 5 ouvert, compte **demo**, trading algorithmique coche.

```powershell
git pull
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\windows\00-setup.ps1
```

Edite `.env` :

```
TRADING_MODE=demo
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...
```

Telegram n'est **pas** obligatoire pour ces scripts.

```powershell
.\scripts\windows\01-test-connexion.ps1
.\scripts\windows\run-scalp-eurusd.ps1
```

Ordre de test :

1. `.\scripts\windows\run-scalp-eurusd.ps1`  (premier, spread plus petit)
2. `.\scripts\windows\run-scalp-xauusd.ps1`
3. `.\scripts\windows\run-breakout-xauusd.ps1`

Un seul `run-*.ps1` a la fois. Arret : `Ctrl+C`.
Au relancement, il faut re-lancer le script (l'armement n'est pas sauvegarde).

Logs : `logs\<nom-du-pack>.log`

---

## Packs

| Dossier | Idee |
| --- | --- |
| `packs/scalp_eurusd_m1` | Scalp M1 EURUSD, TP au moins 4x le spread |
| `packs/scalp_xauusd_m1` | Meme idee sur l'or |
| `packs/session_breakout_xauusd` | 1 trade/jour, cassure New York |

Chaque pack a son journal SQLite dans `data/` pour ne pas melanger les resultats.

---

## Linux (developpeur)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```
