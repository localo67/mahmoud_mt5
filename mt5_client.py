"""
Client MetaTrader 5 asynchrone.
Tous les appels bloquants MT5 sont executes via run_in_executor()
pour ne pas bloquer l'event loop asyncio.
"""

import asyncio
import logging
from typing import Optional, Any

import MetaTrader5 as mt5

from config import (
    MT5_LOGIN,
    MT5_PASSWORD,
    MT5_SERVER,
    MAX_RETRIES,
    DEVIATION_PIPS,
    MAGIC_NUMBER,
    TIMEFRAME_MAP,
)

logger = logging.getLogger(__name__)


class MT5Error(Exception):
    """Erreur personnalisee pour les operations MT5."""

    def __init__(self, message: str, retcode: Optional[int] = None):
        super().__init__(message)
        self.retcode = retcode


class MT5Client:
    """
    Gestionnaire de connexion et d'operations MetaTrader 5.
    Toutes les methodes publiques sont async et thread-safe.
    """

    def __init__(self):
        self._initialized: bool = False
        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    # ------------------------------------------------------------------
    # Cycle de vie de la connexion
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """
        Initialise la connexion au terminal MT5 avec retry.
        Retourne True si connecte, False apres epuisement des tentatives.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"MT5 : tentative de connexion {attempt}/{MAX_RETRIES}...")

            # Etape 1 : initialiser le package MT5
            init_ok = await self._run_blocking(mt5.initialize)
            if not init_ok:
                error = await self._run_blocking(mt5.last_error)
                logger.warning(
                    f"MT5 init echec (tentative {attempt}): {error}"
                )
                await asyncio.sleep(2)
                continue

            # Etape 2 : se connecter au compte
            login_ok = await self._run_blocking(
                mt5.login, MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER
            )
            if not login_ok:
                error = await self._run_blocking(mt5.last_error)
                logger.warning(
                    f"MT5 login echec (tentative {attempt}): {error}"
                )
                await self._run_blocking(mt5.shutdown)
                await asyncio.sleep(2)
                continue

            self._initialized = True
            account_info = await self.get_account_info()
            logger.info(
                f"MT5 connecte : compte {account_info.get('login')} "
                f"sur {account_info.get('server')} "
                f"(solde: {account_info.get('balance', 0):.2f} {account_info.get('currency', '')})"
            )
            return True

        logger.error("MT5 : echec de connexion apres %d tentatives", MAX_RETRIES)
        return False

    async def check_connection(self) -> bool:
        """
        Verifie que la connexion est toujours active.
        Reconnecte automatiquement si necessaire.
        """
        if not self._initialized:
            return await self.initialize()

        terminal_info = await self._run_blocking(mt5.terminal_info)
        if terminal_info is None:
            logger.warning("MT5 : terminal deconnecte, reconnexion...")
            self._initialized = False
            return await self.initialize()

        return True

    async def shutdown(self) -> None:
        """Arret propre de la connexion MT5."""
        if self._initialized:
            logger.info("MT5 : arret de la connexion...")
            await self._run_blocking(mt5.shutdown)
            self._initialized = False

    @property
    def is_connected(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Informations du compte
    # ------------------------------------------------------------------

    async def get_account_info(self) -> dict:
        """
        Retourne les informations du compte :
        balance, equity, margin, free_margin, leverage, etc.
        """
        info = await self._run_blocking(mt5.account_info)
        if info is None:
            error = await self._run_blocking(mt5.last_error)
            raise MT5Error(f"Impossible d'obtenir les infos du compte : {error}")

        return {
            "login": info.login,
            "name": info.name,
            "server": info.server,
            "currency": info.currency,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "leverage": info.leverage,
            "margin_level": info.margin_level if hasattr(info, "margin_level") else None,
        }

    # ------------------------------------------------------------------
    # Positions ouvertes
    # ------------------------------------------------------------------

    async def get_positions(self, symbol: Optional[str] = None) -> list[dict]:
        """
        Retourne la liste des positions ouvertes.
        Filtre par symbole si specifie.
        """
        if symbol:
            positions = await self._run_blocking(mt5.positions_get, symbol=symbol)
        else:
            positions = await self._run_blocking(mt5.positions_get)

        if positions is None:
            return []

        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "commission": p.commission if hasattr(p, "commission") else 0.0,
                "comment": p.comment,
                "time": p.time,
                "identifier": p.identifier,
            })
        return result

    # ------------------------------------------------------------------
    # Prix et donnees de marche
    # ------------------------------------------------------------------

    async def get_current_price(self, symbol: str) -> dict:
        """Retourne le bid et ask actuels pour un symbole."""
        tick = await self._run_blocking(mt5.symbol_info_tick, symbol)
        if tick is None:
            error = await self._run_blocking(mt5.last_error)
            raise MT5Error(f"Impossible d'obtenir le prix pour {symbol} : {error}")

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": (tick.ask - tick.bid) if tick.bid > 0 else 0,
            "time": tick.time,
        }

    async def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Retourne les informations detaillees d'un symbole."""
        info = await self._run_blocking(mt5.symbol_info, symbol)
        if info is None:
            return None

        return {
            "symbol": info.name,
            "digits": info.digits,
            "spread": info.spread,
            "trade_mode": info.trade_mode,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "point": info.point,
            "trade_tick_size": info.trade_tick_size,
            "bid": info.bid,
            "ask": info.ask,
        }

    async def get_rates(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 100,
    ) -> Optional[list]:
        """
        Recupere les donnees OHLCV pour un symbole.
        timeframe : "M1", "M5", "M15", "M30", "H1", "H4", "D1"
        Retourne une liste de rates MT5 (objets avec open, high, low, close, tick_volume, spread, real_volume).
        """
        tf = getattr(mt5, f"TIMEFRAME_{timeframe}", mt5.TIMEFRAME_M5)
        rates = await self._run_blocking(
            mt5.copy_rates_from_pos, symbol, tf, 0, count
        )
        return rates

    # ------------------------------------------------------------------
    # Execution d'ordres
    # ------------------------------------------------------------------

    async def open_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "MT5 AI Bot",
    ) -> dict:
        """
        Ouvre une position au marche.

        Args:
            symbol: Symbole (ex: EURUSD)
            order_type: "buy" ou "sell"
            volume: Volume en lots
            sl: Stop Loss en prix absolu (optionnel)
            tp: Take Profit en prix absolu (optionnel)
            comment: Commentaire sur la position

        Returns:
            dict: {"success": bool, "ticket": int, "volume": float, "price": float,
                   "error": str (si echec), "retcode": int}
        """
        tick = await self.get_current_price(symbol)
        price = tick["ask"] if order_type == "buy" else tick["bid"]

        mt5_type = mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "deviation": DEVIATION_PIPS,
            "magic": MAGIC_NUMBER,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        result = await self._run_blocking(mt5.order_send, request)
        return self._parse_result(result, request)

    async def close_position(
        self,
        ticket: int,
    ) -> dict:
        """
        Ferme une position existante par son numero de ticket.

        Returns:
            dict: {"success": bool, "ticket": int, "error": str (si echec)}
        """
        # Recuperer les infos de la position
        position = await self._run_blocking(mt5.positions_get, ticket=ticket)
        if position is None or len(position) == 0:
            return {"success": False, "error": f"Position ticket {ticket} introuvable"}

        pos = position[0]
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type

        # Determiner le type oppose et le prix de fermeture
        tick = await self.get_current_price(symbol)
        if pos_type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = tick["bid"]
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = tick["ask"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": DEVIATION_PIPS,
            "magic": MAGIC_NUMBER,
            "comment": "Close by MT5 AI Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = await self._run_blocking(mt5.order_send, request)
        parsed = self._parse_result(result, request)
        if parsed["success"]:
            parsed["closed_symbol"] = symbol
            parsed["closed_volume"] = volume
        return parsed

    async def close_all_positions(self, symbol: Optional[str] = None) -> dict:
        """
        Ferme toutes les positions ouvertes, ou seulement celles d'un symbole.

        Returns:
            dict: {"success": bool, "closed": int, "errors": list[str]}
        """
        positions = await self.get_positions(symbol=symbol)
        if not positions:
            return {"success": True, "closed": 0, "errors": []}

        closed = 0
        errors = []

        for pos in positions:
            result = await self.close_position(pos["ticket"])
            if result["success"]:
                closed += 1
                logger.info(
                    f"Position fermee : ticket {pos['ticket']} "
                    f"({pos['symbol']} {pos['type']})"
                )
            else:
                errors.append(f"Ticket {pos['ticket']}: {result.get('error', 'Inconnu')}")
                logger.warning(
                    f"Echec fermeture position {pos['ticket']}: "
                    f"{result.get('error', 'Inconnu')}"
                )

        return {
            "success": len(errors) == 0,
            "closed": closed,
            "errors": errors,
        }

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict:
        """
        Modifie le Stop Loss et/ou Take Profit d'une position existante.

        Returns:
            dict: {"success": bool, "ticket": int, "error": str (si echec)}
        """
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
        }

        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        result = await self._run_blocking(mt5.order_send, request)
        return self._parse_result(result, request)

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    async def _run_blocking(self, func, *args, **kwargs):
        """
        Execute une fonction Python bloquante dans un thread separe
        pour ne pas bloquer l'event loop asyncio.
        """
        return await self._loop.run_in_executor(
            None,
            lambda: func(*args, **kwargs),
        )

    def _parse_result(self, result, request: dict) -> dict:
        """
        Normalise le resultat de mt5.order_send() en dictionnaire.
        Gere les differents codes de retour MT5.
        """
        if result is None:
            error = mt5.last_error()
            return {
                "success": False,
                "retcode": error[0] if error else -1,
                "error": f"Erreur MT5 : {error}",
            }

        retcode = result.retcode

        if retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "success": True,
                "ticket": result.order,
                "volume": request.get("volume", 0),
                "price": request.get("price", 0),
                "retcode": retcode,
                "comment": result.comment,
            }

        # Mapping des codes d'erreur courants
        error_messages = {
            mt5.TRADE_RETCODE_NO_CONNECTION: "Pas de connexion au serveur de trading",
            mt5.TRADE_RETCODE_REQUOTE: "Requote - le prix a change, reessayez",
            mt5.TRADE_RETCODE_TOO_MANY_REQUESTS: "Trop de requetes, attendez un instant",
            mt5.TRADE_RETCODE_INVALID_VOLUME: "Volume invalide",
            mt5.TRADE_RETCODE_INVALID_PRICE: "Prix invalide",
            mt5.TRADE_RETCODE_INVALID_STOPS: "SL/TP invalides",
            mt5.TRADE_RETCODE_LIMIT_ORDERS: "Limite d'ordres atteinte",
            mt5.TRADE_RETCODE_MARKET_CLOSED: "Marche ferme",
            mt5.TRADE_RETCODE_NOT_ENOUGH_MONEY: "Marge insuffisante",
            mt5.TRADE_RETCODE_TRADE_DISABLED: "Trading desactive sur ce compte",
        }

        error_msg = error_messages.get(
            retcode,
            f"Erreur inconnue : {result.comment} (code {retcode})"
        )

        logger.warning(
            f"MT5 order_send echec : retcode={retcode} "
            f"comment={result.comment} request={request}"
        )

        return {
            "success": False,
            "retcode": retcode,
            "error": error_msg,
        }
