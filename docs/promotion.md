# Portes de promotion shadow / paper / demo

Les seuils sont du code, pas des souvenirs. Les compteurs empiriques restent a
zero tant que les sessions reelles n'ont pas ete collectees. Un zero n'est pas
un GO.

| Etape | Minimum | Interdit |
| --- | --- | --- |
| Shadow | 20 sessions, 50 decisions eligibles | divergence replay inexpliquee, ordre non autorise |
| Paper | 20 sessions, 30 allers-retours | frais omis, code change sans reset des preuves |
| Demo | 60 sessions et max(100 trades clotures, volume pour les IC) | ecart de reconciliation |

Toute modification de code, donnees, regle ou parametre remet les preuves a
zero. Telegram ne passe aucun ordre. Le volume broker est le lot minimal, une
position, XAUUSD uniquement.

La chaine est obligatoire : `shadow().go` puis `paper().go` puis `demo().go`.
Un artefact de preuve (`artifact_id`) dont le hash differe du code/config/data
courants remet tous les compteurs a NO-GO.

En shadow, le ledger recoit les memes evenements canoniques qu'en demo
(`intent`, `check`, `fill_*`, `reconcile`) mais `order_send` reste interdit.
Paper n'est pas un `TRADING_MODE` : c'est un etage de preuve calcule depuis le
ledger simule.

La demo valide le cablage. Elle ne reproduit pas la liquidite du reel.
