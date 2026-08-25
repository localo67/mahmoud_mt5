# Charte de recherche

## Objectif

Produire des resultats XAUUSD reproductibles sans confondre exploration,
backtest et preuve de performance. Aucun resultat de recherche n'autorise le
trading live.

## Regles

1. Enoncer avant l'experience une hypothese falsifiable et le mecanisme de
   marche suppose.
2. Figer les parametres, les donnees et le budget maximal de variantes avant
   de consulter les resultats hors echantillon.
3. Separer chronologiquement apprentissage, validation et test final. Ne jamais
   reutiliser le test final pour ajuster une strategie.
4. Inclure spread, commission, swap, slippage et contraintes d'execution dans
   les couts. Documenter toute valeur estimee.
5. Rapporter les metriques positives et negatives, y compris drawdown,
   dispersion, nombre de trades et sensibilite aux couts.
6. Conserver la version du code, les hashes des donnees et la configuration
   complete necessaires a la reproduction.
7. Enregistrer toutes les variantes essayees, y compris les echecs. Une
   variante non declaree compte dans le budget.
8. Definir les criteres de decision avant le lancement : accepter, iterer ou
   abandonner. Une decision doit citer les resultats qui la justifient.
9. Executer recherche et backtests sans acces trading sous Linux ou Docker.
   Toute verification MT5 se limite a un compte demo sous Windows natif, avec
   armement explicite en memoire.

## Revue minimale

Une experience n'est recevable que si son registre contient : hypothese,
mecanisme, parametres, budget de variantes, donnees, couts, metriques,
versions/hashes et decision. Utiliser
`docs/experiment-register-template.md` pour chaque nouvelle experience.
