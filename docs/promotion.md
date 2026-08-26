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

La demo valide le cablage. Elle ne reproduit pas la liquidite du reel.
