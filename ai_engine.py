"""
Moteur d'intelligence artificielle utilisant NVIDIA Nemotron 3 Super (gratuit)
via OpenRouter avec Function Calling pour comprendre les ordres
de trading en langage naturel (francais).

OpenRouter est compatible avec le SDK OpenAI : on change juste le base_url.
"""

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from tools.definitions import FUNCTION_DEFINITIONS

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# System prompt (en francais, avec fallback JSON si pas de tool calling)
# ------------------------------------------------------------------

SYSTEM_PROMPT = """Tu es un assistant de trading expert qui aide les traders a gerer leurs positions sur MetaTrader 5.

TON ROLE :
- Comprendre les instructions de trading en francais et les convertir en actions precises
- Donner des reponses courtes, claires et professionnelles en francais
- Utiliser des emojis pour rendre les reponses agreables

CE QUE TU DOIS FAIRE :
Quand l'utilisateur exprime une intention de trading, reponds avec un bloc JSON dans ce format exact :
```json
{"function": "NOM_FONCTION", "arguments": {...}}
```

Fonctions disponibles et leurs arguments :
- open_position(symbol, order_type, volume, sl?, tp?, comment?)
- close_position(ticket)
- close_all_positions(symbol?)
- modify_position(ticket, sl?, tp?)
- get_account_info()
- get_positions(symbol?)
- get_technical_analysis(symbol)

Exemples :
- "achete 0.1 lot EURUSD" -> ```json\n{"function": "open_position", "arguments": {"symbol": "EURUSD", "order_type": "buy", "volume": 0.1}}\n```
- "vends 0.5 XAUUSD avec SL a 2500" -> ```json\n{"function": "open_position", "arguments": {"symbol": "XAUUSD", "order_type": "sell", "volume": 0.5, "sl": 2500}}\n```
- "ferme le ticket 12345" -> ```json\n{"function": "close_position", "arguments": {"ticket": 12345}}\n```
- "ferme toutes mes positions" -> ```json\n{"function": "close_all_positions", "arguments": {}}\n```
- "quel est mon solde ?" -> ```json\n{"function": "get_account_info", "arguments": {}}\n```
- "montre mes positions" -> ```json\n{"function": "get_positions", "arguments": {}}\n```
- "analyse EURUSD" -> ```json\n{"function": "get_technical_analysis", "arguments": {"symbol": "EURUSD"}}\n```

IMPORTANT :
- Reponds TOUJOURS avec un bloc JSON quand il s'agit d'une action de trading
- Si l'utilisateur ne donne pas de volume, utilise 0.01 par defaut
- Si l'utilisateur dit "achat" ou "long" -> order_type = "buy"
- Si l'utilisateur dit "vente", "short", "vend" -> order_type = "sell"
- Les symboles doivent etre en majuscules (EURUSD, GBPUSD, XAUUSD, etc.)
- Pour les SL/TP, utilise TOUJOURS des prix absolus, pas des ecarts en pips
- Si la demande est ambigue, pose une question pour clarifier SANS mettre de JSON
- Si ce n'est pas une demande de trading, reponds naturellement en francais SANS JSON"""

# ------------------------------------------------------------------
# Mapping rapide pour le fallback par mots-cles (si le modele echoue)
# ------------------------------------------------------------------

QUICK_PATTERNS = [
    # (regex, function_name, args_builder)
    (r"(?:quel|combien|affiche|montre|voir|consulter)\s+(?:est\s+)?(?:mon|le|mon)\s+solde", "get_account_info", lambda m: {}),
    (r"(?:quel|combien|affiche|montre|voir|consulter)\s+(?:est\s+)?(?:mon|le)\s+(?:capital|equity|compte)", "get_account_info", lambda m: {}),
    (r"(?:affiche|montre|liste|voir|quelles|quels)\s+(?:mes|les)\s+positions?", "get_positions", lambda m: {}),
    (r"positions?\s+(?:ouvertes?|en\s+cours)", "get_positions", lambda m: {}),
    (r"analyse(?:\s+technique)?\s+(\w+)", "get_technical_analysis", lambda m: {"symbol": m.group(1).upper()}),
    (r"ferme?\s+(?:toutes?|toutes)\s+(?:mes\s+)?positions?\s*(?:sur\s+(\w+))?", "close_all_positions", lambda m: {"symbol": m.group(1).upper()} if m.group(1) else {}),
    (r"ferme?\s+(?:la\s+)?position\s+(?:ticket\s+)?#?(\d+)", "close_position", lambda m: {"ticket": int(m.group(1))}),
]


