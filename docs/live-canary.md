# Canari live conditionnel

Le mode `TRADING_MODE=live` est reconnu et **refuse**. Aucune mutation live
n'est implementee. Une nouvelle approbation explicite de l'utilisateur est
obligatoire avant tout travail d'implementation.

## Preconditions

- Verifier avec le broker (et si besoin des professionnels competents) :
  automatisation autorisee, produit XAUUSD, conservation des ordres, fiscalite
  locale, licences news/donnees, confidentialite Telegram/IA. Ceci n'est pas un
  conseil juridique ou fiscal.
- Manifeste signe : capital max, risque par trade, pertes jour/semaine/mois,
  drawdown peak-to-trough, marge minimale, perte totale du canari.
- Secrets demo et live separes. Armement a deux niveaux, desarme a chaque
  restart.
- Si le lot minimal broker depasse le risque par trade : **NO-GO**.

## Canari

- XAUUSD uniquement, une strategie/version, une session, une position, lot
  minimal, aucun ordre Telegram, challengers en shadow.
- Premiere revue apres au moins 20 sessions et 30 trades reels clotures.
- Hausse au plus x2 apres revue humaine, jamais apres une courte serie gagnante.
- TCA : prix de decision, mid, arrivee, soumission, accuse, fill, spread paye,
  slippage, implementation shortfall, adverse selection.

ROLLBACK a la premiere violation. Aucun palier automatique.
