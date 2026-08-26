"""
Client MetaTrader 5 asynchrone.
Tous les appels bloquants MT5 sont executes via run_in_executor()
pour ne pas bloquer l'event loop asyncio.
"""

import atexit
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional, Any

try:
    import MetaTrader5 as mt5
except ModuleNotFoundError:
    mt5 = None

from config import (
    MT5_LOGIN,
    MT5_PASSWORD,
    MT5_SERVER,
    MAX_RETRIES,
    DEVIATION_PIPS,
    MAGIC_NUMBER,
    TIMEFRAME_MAP,
    TRADING_MODE,
    VALID_TRADING_MODES,
)
from cycle_result import (
    Blocker,
    MIN_CLOSED_BARS,
    STALE_TICK_SECONDS,
)

logger = logging.getLogger(__name__)

_EXECUTOR_LOCK = threading.Lock()
_SHARED_EXECUTOR: Optional[ThreadPoolExecutor] = None


def _get_shared_executor() -> ThreadPoolExecutor:
    global _SHARED_EXECUTOR
    with _EXECUTOR_LOCK:
        if _SHARED_EXECUTOR is None:
            _SHARED_EXECUTOR = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="mt5-client",
            )
        return _SHARED_EXECUTOR


def _shutdown_shared_executor() -> None:
    global _SHARED_EXECUTOR
    with _EXECUTOR_LOCK:
        executor = _SHARED_EXECUTOR
        _SHARED_EXECUTOR = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)


