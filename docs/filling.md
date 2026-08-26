# Filling MT5

Le mode de filling n'est pas hardcode. `core/filling.py` lit le bitmask
`SYMBOL_FILLING_*` du symbole a chaque connexion.

| Bit symbole | Constante ordre | Marche OTC XAUUSD |
| --- | --- | --- |
| `SYMBOL_FILLING_IOC` (2) | `ORDER_FILLING_IOC` | Preferer si annonce |
| `SYMBOL_FILLING_FOK` (1) | `ORDER_FILLING_FOK` | Sinon si annonce |
| aucun | `ORDER_FILLING_RETURN` | Instant/Request ; interdit en Market Execution |

Politique actuelle :

- IOC partiel : fill enregistre, reliquat `CANCELED`.
- RETURN partiel : reliquat encore actif.
- FOK partiel : anomalie, halt des entrees, reconcilier, ne pas renvoyer.

Les pending orders, si un jour ajoutes, doivent utiliser RETURN.