class AIEngine:
    """
    Moteur de traitement du langage naturel.
    Utilise NVIDIA Nemotron 3 Super via OpenRouter (gratuit)
    pour analyser les messages en francais et produire des actions structurees.
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "https://github.com/mt5-ai-bot",  # Optionnel mais recommande par OpenRouter
                "X-Title": "MT5 AI Trading Bot",
            },
        )
        self.model = OPENROUTER_MODEL

    async def process_message(self, user_text: str) -> dict[str, Any]:
        """
        Analyse un message utilisateur et retourne l'action a effectuer.

        Args:
            user_text: Le message en francais de l'utilisateur

        Returns:
            dict avec les cles :
            - "intent": "trade_command" | "chat" | "error"
            - "action": {"function": str, "arguments": dict}  (si trade_command)
            - "response": str  (si chat ou error)
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        # --- Tentative 1 : API OpenRouter avec Function Calling ---
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=FUNCTION_DEFINITIONS,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=500,
            )
        except Exception as e:
            logger.error(f"OpenRouter API error : {e}")
            # Fallback : essayer sans les tools (certains modeles gratuits ne les supportent pas)
            logger.info("Nouvelle tentative sans Function Calling...")
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=500,
                )
            except Exception as e2:
                logger.error(f"OpenRouter API error (fallback) : {e2}")
                return {
                    "intent": "error",
                    "response": (
                        " Desole, je n'arrive pas a contacter l'IA (OpenRouter). "
                        "Verifiez votre connexion internet et votre cle API."
                    ),
                }

        # Verifier qu'on a bien une reponse
        if not response.choices:
            logger.warning("OpenRouter : pas de choix dans la reponse")
            return {
                "intent": "chat",
                "response": " Je n'ai pas compris. Pouvez-vous reformuler votre demande ?",
            }

        msg = response.choices[0].message

        # --- Cas 1 : Appel de fonction natif (tool_calls) ---
        if msg.tool_calls:
            return self._parse_tool_call(msg.tool_calls[0])

        # --- Cas 2 : JSON dans le texte (fallback si le modele ne supporte pas les tools) ---
        if msg.content:
            json_match = self._extract_json_from_text(msg.content)
            if json_match:
                return json_match

        # --- Cas 3 : Fallback par mots-cles (dernier recours) ---
        quick_result = self._quick_parse(user_text)
        if quick_result:
            return quick_result

        # --- Cas 4 : Reponse conversationnelle ---
        text = msg.content or "D'accord ! "
        return {
            "intent": "chat",
            "response": text,
        }

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_tool_call(self, tool_call) -> dict:
        """Parse un tool_call OpenAI standard."""
        func_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            logger.warning(f"Tool call : arguments JSON invalides : {e}")
            args = {}

        logger.info(
            f"AI (tool_call) : fonction={func_name} "
            f"args={json.dumps(args, ensure_ascii=False)}"
        )

        return {
            "intent": "trade_command",
            "action": {
                "function": func_name,
                "arguments": args,
            },
            "response": None,
        }

    def _extract_json_from_text(self, text: str) -> dict | None:
        """
        Tente d'extraire un bloc JSON du texte de reponse.
        Supporte les formats : ```json {...} ``` et {...} brut.
        """
        # Pattern 1 : bloc markdown ```json ... ```
        match = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                return self._validate_json_action(data)
            except json.JSONDecodeError:
                pass

        # Pattern 2 : JSON brut dans le texte { ... }
        match = re.search(r'\{[^{}]*"function"\s*:\s*"[^"]+"\s*[,}][^{}]*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return self._validate_json_action(data)
            except json.JSONDecodeError:
                pass

        return None

    def _validate_json_action(self, data: dict) -> dict | None:
        """Valide qu'un dict JSON contient bien une action reconnue."""
        func_name = data.get("function")
        if not func_name:
            return None

        valid_functions = {
            "open_position", "close_position", "close_all_positions",
            "modify_position", "get_account_info", "get_positions",
            "get_technical_analysis",
        }
        if func_name not in valid_functions:
            logger.warning(f"Fonction inconnue dans le JSON : {func_name}")
            return None

        logger.info(
            f"AI (json_parse) : fonction={func_name} "
            f"args={json.dumps(data.get('arguments', {}), ensure_ascii=False)}"
        )

        return {
            "intent": "trade_command",
            "action": {
                "function": func_name,
                "arguments": data.get("arguments", {}),
            },
            "response": None,
        }

    def _quick_parse(self, user_text: str) -> dict | None:
        """
        Fallback rapide par expressions regulieres.
        Utile si le modele ne repond pas du tout en JSON.
        """
        user_lower = user_text.lower().strip()

        for pattern, func_name, args_builder in QUICK_PATTERNS:
            match = re.search(pattern, user_lower)
            if match:
                logger.info(f"AI (quick_parse) : pattern={pattern} -> {func_name}")
                return {
                    "intent": "trade_command",
                    "action": {
                        "function": func_name,
                        "arguments": args_builder(match),
                    },
                    "response": None,
                }

        return None
