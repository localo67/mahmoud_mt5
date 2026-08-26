# Registre fournisseurs

| Fournisseur | Role | Fallback | Fail-closed |
| --- | --- | --- | --- |
| Broker / MetaTrader 5 | execution, specs, ticks | aucun trading | oui : pas d'ordre si API/compte invalide |
| Runtime Windows natif | terminal MT5 | Linux tests injectes | oui |
| Telegram | lecture seule | logs locaux | oui : pas de mutation |
| OpenRouter / modeles IA | veto optionnel | VETO sur timeout | oui |
| News / FMP | calendrier et titres | bloquer si `first_seen_at` absent | oui |
| SQLite ledger | journal applicatif | arret entrees | oui |

Versions, quotas, SLA et licences doivent etre renseignes avant tout canari
live. Aucun secret n'est stocke dans ce fichier.
