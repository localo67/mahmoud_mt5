# Runbook incidents

## Arret des nouvelles entrees

Declencheurs : mauvais compte/symbole/version, donnee perimee, SL absent,
position inconnue, reconciliation en echec, limite de perte, kill switch.

1. Bloquer les entrees (`Monitor.observe` -> halt, desarmer `MT5Client`).
2. Ne **pas** fermer aveuglement toutes les positions.
3. Appliquer la politique preecrite position par position.
4. Reconcilier journal interne, ordres, deals, positions, releve.
5. Restaurer la derniere version validee si le code est en cause.
6. Post-mortem date, sans optimisation automatique en production.

## Revues

- Hebdomadaire : operations, incidents, fraicheur, rejets.
- Mensuelle : statistique hors echantillon vs champion gele.
- Trimestrielle : modele complet, fournisseurs, licences.

Pause des qu'un indicateur de cout, risque ou comportement sort durablement de
son enveloppe. Decommission si la revalidation preenregistree ne retrouve pas
l'avantage.