atexit.register(_shutdown_shared_executor)


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

    def __init__(self, mt5_api=None, trading_mode: str = TRADING_MODE):
        normalized_mode = trading_mode.lower()
        if normalized_mode not in VALID_TRADING_MODES:
            raise ValueError(f"Mode de trading invalide: {trading_mode!r}")

        self._mt5 = mt5_api if mt5_api is not None else mt5
        self._mutation_lock = threading.RLock()
        self._trading_mode = normalized_mode
        self._trading_armed: bool = False
        self._initialized: bool = False

    @staticmethod
    def shutdown_shared_executor() -> None:
        """Ferme l'executant MT5 global; un prochain appel le recreera."""
        _shutdown_shared_executor()

    def arm_trading(self) -> None:
        """Arme les mutations en memoire pour cette instance uniquement."""
        with self._mutation_lock:
            self._trading_armed = True

    def disarm_trading(self) -> None:
        """Desarme immediatement toutes les mutations."""
        with self._mutation_lock:
            self._trading_armed = False

    @property
    def is_trading_armed(self) -> bool:
        with self._mutation_lock:
            return self._trading_armed

    @property
    def trading_mode(self) -> str:
        with self._mutation_lock:
            return self._trading_mode

    @trading_mode.setter
    def trading_mode(self, value: str) -> None:
        normalized_mode = value.lower()
        if normalized_mode not in VALID_TRADING_MODES:
            raise ValueError(f"Mode de trading invalide: {value!r}")
        with self._mutation_lock:
            self._trading_mode = normalized_mode

    def _require_api(self):
        if self._mt5 is None:
            raise MT5Error(
                "MetaTrader5 indisponible: utilisez Windows natif ou injectez une API de test"
            )
        return self._mt5

    async def _mutation_refusal(self) -> Optional[dict]:
        """Retourne un refus, ou None si la mutation est explicitement autorisee."""
        with self._mutation_lock:
            trading_mode = self._trading_mode
            trading_armed = self._trading_armed

        if trading_mode == "live":
            return {
                "success": False,
                "error": "Mutation MT5 refusee: mode live reconnu mais non implemente.",
            }
        if trading_mode != "demo":
            return {
                "success": False,
                "error": f"Mutation MT5 refusee: mode {trading_mode} en lecture seule.",
            }
        if not trading_armed:
            return {
                "success": False,
                "error": "Mutation MT5 refusee: armement explicite requis.",
            }

        try:
            api = self._require_api()
        except MT5Error as exc:
            return {"success": False, "error": f"Mutation MT5 refusee: {exc}"}

        account = await self._run_blocking(api.account_info)
        if account is None:
            return {
                "success": False,
                "error": "Mutation MT5 refusee: compte MT5 non confirme.",
            }
        if getattr(account, "trade_mode", None) != api.ACCOUNT_TRADE_MODE_DEMO:
            return {
                "success": False,
                "error": "Mutation MT5 refusee: le compte confirme n'est pas un compte demo.",
            }
        return None

    def _guarded_order_send(self, request: dict) -> tuple[Optional[dict], Any, Any]:
        """Valide l'etat final et envoie atomiquement dans le thread MT5."""
        with self._mutation_lock:
            if self._trading_mode == "live":
                return (
                    {
                        "success": False,
                        "error": (
                            "Mutation MT5 refusee: mode live reconnu mais non implemente."
                        ),
                    },
                    None,
                    None,
                )
            if self._trading_mode != "demo":
                return (
                    {
                        "success": False,
                        "error": (
                            f"Mutation MT5 refusee: mode {self._trading_mode} "
                            "en lecture seule."
                        ),
                    },
                    None,
                    None,
                )
            if not self._trading_armed:
                return (
                    {
                        "success": False,
                        "error": "Mutation MT5 refusee: armement explicite requis.",
                    },
                    None,
                    None,
                )

            api = self._require_api()
            account = api.account_info()
            if account is None:
                return (
                    {
                        "success": False,
                        "error": "Mutation MT5 refusee: compte MT5 non confirme.",
                    },
                    None,
                    None,
                )
            if getattr(account, "trade_mode", None) != api.ACCOUNT_TRADE_MODE_DEMO:
                return (
                    {
                        "success": False,
                        "error": (
                            "Mutation MT5 refusee: le compte confirme "
                            "n'est pas un compte demo."
                        ),
                    },
                    None,
                    None,
                )

            result = api.order_send(request)
            last_error = api.last_error() if result is None else None
            return None, result, last_error

    async def _send_guarded_order(self, request: dict) -> dict:
        refusal, result, last_error = await self._run_blocking(
            self._guarded_order_send,
            request,
        )
        if refusal is not None:
            return refusal
        return self._parse_result(result, request, last_error)

    # ------------------------------------------------------------------
    # Cycle de vie de la connexion
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """
        Initialise la connexion au terminal MT5 avec retry.
        Retourne True si connecte, False apres epuisement des tentatives.
        """
        if self._mt5 is None:
            logger.warning(
                "MetaTrader5 indisponible sur ce runtime; connexion MT5 desactivee"
            )
            return False

        api = self._mt5
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"MT5 : tentative de connexion {attempt}/{MAX_RETRIES}...")

            # Etape 1 : initialiser le package MT5
            init_ok = await self._run_blocking(api.initialize)
            if not init_ok:
                error = await self._run_blocking(api.last_error)
                logger.warning(
                    f"MT5 init echec (tentative {attempt}): {error}"
                )
                await asyncio.sleep(2)
                continue

            # Etape 2 : se connecter au compte
            login_ok = await self._run_blocking(
                api.login, MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER
            )
            if not login_ok:
                error = await self._run_blocking(api.last_error)
                logger.warning(
                    f"MT5 login echec (tentative {attempt}): {error}"
                )
                await self._run_blocking(api.shutdown)
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

        api = self._require_api()
        terminal_info = await self._run_blocking(api.terminal_info)
        if terminal_info is None:
            logger.warning("MT5 : terminal deconnecte, reconnexion...")
            self._initialized = False
            return await self.initialize()

        return True

    async def shutdown(self) -> None:
        """Arret propre de la connexion MT5."""
        if self._initialized:
            logger.info("MT5 : arret de la connexion...")
            api = self._require_api()
            await self._run_blocking(api.shutdown)
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
        api = self._require_api()
        info = await self._run_blocking(api.account_info)
        if info is None:
            error = await self._run_blocking(api.last_error)
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
            "trade_mode": info.trade_mode if hasattr(info, "trade_mode") else None,
        }

    # ------------------------------------------------------------------
    # Positions ouvertes
    # ------------------------------------------------------------------

    async def get_positions(self, symbol: Optional[str] = None) -> list[dict]:
        """
        Retourne la liste des positions ouvertes.
        Filtre par symbole si specifie.
        """
        api = self._require_api()
        if symbol:
            positions = await self._run_blocking(api.positions_get, symbol=symbol)
        else:
            positions = await self._run_blocking(api.positions_get)

        if positions is None:
            return []

        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == api.POSITION_TYPE_BUY else "SELL",
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

    async def get_closed_profit(self, ticket: int) -> Optional[float]:
        """Retourne le profit du dernier deal de fermeture des dernieres 24 h."""
        api = self._require_api()
        to_date = datetime.now()
        deals = await self._run_blocking(
            api.history_deals_get,
            to_date - timedelta(days=1),
            to_date,
            position=ticket,
        )
        if not deals:
            return None
        for deal in reversed(deals):
            if deal.entry == api.DEAL_ENTRY_OUT:
                return deal.profit
        return None

    # ------------------------------------------------------------------
    # Prix et donnees de marche
    # ------------------------------------------------------------------

    async def get_current_price(self, symbol: str) -> dict:
        """Retourne le bid et ask actuels pour un symbole."""
        api = self._require_api()
        tick = await self._run_blocking(api.symbol_info_tick, symbol)
        if tick is None:
            error = await self._run_blocking(api.last_error)
            raise MT5Error(f"Impossible d'obtenir le prix pour {symbol} : {error}")

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": (tick.ask - tick.bid) if tick.bid > 0 else 0,
            "time": tick.time,
            "time_msc": getattr(tick, "time_msc", tick.time * 1000),
        }

    async def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Retourne les informations detaillees d'un symbole."""
        api = self._require_api()
        info = await self._run_blocking(api.symbol_info, symbol)
        if info is None:
            return None

        return {
            "symbol": info.name,
            "visible": getattr(info, "visible", True),
            "select": getattr(info, "select", True),
            "digits": info.digits,
            "spread": info.spread,
            "trade_mode": info.trade_mode,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "volume_limit": getattr(info, "volume_limit", None),
            "point": info.point,
            "trade_tick_size": info.trade_tick_size,
            "trade_tick_value": getattr(info, "trade_tick_value", None),
            "trade_tick_value_profit": getattr(info, "trade_tick_value_profit", None),
            "trade_tick_value_loss": getattr(info, "trade_tick_value_loss", None),
            "trade_contract_size": getattr(info, "trade_contract_size", None),
            "trade_calc_mode": getattr(info, "trade_calc_mode", None),
            "currency_profit": getattr(info, "currency_profit", None),
            "currency_margin": getattr(info, "currency_margin", None),
            "trade_stops_level": getattr(info, "trade_stops_level", None),
            "trade_freeze_level": getattr(info, "trade_freeze_level", None),
            "filling_mode": getattr(info, "filling_mode", None),
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
        api = self._require_api()
        tf = getattr(api, f"TIMEFRAME_{timeframe}", api.TIMEFRAME_M5)
        rates = await self._run_blocking(
            api.copy_rates_from_pos, symbol, tf, 0, count
        )
        return rates

    async def get_closed_rates(
        self,
        symbol: str,
        timeframe: str = "M5",
        count: int = 100,
    ) -> Optional[list]:
        """OHLCV des bougies deja cloturees (ignore la bougie en formation)."""
        api = self._require_api()
        tf = getattr(api, f"TIMEFRAME_{timeframe}", api.TIMEFRAME_M5)
        return await self._run_blocking(
            api.copy_rates_from_pos, symbol, tf, 1, count
        )

    async def resolve_symbol(self, requested: str) -> dict:
        """Resout un symbole broker. N'en choisit jamais un si le match est ambigu."""
        api = self._require_api()
        requested_upper = requested.upper()
        listing = await self._run_blocking(api.symbols_get)
        names = [item.name for item in listing] if listing else []
        exact = [name for name in names if name.upper() == requested_upper]
        if len(exact) == 1:
            return {
                "requested": requested,
                "resolved": exact[0],
                "candidates": exact,
                "ambiguous": False,
            }
        prefixed = [
            name for name in names if name.upper().startswith(requested_upper)
        ]
        if len(prefixed) == 1:
            return {
                "requested": requested,
                "resolved": prefixed[0],
                "candidates": prefixed,
                "ambiguous": False,
            }
        return {
            "requested": requested,
            "resolved": None,
            "candidates": prefixed or exact,
            "ambiguous": len(prefixed) > 1,
        }

    async def check_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict:
        """Valide un ordre via order_check, sans jamais appeler order_send."""
        api = self._require_api()
        tick = await self.get_current_price(symbol)
        price = tick["ask"] if order_type == "buy" else tick["bid"]
        mt5_type = api.ORDER_TYPE_BUY if order_type == "buy" else api.ORDER_TYPE_SELL
        request = {
            "action": api.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "deviation": DEVIATION_PIPS,
            "magic": MAGIC_NUMBER,
            "comment": "preflight-check",
            "type_time": api.ORDER_TIME_GTC,
            "type_filling": api.ORDER_FILLING_IOC,
        }
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        result = await self._run_blocking(api.order_check, request)
        if result is None:
            last_error = await self._run_blocking(api.last_error)
            return {
                "ok": False,
                "called": True,
                "retcode": last_error[0] if last_error else -1,
                "comment": str(last_error),
            }
        retcode = result.retcode
        return {
            "ok": retcode == api.TRADE_RETCODE_DONE,
            "called": True,
            "retcode": retcode,
            "comment": getattr(result, "comment", ""),
        }

    async def preflight(self, requested_symbol: str) -> dict:
        """Rapport machine-lisible, sans secret, avant toute mutation."""
        blockers: list[str] = []
        report: dict = {
            "ok": False,
            "blockers": blockers,
            "account": {},
            "terminal": {},
            "symbol": {},
            "specs": {},
            "rates": {},
            "tick": {},
            "order_check": {"called": False, "ok": False},
        }
        if self._mt5 is None:
            blockers.append(Blocker.MT5_UNAVAILABLE.value)
            return report

        try:
            api = self._require_api()
            terminal = await self._run_blocking(api.terminal_info)
            account = await self._run_blocking(api.account_info)
        except MT5Error as exc:
            blockers.append(Blocker.MT5_UNAVAILABLE.value)
            report["error"] = str(exc)
            return report

        report["terminal"] = {
            "connected": bool(getattr(terminal, "connected", False)) if terminal else False,
            "trade_allowed": bool(getattr(terminal, "trade_allowed", False)) if terminal else False,
            "name": getattr(terminal, "name", None) if terminal else None,
        }
        if terminal is None or not report["terminal"]["trade_allowed"]:
            blockers.append(Blocker.PREFLIGHT_FAILED.value)

        if account is None:
            blockers.append(Blocker.PREFLIGHT_FAILED.value)
            report["account"] = {"trade_mode": "unknown"}
        else:
            trade_mode = getattr(account, "trade_mode", None)
            label = "unknown"
            if trade_mode == api.ACCOUNT_TRADE_MODE_DEMO:
                label = "demo"
            elif trade_mode == getattr(api, "ACCOUNT_TRADE_MODE_REAL", object()):
                label = "real"
            report["account"] = {
                "trade_mode": label,
                "currency": getattr(account, "currency", None),
                "leverage": getattr(account, "leverage", None),
                "margin_free": getattr(account, "margin_free", None),
            }
            if label != "demo":
                blockers.append(Blocker.PREFLIGHT_FAILED.value)

        try:
            resolved = await self.resolve_symbol(requested_symbol)
        except MT5Error:
            blockers.append(Blocker.SYMBOL_UNRESOLVED.value)
            return report

        report["symbol"] = resolved
        symbol = resolved.get("resolved")
        if not symbol:
            blockers.append(Blocker.SYMBOL_UNRESOLVED.value)
            report["ok"] = False
            report["blockers"] = list(dict.fromkeys(blockers))
            return report

        await self._run_blocking(api.symbol_select, symbol, True)
        specs = await self.get_symbol_info(symbol)
        report["specs"] = specs or {}
        if specs is None:
            blockers.append(Blocker.SYMBOL_UNRESOLVED.value)

        try:
            tick = await self.get_current_price(symbol)
            report["tick"] = {
                "bid": tick["bid"],
                "ask": tick["ask"],
                "spread": tick["spread"],
                "age_seconds": int(datetime.now().timestamp()) - int(tick.get("time") or 0),
            }
            if report["tick"]["age_seconds"] > STALE_TICK_SECONDS:
                blockers.append(Blocker.STALE_TICK.value)
        except MT5Error:
            blockers.append(Blocker.STALE_TICK.value)

        m5 = await self.get_closed_rates(symbol, "M5", 200)
        m15 = await self.get_closed_rates(symbol, "M15", 200)
        m5_count = len(m5) if m5 is not None else 0
        m15_count = len(m15) if m15 is not None else 0
        report["rates"] = {"m5_closed": m5_count, "m15_closed": m15_count}
        if m5_count < MIN_CLOSED_BARS or m15_count < MIN_CLOSED_BARS:
            blockers.append(Blocker.INSUFFICIENT_CLOSED_BARS.value)

        if specs is not None:
            bid = float(specs.get("bid") or 0)
            check = await self.check_order(
                symbol,
                "buy",
                float(specs.get("volume_min") or 0.01),
                sl=bid - 10.0 if bid else None,
                tp=bid + 20.0 if bid else None,
            )
            report["order_check"] = check
            if not check.get("ok"):
                blockers.append(Blocker.ORDER_CHECK_REJECTED.value)

        report["blockers"] = list(dict.fromkeys(blockers))
        report["ok"] = len(report["blockers"]) == 0
        return report

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
        refusal = await self._mutation_refusal()
        if refusal is not None:
            return refusal

        api = self._require_api()
        tick = await self.get_current_price(symbol)
        price = tick["ask"] if order_type == "buy" else tick["bid"]

        mt5_type = api.ORDER_TYPE_BUY if order_type == "buy" else api.ORDER_TYPE_SELL

        request = {
            "action": api.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "deviation": DEVIATION_PIPS,
            "magic": MAGIC_NUMBER,
            "comment": comment,
            "type_time": api.ORDER_TIME_GTC,
            "type_filling": api.ORDER_FILLING_IOC,
        }

        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        return await self._send_guarded_order(request)

    async def close_position(
        self,
        ticket: int,
    ) -> dict:
        """
        Ferme une position existante par son numero de ticket.

        Returns:
            dict: {"success": bool, "ticket": int, "error": str (si echec)}
        """
        refusal = await self._mutation_refusal()
        if refusal is not None:
            return refusal

        api = self._require_api()
        # Recuperer les infos de la position
        position = await self._run_blocking(api.positions_get, ticket=ticket)
        if position is None or len(position) == 0:
            return {"success": False, "error": f"Position ticket {ticket} introuvable"}

        pos = position[0]
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type

        # Determiner le type oppose et le prix de fermeture
        tick = await self.get_current_price(symbol)
        if pos_type == api.POSITION_TYPE_BUY:
            close_type = api.ORDER_TYPE_SELL
            price = tick["bid"]
        else:
            close_type = api.ORDER_TYPE_BUY
            price = tick["ask"]

        request = {
            "action": api.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": DEVIATION_PIPS,
            "magic": MAGIC_NUMBER,
            "comment": "Close by MT5 AI Bot",
            "type_time": api.ORDER_TIME_GTC,
            "type_filling": api.ORDER_FILLING_IOC,
        }

        parsed = await self._send_guarded_order(request)
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
        refusal = await self._mutation_refusal()
        if refusal is not None:
            return refusal

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
        refusal = await self._mutation_refusal()
        if refusal is not None:
            return refusal

        api = self._require_api()
        request = {
            "action": api.TRADE_ACTION_SLTP,
            "position": ticket,
        }

        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        return await self._send_guarded_order(request)

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    async def _run_blocking(self, func, *args, **kwargs):
        """
        Execute et serialise les appels MT5 dans un thread dedie.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _get_shared_executor(),
            lambda: func(*args, **kwargs),
        )

    def _parse_result(self, result, request: dict, last_error=None) -> dict:
        """
        Normalise le resultat de mt5.order_send() en dictionnaire.
        Gere les differents codes de retour MT5.
        """
        if result is None:
            return {
                "success": False,
                "retcode": last_error[0] if last_error else -1,
                "error": f"Erreur MT5 : {last_error}",
            }

        api = self._require_api()
        retcode = result.retcode

        if retcode == api.TRADE_RETCODE_DONE:
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
            api.TRADE_RETCODE_NO_CONNECTION: "Pas de connexion au serveur de trading",
            api.TRADE_RETCODE_REQUOTE: "Requote - le prix a change, reessayez",
            api.TRADE_RETCODE_TOO_MANY_REQUESTS: "Trop de requetes, attendez un instant",
            api.TRADE_RETCODE_INVALID_VOLUME: "Volume invalide",
            api.TRADE_RETCODE_INVALID_PRICE: "Prix invalide",
            api.TRADE_RETCODE_INVALID_STOPS: "SL/TP invalides",
            api.TRADE_RETCODE_LIMIT_ORDERS: "Limite d'ordres atteinte",
            api.TRADE_RETCODE_MARKET_CLOSED: "Marche ferme",
            api.TRADE_RETCODE_NOT_ENOUGH_MONEY: "Marge insuffisante",
            api.TRADE_RETCODE_TRADE_DISABLED: "Trading desactive sur ce compte",
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
