# Qualite des donnees et replay

Les ticks bid/ask sont archives en SQLite evenementiel. Un export colonnes
`.parquet` (conteneur versionne `MT5PARQ1`) est produit au flush. `time_msc`,
latence et specifications symbole peuvent etre joints.

Le backtest est evenementiel : le signal n'est evalue qu'apres cloture de
bougie, le fill utilise le tick suivant, achat au ask, vente au bid, SL/TP
tick par tick.

Les news historiques sans `first_seen_at` sont refusees. Elles ne sont jamais
reconstruites.

Un replay dore sur les memes ticks, barres et fonction de signal doit etre
bit-a-bit identique. `assert_no_lookahead` echoue si une barre future est lue.
