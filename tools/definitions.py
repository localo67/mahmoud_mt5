"""
Definitions des fonctions OpenAI (Function Calling) pour les operations de trading.
Chaque fonction est decrite en francais pour que le modele comprenne
les intentions exprimees en langage naturel.
"""

FUNCTION_DEFINITIONS = [
    # ------------------------------------------------------------------
    # 1. Ouvrir une position
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "open_position",
            "description": (
                "Ouvre une position d'achat (buy) ou de vente (sell) sur un symbole. "
                "Utilise cette fonction quand l'utilisateur veut trader, acheter, vendre, "
                "prendre une position, ou passer un ordre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbole de trading (ex: EURUSD, GBPUSD, XAUUSD, BTCUSD)",
                    },
                    "order_type": {
                        "type": "string",
                        "enum": ["buy", "sell"],
                        "description": "Type d'ordre : buy pour achat/achat/long, sell pour vente/vente/short",
                    },
                    "volume": {
                        "type": "number",
                        "description": "Volume en lots (ex: 0.01 = micro lot, 0.1 = mini lot, 1.0 = lot standard)",
                    },
                    "sl": {
                        "type": "number",
                        "description": "Stop Loss en prix absolu (optionnel)",
                    },
                    "tp": {
                        "type": "number",
                        "description": "Take Profit en prix absolu (optionnel)",
                    },
                    "comment": {
                        "type": "string",
                        "description": "Commentaire optionnel pour identifier la position",
                    },
                },
                "required": ["symbol", "order_type", "volume"],
            },
        },
    },
    # ------------------------------------------------------------------
    # 2. Fermer une position
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "close_position",
            "description": (
                "Ferme une position existante par son numero de ticket. "
                "Utilise quand l'utilisateur veut fermer, cloturer, vendre ou sortir d'une position specifique."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket": {
                        "type": "integer",
                        "description": "Numero du ticket (identifiant) de la position a fermer",
                    },
                },
                "required": ["ticket"],
            },
        },
    },
    # ------------------------------------------------------------------
    # 3. Fermer toutes les positions
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "close_all_positions",
            "description": (
                "Ferme toutes les positions ouvertes, ou toutes les positions d'un symbole specifique. "
                "Utilise quand l'utilisateur dit 'ferme tout', 'cloture toutes mes positions', "
                "'ferme mes EURUSD', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbole optionnel pour ne fermer que les positions de ce symbole",
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # 4. Modifier une position
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "modify_position",
            "description": (
                "Modifie le Stop Loss (SL) et/ou le Take Profit (TP) d'une position existante. "
                "Utilise quand l'utilisateur veut ajuster, modifier, changer ou deplacer son SL ou TP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket": {
                        "type": "integer",
                        "description": "Numero du ticket de la position a modifier",
                    },
                    "sl": {
                        "type": "number",
                        "description": "Nouveau prix de Stop Loss (optionnel)",
                    },
                    "tp": {
                        "type": "number",
                        "description": "Nouveau prix de Take Profit (optionnel)",
                    },
                },
                "required": ["ticket"],
            },
        },
    },
    # ------------------------------------------------------------------
    # 5. Consulter le compte
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_account_info",
            "description": (
                "Consulte les informations du compte de trading : solde, capital (equity), "
                "marge utilisee, marge libre, niveau de marge et levier. "
                "Utilise quand l'utilisateur demande son solde, son capital, l'etat de son compte, "
                "combien il a, ou sa marge disponible."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    # ------------------------------------------------------------------
    # 6. Lister les positions
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_positions",
            "description": (
                "Liste toutes les positions ouvertes avec leur profit/perte (P&L). "
                "Utilise quand l'utilisateur demande ses positions, ce qu'il a en cours, "
                "ses trades ouverts, ou l'etat de ses ordres."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbole optionnel pour filtrer les positions",
                    },
                },
            },
        },
    },
    # ------------------------------------------------------------------
    # 7. Analyse technique
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_technical_analysis",
            "description": (
                "Analyse technique d'un symbole : prix actuel (bid/ask/spread), "
                "moyennes mobiles 20 et 50 periodes, et tendance (haussier/baissier). "
                "Utilise quand l'utilisateur demande une analyse, le prix, la tendance, "
                "ou les indicateurs techniques d'un symbole."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbole a analyser (ex: EURUSD, GBPUSD, XAUUSD)",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
]
