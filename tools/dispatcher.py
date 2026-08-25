"""
Dispatcher : execute les actions structurees produites par l'IA
via les methodes du MT5Client et retourne des reponses formatees en francais.
"""

import logging
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mt5_client import MT5Client

logger = logging.getLogger(__name__)

MUTATING_FUNCTIONS = frozenset({
    "open_position",
    "close_position",
    "close_all_positions",
    "modify_position",
})


class Dispatcher:
    """
    Traduit les appels de fonction OpenAI en operations MT5 concretes
    et genere des messages de reponse en francais avec emojis.
    """

    def __init__(self, mt5: "MT5Client"):
        self.mt5 = mt5

    async def execute(self, action: dict) -> str:
        """
        Execute une action structuree et retourne le message de reponse.

        Args:
            action: {"function": "open_position", "arguments": {...}}

        Returns:
            str: Message formate en francais a envoyer a l'utilisateur
        """
        func_name = action.get("function", "")
        args = action.get("arguments", {})

        if func_name in MUTATING_FUNCTIONS:
            return (
                "Action refusee : le Dispatcher IA est strictement en lecture seule. "
                "Aucune mutation MT5 n'a ete appelee."
            )

        handler = self._get_handler(func_name)
        if handler is None:
            logger.warning(f"Fonction inconnue demandee : {func_name}")
            return (
                f" Je ne connais pas l'action '{func_name}'. "
                f"Essayez avec une autre formulation."
            )

        try:
            # Verifier la connexion MT5 avant chaque operation
            if not await self.mt5.check_connection():
                return (
                    " Impossible de se connecter a MetaTrader 5. "
                    "Verifiez que le terminal MT5 est ouvert et connecte."
                )

            return await handler(args)

        except Exception as e:
            logger.exception(f"Dispatcher : erreur dans {func_name} : {e}")
            return f" Erreur lors de l'execution : {str(e)}"

    # ------------------------------------------------------------------
    # Mapping fonctions -> handlers
    # ------------------------------------------------------------------

    def _get_handler(self, name: str):
        handlers = {
            "get_account_info": self._handle_account_info,
            "get_positions": self._handle_positions,
            "get_technical_analysis": self._handle_analysis,
        }
        return handlers.get(name)

    # ------------------------------------------------------------------
    # Handlers individuels
    # ------------------------------------------------------------------

    async def _handle_account_info(self, args: dict) -> str:
        info = await self.mt5.get_account_info()

        profit = info["equity"] - info["balance"]
        pnl_emoji = " " if profit >= 0 else " "

        lines = [
            f" Etat du compte",
            f"",
            f" Compte : {info['name']} (#{info['login']})",
            f" Serveur : {info['server']}",
            f"",
            f" Solde : **{info['balance']:,.2f}** {info['currency']}",
            f" Capital : **{info['equity']:,.2f}** {info['currency']}",
            f" P&L flottant : {profit:+,.2f} {info['currency']} {pnl_emoji}",
            f"",
            f" Marge : {info['margin']:,.2f} {info['currency']}",
            f" Marge libre : {info['free_margin']:,.2f} {info['currency']}",
        ]

        if info.get("margin_level"):
            lines.append(f" Niveau de marge : {info['margin_level']:.2f}%")

        lines.append(f" Levier : 1:{info['leverage']}")

        return "\n".join(lines)

    async def _handle_positions(self, args: dict) -> str:
        symbol = args.get("symbol")
        if symbol:
            symbol = symbol.upper()

        positions = await self.mt5.get_positions(symbol=symbol)

        if not positions:
            cible = f"sur {symbol}" if symbol else "ouvertes"
            return f" Aucune position {cible}. "

        total_pnl = sum(p["profit"] for p in positions)
        pnl_emoji = " " if total_pnl >= 0 else " "

        cible = f"sur {symbol}" if symbol else "ouvertes"
        lines = [f" Positions {cible} ({len(positions)}) :", ""]

        for p in positions:
            dir_emoji = " " if p["type"] == "BUY" else " "
            pnl_s = f"{p['profit']:+,.2f}"
            sl_s = f"{p['sl']:.5f}" if p["sl"] and p["sl"] > 0 else "Aucun"
            tp_s = f"{p['tp']:.5f}" if p["tp"] and p["tp"] > 0 else "Aucun"

            lines.append(
                f"{dir_emoji} **#{p['ticket']}** - {p['symbol']} {p['type']}\n"
                f"   Volume : {p['volume']} | Ouvert : {p['price_open']:.5f}\n"
                f"   SL : {sl_s} | TP : {tp_s}\n"
                f"   P&L : {pnl_s} | Swap : {p['swap']:+.2f}"
            )

        lines.append("")
        lines.append(f" P&L total : **{total_pnl:+,.2f}** {pnl_emoji}")

        return "\n".join(lines)

    async def _handle_analysis(self, args: dict) -> str:
        symbol = args.get("symbol", "EURUSD").upper()

        # Prix actuel
        try:
            price = await self.mt5.get_current_price(symbol)
        except Exception as e:
            return f" Impossible d'obtenir le prix pour {symbol} : {e}"

        # Donnees historiques pour les MAs
        rates = await self.mt5.get_rates(symbol, timeframe="M5", count=100)

        if rates is None or len(rates) < 50:
            return (
                f" Analyse {symbol}\n"
                f" Bid : {price['bid']:.5f}\n"
                f" Ask : {price['ask']:.5f}\n"
                f" Spread : {price['spread']:.5f}\n"
                f"\n"
                f" Donnees insuffisantes pour les indicateurs techniques "
                f"(donnees disponibles : {len(rates) if rates is not None else 0})."
            )

        closes = np.array([r.close for r in rates])

        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None

        # Tendance
        if ma20 and ma50:
            if ma20 > ma50:
                trend = "HAUSSIERE "
                trend_detail = f"MA20 ({ma20:.5f}) > MA50 ({ma50:.5f})"
            else:
                trend = "BAISSIERE "
                trend_detail = f"MA20 ({ma20:.5f}) < MA50 ({ma50:.5f})"
        else:
            trend = "INDETERMINEE "
            trend_detail = "Donnees insuffisantes"

        # Prix par rapport aux MAs
        current = price["bid"]
        ma_status = ""
        if ma20 and ma50:
            if current > ma20 and current > ma50:
                ma_status = "Le prix est au-dessus des deux MAs"
            elif current < ma20 and current < ma50:
                ma_status = "Le prix est en-dessous des deux MAs"
            elif ma20 > ma50:
                ma_status = "Le prix est entre les MAs (zone de pullback haussier)"
            else:
                ma_status = "Le prix est entre les MAs (zone de pullback baissier)"

        lines = [
            f" Analyse technique - {symbol}",
            f"",
            f" Bid : {price['bid']:.5f} | Ask : {price['ask']:.5f}",
            f" Spread : {price['spread']:.5f}",
            f"",
            f" Moyennes Mobiles (M5) :",
            f" MA(20) : {ma20:.5f}" if ma20 else " MA(20) : N/A",
            f" MA(50) : {ma50:.5f}" if ma50 else " MA(50) : N/A",
            f"",
            f" Tendance : {trend}",
            f" {trend_detail}",
            f" {ma_status}",
        ]

        return "\n".join(lines)
