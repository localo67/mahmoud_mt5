# Runbook incidents

## Trois capacites separees

`ops/control.py` persiste trois drapeaux independants :

- `entries_allowed` : bloque toute nouvelle exposition ;
- `position_management_enabled` : laisse reconcilier, resserrer un SL et sortir
  en fin de session ;
- `emergency_exit_requested` : sortie explicite, ticket par ticket, positions
  possedees uniquement. Ce n'est **pas** un `close_all`.

Un halt d'entrees n'appelle jamais `close_all_positions`.

## Arret des nouvelles entrees

Declencheurs : mauvais compte/symbole/version, donnee perimee, SL absent,
position inconnue, reconciliation en echec, limite de perte, kill switch,
exposition ambigue (timeout apres `SEND_ATTEMPT_STARTED`).

1. Bloquer les entrees (`Monitor.observe` -> `OperationalControl.halt_entries`).
2. Ne **pas** fermer aveuglement toutes les positions.
3. Laisser `position_management_enabled` actif pour reconcilier et gerer les SL.
4. Reconcilier journal interne, ordres, deals, positions, releve.
5. Restaurer le ledger depuis un backup `integrity_check` OK, instance desarmee.
6. Post-mortem date, sans optimisation automatique en production.

## Restauration du ledger

1. Halt des entrees et arret du writer.
2. `Ledger.backup()` vers un fichier neuf, `PRAGMA integrity_check`.
3. `Ledger.restore_to()` vers un nouveau fichier, puis echange atomique.
4. Redemarrage desarme, reconciliation complete, reprise seulement si zero gap.

## Smoke test Windows natif

Voir `scripts/windows-smoke.py` : `off`, puis `shadow` (zero `order_send`),
puis `demo` desarme. L'envoi demo arme reste une validation manuelle separee.

## Revues

- Hebdomadaire : operations, incidents, fraicheur, rejets.
- Mensuelle : statistique hors echantillon vs champion gele.
- Trimestrielle : modele complet, fournisseurs, licences.
