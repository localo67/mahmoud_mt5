# Pack scalp EURUSD (a tester en premier)

Bot autonome, **compte demo uniquement**. Une position a la fois.

## Idee

Toutes les minutes, quand une bougie est **terminee** :

1. Le spread (ecart achat/vente) n'est pas trop large (max 1.5 pip).
2. La bougie a un vrai corps (plus grand que 1.5 fois le spread) : ce n'est pas du bruit.
3. La moyenne EMA20 en M5 va dans le meme sens.
4. Stop au-dela de la bougie, objectif au moins **4 fois le spread**.

Sinon : **aucun trade**. C'est normal.

## Quand lancer

Seance Londres, jours de semaine, environ 8h-17h heure de Londres
(en France l'ete : souvent 9h-18h).

Maximum 8 essais par jour, pause de 5 minutes entre deux entrees.

## Windows

```powershell
.\scripts\windows\run-scalp-eurusd.ps1
```

Ce pack **n'est pas garanti gagnant**. Lis les logs : `EXECUTED`, `NO_SIGNAL`, `SPREAD_BLOCK`.
