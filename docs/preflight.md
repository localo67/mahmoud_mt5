# Préflight et diagnostic shadow

Le préflight produit un rapport machine-lisible **sans secret**. Il ne contient
jamais de mot de passe, token ou identifiant de connexion. Il n'appelle jamais
`order_send` : seul `order_check` est autorisé.

Le mode `shadow` parcourt le pipeline jusqu'à un candidat d'ordre. Le résultat
est `SHADOW_CANDIDATE`. Aucune mutation n'est envoyée au broker.

`WAIT` est un résultat valide. Une bougie clôturée sans trade n'est pas un
échec silencieux : chaque évaluation retourne `CycleResult` avec `blockers[]`.

## Exemple assaini

```json
{
  "ok": true,
  "blockers": [],
  "account": {
    "trade_mode": "demo",
    "currency": "USD",
    "leverage": 100,
    "margin_free": 10000.0
  },
  "terminal": {
    "connected": true,
    "trade_allowed": true,
    "name": "MetaTrader 5"
  },
  "symbol": {
    "requested": "XAUUSD",
    "resolved": "XAUUSD.s",
    "candidates": ["XAUUSD.s"],
    "ambiguous": false
  },
  "specs": {
    "point": 0.01,
    "volume_min": 0.01,
    "filling_mode": 1
  },
  "rates": {
    "m5_closed": 199,
    "m15_closed": 199
  },
  "tick": {
    "bid": 2500.0,
    "ask": 2500.2,
    "spread": 0.2,
    "age_seconds": 1
  },
  "order_check": {
    "ok": true,
    "called": true,
    "retcode": 10009
  }
}
```

## Bloqueurs

| Code | Signification |
| --- | --- |
| `MT5_UNAVAILABLE` | Package ou API MT5 absent |
| `PREFLIGHT_FAILED` | Compte non démo, terminal absent ou Algo Trading off |
| `NOT_ARMED` | Armement en mémoire manquant (mode demo) |
| `SYMBOL_UNRESOLVED` | Symbole absent ou suffixe ambigu (aucun choix automatique) |
| `STALE_TICK` | Dernier tick trop ancien |
| `INSUFFICIENT_CLOSED_BARS` | Moins de 50 bougies M5/M15 déjà clôturées |
| `OUTSIDE_SESSION` | Hors fenêtre de session configurée |
| `NEWS_BLOCK` | Fenêtre news, ou filtre news en échec (fail-closed) |
| `RISK_BLOCK` | Limite de risque |
| `SPREAD_BLOCK` | Spread au-dessus du plafond |
| `MARGIN_BLOCK` | Marge insuffisante ou lecture de marge en échec |
| `POSITION_EXISTS` | Position déjà ouverte sur le symbole |
| `AI_WAIT` | Décision WAIT (valide) |
| `LOW_CONFIDENCE` | Confiance sous le seuil |
| `SYMBOL_SPEC_CHANGED` | Spécifications broker changées en cours de session |
| `ORDER_CHECK_REJECTED` | `order_check` refusé, ou SL/TP manquant |
| `SHADOW_CANDIDATE` | Candidat valide en shadow, aucun `order_send` |
| `SEND_AMBIGUOUS` | Envoi demo sans confirmation claire |
| `RECONCILIATION_ERROR` | Écart interne/broker (J3) |
| `EXECUTED` | Ordre demo confirmé |

La commande Telegram `/status` affiche le compteur de bougies évaluées et la
distribution des bloqueurs. Plusieurs codes peuvent coexister sur la même
bougie.
