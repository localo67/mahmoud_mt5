# MT5 AI Trading Bot

Bot de trading complet combinant **Telegram**, **NVIDIA Nemotron 3 Super** (gratuit via OpenRouter), et **MetaTrader 5**.

- Interface Telegram en francais avec emojis
- Comprend les ordres en langage naturel (francais)
- Strategie automatisee : MA Crossover et RSI
- Securise : seul un chat_id autorise peut utiliser le bot

---

## Structure du projet

```
mt5-ai-bot/
├── bot.py                  # Point d'entree, assemble tout
├── config.py               # Configuration et constantes
├── mt5_client.py           # Wrapper asynchrone MetaTrader 5
├── ai_engine.py            # Moteur IA (OpenRouter + Nemotron 3 Super)
├── automation.py           # Strategies automatisees (MA + RSI)
├── handlers/
│   ├── commands.py         # Handlers des commandes Telegram
│   └── messages.py         # Handlers messages libres et callbacks
├── tools/
│   ├── definitions.py      # Schemas OpenAI pour le Function Calling
│   └── dispatcher.py       # Execution des actions de trading
├── .env.example            # Template de configuration
├── requirements.txt        # Dependances Python
└── README.md               # Ce fichier
```

---

## Fonctionnalites

### 1. Trading manuel en langage naturel
Envoyez un message en francais et l'IA l'interprete :
- _"Achete 0.1 lot EURUSD avec SL a 1.0500"_
- _"Vends 0.5 XAUUSD"_
- _"Ferme le ticket 12345678"_
- _"Ferme toutes mes positions"_
- _"Modifie le SL du ticket 12345678 a 1.0850"_

### 2. Consultation du compte
- `/solde` - Solde, capital, marge disponible
- `/positions` - Positions ouvertes avec P&L

### 3. Analyse technique
- `/analyse EURUSD` - Prix actuel, MA20, MA50, tendance
- Boutons inline pour analyses rapides

### 4. Automatisation
- `/auto on` - Active les strategies MA Crossover et RSI
- `/auto off` - Met en pause
- Alertes Telegram automatiques a chaque signal
- Execution automatique des trades

### 5. Boutons inline
Menu principal avec actions rapides : Solde, Positions, Analyse, Automation

### 6. Securite
Seul le `AUTHORIZED_CHAT_ID` peut interagir avec le bot

---

## Installation

### Prerequisites

- Python 3.10 ou plus recent
- Un compte [OpenRouter](https://openrouter.ai/) (cle API gratuite)
- MetaTrader 5 installe et connecte a un compte (demo ou reel)
- Un bot Telegram (creer via [@BotFather](https://t.me/BotFather))

### 1. Cloner et installer les dependances

```bash
cd mt5-ai-bot
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou : venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Editer .env avec vos propres valeurs
```

Variables requises :
| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Token du bot Telegram (via @BotFather) |
| `OPENROUTER_API_KEY` | Cle API OpenRouter (gratuite sur openrouter.ai/keys) |
| `OPENROUTER_MODEL` | Modele IA (defaut : `nvidia/nemotron-3-super-120b-a12b:free`) |
| `AUTHORIZED_CHAT_ID` | Votre ID Telegram personnel |
| `MT5_LOGIN` | Numero de compte MT5 |
| `MT5_PASSWORD` | Mot de passe MT5 |
| `MT5_SERVER` | Nom du serveur du broker |

> Pour obtenir votre `AUTHORIZED_CHAT_ID`, envoyez un message a [@userinfobot](https://t.me/userinfobot) sur Telegram.

### 3. Lancer le bot

```bash
python bot.py
```

---

### 4. Obtenir une cle API OpenRouter (gratuit)

1. Creez un compte sur [openrouter.ai](https://openrouter.ai/)
2. Allez dans [openrouter.ai/keys](https://openrouter.ai/keys)
3. Creez une cle API et copiez-la dans votre `.env`

**Modeles gratuits alternatifs** (modifiez `OPENROUTER_MODEL` dans `.env`) :

| Modele | ID OpenRouter | Contexte |
|--------|--------------|----------|
| Nemotron 3 Super (defaut) | `nvidia/nemotron-3-super-120b-a12b:free` | 1M |
| Nemotron 3 Nano Omni | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256K |
| Nemotron Nano 9B v2 | `nvidia/nemotron-nano-9b-v2:free` | 128K |

> **Note** : Les modeles gratuits ont des limites (20 requetes/min). Le bot inclut un systeme de fallback : si le modele ne supporte pas le Function Calling natif, il extrait le JSON du texte de reponse.

---

## MetaTrader 5 sur Linux

Le package Python `MetaTrader5` est un binaire Windows. Sur Linux, deux options :

### Option A : Wine (recommandee)

```bash
# Installer Wine
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install wine64 wine32

# Installer MT5 sous Wine
wine mt5setup.exe

# Installer Windows Python sous Wine
wine python-3.10.11-amd64.exe

# Installer le package MetaTrader5
wine python -m pip install MetaTrader5

# Lancer MT5 sous Wine AVANT de demarrer le bot
wine "C:\Program Files\MetaTrader 5\terminal64.exe"
```

### Option B : Mode mock (developpement)

Pour tester le bot sans MT5, vous pouvez creer un mock de `MT5Client`.
Le bot continuera a fonctionner pour les interactions Telegram et IA.

---

## Strategies d'automation

### MA Crossover (Golden Cross / Death Cross)
- Utilise MA20 et MA50 sur timeframe M5
- Golden Cross (MA20 passe au-dessus de MA50) = Signal **BUY**
- Death Cross (MA20 passe en-dessous de MA50) = Signal **SELL**

### RSI (Relative Strength Index)
- Periode 14
- RSI >= 70 = Surachat = Signal **SELL**
- RSI <= 30 = Survente = Signal **BUY**

Les deux strategies tournent en parallele et sont independantes.

---

## Exemples d'utilisation

```
Utilisateur : Quel est mon solde ?
Bot : Solde du compte ...
      Solde : 10,234.56 EUR
      Capital : 10,189.23 EUR
      ...

Utilisateur : Achete 0.1 lot EURUSD avec SL a 1.0520 et TP a 1.0580
Bot : Position ouverte avec succes !
      Ticket : 12345678
      Symbole : EURUSD
      Direction : ACHAT
      Volume : 0.1 lot(s)
      ...

Utilisateur : Analyse XAUUSD
Bot : Analyse technique - XAUUSD
      Bid : 2650.32 | Ask : 2650.80
      MA(20) : 2648.15
      MA(50) : 2642.90
      Tendance : HAUSSIERE
      ...
```

---

## Licence

Ce projet est fourni a titre educatif. Le trading comporte des risques.
Utilisez toujours un compte demo avant de trader en reel.
