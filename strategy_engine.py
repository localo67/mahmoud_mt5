"""
Orchestrateur principal — IA-first avec self-reflection, trailing stop,
verification de position, P&L tracking reel, retry, heartbeat, et rapport quotidien.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from telegram.ext import Application

from config import (
    SYMBOL,
    VOLUME,
    CANDLE_COUNT,
    NY_START_HOUR,
    NY_END_HOUR,
    AI_MIN_CONFIDENCE,
    TRAILING_ENABLED,
    TRAILING_ACTIVATE_PIPS,
    TRAILING_DISTANCE_PIPS,
    DAILY_REPORT_HOUR,
    MAX_SPREAD_POINTS,
)
from strategies.base import Signal
from risk_manager import RiskManager
from news_filter import NewsFilter
from news_collector import NewsCollector
from fmp_collector import FMPCollector
from ai_trader import AITrader

logger = logging.getLogger(__name__)

PIP_VALUE = 0.01  # 1 pip XAUUSD
ORDER_RETRIES = 2
ORDER_RETRY_DELAY = 2  # secondes
HEARTBEAT_INTERVAL = 30  # secondes


# Helper: extraire les champs d'un rate MT5 (tuple ou objet, compatible Windows/Linux)
def _ro(r): return r.open if hasattr(r, 'open') else r[1]   # open
def _rh(r): return r.high  if hasattr(r, 'high')  else r[2]  # high
def _rl(r): return r.low   if hasattr(r, 'low')   else r[3]  # low
def _rc(r): return r.close if hasattr(r, 'close') else r[4]  # close
def _rt(r): return r.tick_volume if hasattr(r, 'tick_volume') else r[5]  # tick_volume
def _rtime(r): return r.time if hasattr(r, 'time') else r[0]  # time


class StrategyEngine:
    """Orchestrateur IA-first avec toutes les ameliorations."""

    def __init__(
        self,
        application: Application,
        mt5_client,
        risk_manager: RiskManager,
        news_filter: NewsFilter,
        news_collector: NewsCollector,
        fmp_collector: FMPCollector,
        ai_trader: AITrader,
        strategies: list,
    ):
        self.app = application
        self.mt5 = mt5_client
        self.risk_mgr = risk_manager
        self.news_filter = news_filter
        self.news_collector = news_collector
        self.fmp = fmp_collector
        self.ai = ai_trader
        self.strategies = strategies
        self.chat_id: Optional[int] = None
        self.enabled: bool = True  # /auto on/off

        self._last_candle_time: int = 0
        self._traded_this_candle: bool = False
        self._trade_history: list[dict] = []
        self._known_tickets: set[int] = set()
        self._last_heartbeat: float = 0.0
        self._consecutive_errors: int = 0
        self._emergency_stop: bool = False

    async def run(self) -> None:
        """Boucle principale."""
        logger.info(
            f"StrategyEngine: IA-first, {len(self.strategies)} strategies, "
            f"trailing={'ON' if TRAILING_ENABLED else 'OFF'}, retries={ORDER_RETRIES}"
        )
        report_task = asyncio.create_task(self._daily_report_scheduler())

        try:
            while True:
                try:
                    await asyncio.sleep(10)

                    if not self.enabled:
                        continue

                    # Emergency stop
                    if self._emergency_stop:
                        continue

                    # Heartbeat MT5
                    if not await self._heartbeat():
                        continue

                    # Maintenance: P&L reel + trailing
                    await self._maintenance_cycle()

                    # Donnees
                    rates_m5 = await self.mt5.get_rates(SYMBOL, "M5", CANDLE_COUNT)
                    rates_m15 = await self.mt5.get_rates(SYMBOL, "M15", CANDLE_COUNT)
                    price = await self.mt5.get_current_price(SYMBOL)

                    if rates_m5 is None or rates_m15 is None or len(rates_m5) < 50:
                        continue

                    # Nouvelle bougie ? L'IA ne s'appelle QUE sur nouvelle bougie M5 (economise API)
                    current_candle_time = self._get_candle_time(rates_m5[-1])
                    is_new_candle = current_candle_time != self._last_candle_time
                    if is_new_candle:
                        self._last_candle_time = current_candle_time
                        self._traded_this_candle = False

                    # Skip si pas nouvelle bougie — maintenance uniquement, pas d'appel IA
                    if not is_new_candle or self._traded_this_candle:
                        continue

                    logger.info(
                        f"StrategyEngine: nouvelle bougie M5 — "
                        f"bid={price['bid']:.2f} spread={price['spread']:.3f}"
                    )

                    # Filtres
                    if not self._is_ny_session():
                        continue
                    if await self.news_filter.is_news_time():
                        continue
                    allowed, reason = self.risk_mgr.check_trade_allowed()
                    if not allowed:
                        continue

                    # Spread filter
                    if not self._check_spread(price):
                        continue

                    # Verifier marge disponible
                    if not await self._check_margin():
                        continue

                    # Verifier si deja une position XAUUSD
                    xau_positions = await self.mt5.get_positions(symbol=SYMBOL)
                    if xau_positions:
                        continue

                    # Evaluer les strategies (guidelines)
                    strategy_signals = []
                    for strategy in self.strategies:
                        try:
                            signal: Optional[Signal] = await strategy.evaluate(
                                rates_m5, rates_m15, price
                            )
                            s = {
                                "name": strategy.name,
                                "direction": signal.direction.upper() if signal else "NONE",
                                "sl_price": signal.sl_price if signal else None,
                                "tp_price": signal.tp_price if signal else None,
                            }
                        except Exception as e:
                            logger.error(f"StrategyEngine: {strategy.name} error — {e}")
                            s = {"name": strategy.name, "direction": "NONE", "sl_price": None, "tp_price": None}
                        strategy_signals.append(s)

                    # Contexte pour l'IA
                    closes_m5 = np.array([_rc(r) for r in rates_m5])
                    closes_m15 = np.array([_rc(r) for r in rates_m15])

                    dxy_price = None
                    try:
                        dxy_tick = await self.mt5.get_current_price("USDX")
                        if dxy_tick:
                            dxy_price = dxy_tick.get("bid")
                    except Exception:
                        pass

                    tick_vol = sum(_rt(r) for r in rates_m5[-5:]) if rates_m5 is not None and len(rates_m5) > 0 else 0
                    market_data = self._build_market_data(rates_m5, closes_m5, closes_m15, price, dxy_price, tick_vol)

                    headlines = await self.news_collector.get_headlines(5)
                    headlines = await self.news_collector.analyze_sentiment(headlines)
                    news_text = self.news_collector.format_for_ai(headlines)

                    # FMP: forex news, prix or, taux
                    fmp_news = await self.fmp.get_forex_news(5)
                    gold_quote = await self.fmp.get_gold_price()
                    treasury = await self.fmp.get_treasury_rates()
                    fmp_text = self.fmp.format_for_ai(fmp_news, gold_quote, treasury)

                    # Fusionner les sources
                    combined_news = f"{news_text}\n\n[FOREX NEWS + MACRO FMP]\n{fmp_text}"

                    risk_context = self.risk_mgr.get_context_for_ai()
                    history_text = self._format_trade_history()

                    # Decision IA
                    decision = await self.ai.decide(
                        market_data=market_data,
                        strategy_signals=strategy_signals,
                        news_formatted=combined_news,
                        risk_context=risk_context,
                        trade_history=history_text,
                    )

                    if decision["action"] == "WAIT":
                        continue
                    if decision["confidence"] < AI_MIN_CONFIDENCE:
                        continue

                    allowed, reason = self.risk_mgr.check_trade_allowed()
                    if not allowed:
                        continue

                    # Verifier encore une fois avant d'executer
                    xau_positions = await self.mt5.get_positions(symbol=SYMBOL)
                    if xau_positions:
                        continue
                    if not await self._check_margin():
                        continue

                    # Volume dynamique selon ATR et equity
                    account_info = await self.mt5.get_account_info()
                    atr_val = float(str(market_data.get("atr", "0")).replace(",", "."))
                    trade_volume = self.risk_mgr.calculate_position_size(
                        account_info["equity"], atr_val
                    )

                    # Executer avec retry
                    result = await self._execute_with_retry(decision, trade_volume)

                    if result["success"]:
                        self._traded_this_candle = True
                        ticket = result.get("ticket")
                        if ticket:
                            self._known_tickets.add(ticket)

                        self._trade_history.append({
                            "time": datetime.now(timezone.utc).strftime("%H:%M"),
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "action": decision["action"],
                            "sl": f"{decision.get('sl_price', 0) or 0:.2f}",
                            "tp": f"{decision.get('tp_price', 0) or 0:.2f}",
                            "confidence": decision.get("confidence", 0),
                            "reasoning": decision.get("reasoning", "")[:100],
                            "ticket": ticket,
                        })
                        if len(self._trade_history) > 5:
                            self._trade_history = self._trade_history[-5:]

                        self.risk_mgr.record_trade_result(0.0)
                        await self._send_alert(decision, result)

                    # Reinitialiser le compteur d'erreurs sur cycle reussi
                    self._consecutive_errors = 0

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._consecutive_errors += 1
                    logger.error(
                        f"StrategyEngine: error #{self._consecutive_errors} — {e}",
                        exc_info=True,
                    )
                    if self._consecutive_errors >= 10:
                        self._emergency_stop = True
                        logger.critical(
                            f"EMERGENCY STOP: {self._consecutive_errors} erreurs consecutives"
                        )
                        try:
                            await self._send_system_alert(
                                f"ARRET D'URGENCE — {self._consecutive_errors} erreurs consecutives. Bot bloque."
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("StrategyEngine: arret")
        finally:
            report_task.cancel()
            try:
                await report_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Heartbeat MT5
    # ------------------------------------------------------------------

    async def _heartbeat(self) -> bool:
        """Verifie la sante de MT5 avec un ping periodique."""
        now = asyncio.get_event_loop().time()
        if now - self._last_heartbeat < HEARTBEAT_INTERVAL:
            return True

        self._last_heartbeat = now
        logger.info("StrategyEngine: heartbeat MT5 OK")
        if not await self.mt5.check_connection():
            logger.error("MT5 heartbeat: connexion perdue, tentative reconnexion...")
            if not await self.mt5.initialize():
                logger.critical("MT5 heartbeat: echec reconnexion")
                await self._send_system_alert("MT5 DECONNECTE — le bot ne peut plus trader")
                return False
        return True

    @staticmethod
    def _check_spread(price: dict) -> bool:
        """Bloque le trading si le spread est trop eleve."""
        spread = price.get("spread", 0)
        spread_points = spread / PIP_VALUE  # Convertir prix en points
        if spread_points > MAX_SPREAD_POINTS:
            logger.info(f"Spread filter: spread={spread_points:.0f}pts > max={MAX_SPREAD_POINTS}pts → skip")
            return False
        return True

    async def _check_margin(self) -> bool:
        """Verifie que la marge libre est suffisante pour ouvrir une position."""
        try:
            info = await self.mt5.get_account_info()
            margin_required = info.get("margin", 0)
            free_margin = info.get("free_margin", 0)

            # Estimer la marge pour 0.01 XAUUSD (~3-10$ selon levier)
            estimated_margin = 5.0

            if free_margin < margin_required + estimated_margin:
                logger.warning(
                    f"Margin check: marge insuffisante "
                    f"(free={free_margin:.2f}, used={margin_required:.2f})"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Margin check error: {e}")
            return True  # Fail-open: on tente quand meme

    # ------------------------------------------------------------------
    # Retry sur echec d'ordre
    # ------------------------------------------------------------------

    async def _execute_with_retry(self, decision: dict, volume: float = VOLUME) -> dict:
        """Execute un ordre avec retry en cas de requote ou echec temporaire."""
        for attempt in range(1, ORDER_RETRIES + 1):
            result = await self._execute_decision(decision, volume)
            if result["success"]:
                return result

            retcode = result.get("retcode", 0)
            # Retry uniquement sur requote, trop de requetes, ou pas de connexion
            if retcode in (10004, 10014, 10015):
                logger.warning(
                    f"Order retry {attempt}/{ORDER_RETRIES}: "
                    f"retcode={retcode} — {result.get('error', '')}"
                )
                if attempt < ORDER_RETRIES:
                    await asyncio.sleep(ORDER_RETRY_DELAY)
                    # Rafraichir le prix pour le retry
                    continue
            else:
                # Erreur definitive (params invalides, pas de marge, etc.)
                break

        return result

    # ------------------------------------------------------------------
    # Maintenance: P&L reel + trailing
    # ------------------------------------------------------------------

    async def _maintenance_cycle(self) -> None:
        """Trailing stop + tracking du P&L reel des positions fermees."""
        try:
            positions = await self.mt5.get_positions(symbol=SYMBOL)

            # Trailing stop
            if TRAILING_ENABLED and positions:
                for pos in positions:
                    await self._apply_trailing_stop(pos)

            # P&L reel: detecter tickets fermes
            current_tickets = {p["ticket"] for p in positions}
            closed_tickets = self._known_tickets - current_tickets

            if closed_tickets:
                # Parcourir l'historique pour trouver les trades fermes
                for t in self._trade_history:
                    tkt = t.get("ticket")
                    if tkt and tkt in closed_tickets:
                        # Verifier le P&L via l'historique des deals MT5
                        try:
                            profit = await self._get_closed_profit(tkt)
                            if profit is not None:
                                self.risk_mgr.update_real_pnl(profit)
                                t["pnl"] = profit
                                logger.info(f"P&L reel ticket {tkt}: {profit:+.2f}$")
                        except Exception as e:
                            logger.debug(f"P&L lookup error ticket {tkt}: {e}")

            # Mettre a jour l'ensemble des tickets connus
            self._known_tickets = current_tickets

            # Mettre a jour le P&L flottant dans le risk manager
            if positions:
                floating_pnl = sum(p["profit"] for p in positions)
                # Le risk manager stocke deja daily_pnl, on ne double pas

        except Exception as e:
            logger.debug(f"Maintenance error: {e}")

    async def _get_closed_profit(self, ticket: int) -> Optional[float]:
        """Recupere le profit/perte d'une position fermee via l'historique MT5."""
        return await self.mt5.get_closed_profit(ticket)

    async def _apply_trailing_stop(self, position: dict) -> None:
        try:
            ticket = position["ticket"]
            pos_type = position["type"]
            entry = position["price_open"]
            current_sl = position["sl"]
            current_price = position["price_current"]

            if pos_type == "BUY":
                profit_pips = (current_price - entry) / PIP_VALUE
            else:
                profit_pips = (entry - current_price) / PIP_VALUE

            if profit_pips < TRAILING_ACTIVATE_PIPS:
                return

            if pos_type == "BUY":
                new_sl = current_price - (TRAILING_DISTANCE_PIPS * PIP_VALUE)
                if current_sl and new_sl <= current_sl:
                    return
            else:
                new_sl = current_price + (TRAILING_DISTANCE_PIPS * PIP_VALUE)
                if current_sl and new_sl >= current_sl:
                    return

            await self.mt5.modify_position(ticket=ticket, sl=new_sl)
            logger.info(f"Trailing: ticket {ticket} SL→{new_sl:.2f} ({profit_pips:.0f}pips)")
        except Exception as e:
            logger.debug(f"Trailing error ticket {position.get('ticket')}: {e}")

    # ------------------------------------------------------------------
    # Rapport quotidien
    # ------------------------------------------------------------------

    async def _daily_report_scheduler(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            if now.hour == DAILY_REPORT_HOUR and now.minute == 0:
                await self._send_daily_report()
                await asyncio.sleep(120)

    async def _send_daily_report(self) -> None:
        if not self.chat_id:
            return
        try:
            info = await self.mt5.get_account_info()
            positions = await self.mt5.get_positions(symbol=SYMBOL)
            risk_status = self.risk_mgr.get_status()

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_trades = [t for t in self._trade_history if t.get("date") == today]

            lines = [
                f"RAPPORT QUOTIDIEN {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
                f"",
                f"Compte: {info['balance']:,.2f} {info['currency']}",
                f"Capital: {info['equity']:,.2f} {info['currency']}",
                f"",
                f"Trades aujourd'hui: {len(today_trades)}",
                f"Positions ouvertes: {len(positions)}",
                f"",
                risk_status,
            ]
            if today_trades:
                lines.append(f"")
                lines.append(f"Historique:")
                for t in today_trades[-5:]:
                    pnl_str = f" P&L:{t.get('pnl', 0):+.2f}$" if 'pnl' in t else ""
                    lines.append(
                        f"  [{t['time']}] {t['action']} "
                        f"SL:{t['sl']} TP:{t['tp']} ({t['confidence']}%){pnl_str}"
                    )

            await self.app.bot.send_message(chat_id=self.chat_id, text="\n".join(lines))
            logger.info("Rapport quotidien envoye")
        except Exception as e:
            logger.error(f"Rapport quotidien error: {e}")

    # ------------------------------------------------------------------
    # Alertes
    # ------------------------------------------------------------------

    async def _send_alert(self, decision: dict, result: dict) -> None:
        if self.chat_id is None:
            return
        emoji = "+" if decision["action"] == "BUY" else "-"
        status = "OK" if result["success"] else "ECHEC"
        lines = [
            f"TRADE IA {status} {emoji}",
            f"",
            f"Action: {decision['action']} | Confiance: {decision.get('confidence', 0)}%",
            f"SL: {decision.get('sl_price', 0) or 0:.2f} | TP: {decision.get('tp_price', 0) or 0:.2f}",
        ]
        if result["success"]:
            lines.append(f"Ticket: {result.get('ticket', 'N/A')}")
        else:
            lines.append(f"Erreur: {result.get('error', 'Inconnue')}")
        lines.append(f"")
        lines.append(f"IA: {decision.get('reasoning', '')}")
        lines.append(f"")
        lines.append(self.risk_mgr.get_status())
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text="\n".join(lines))
        except Exception as e:
            logger.error(f"Alert error: {e}")

    async def _send_system_alert(self, message: str) -> None:
        """Alerte systeme critique."""
        if self.chat_id:
            try:
                await self.app.bot.send_message(chat_id=self.chat_id, text=f"SYSTEME: {message}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Self-reflection
    # ------------------------------------------------------------------

    def _format_trade_history(self) -> str:
        if not self._trade_history:
            return "Aucun trade aujourd'hui."
        lines = ["Derniers trades:"]
        for t in self._trade_history:
            pnl_str = f" P&L:{t['pnl']:+.2f}$" if t.get('pnl') else ""
            lines.append(
                f"  [{t['time']}] {t['action']} "
                f"SL:{t['sl']} TP:{t['tp']} ({t['confidence']}%){pnl_str} — {t['reasoning'][:60]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def _build_market_data(self, rates_m5, closes_m5, closes_m15, price, dxy=None, tick_vol=0) -> dict:
        ema50_m5 = self._ema(closes_m5, 50) if len(closes_m5) >= 50 else 0
        ema200_m5 = self._ema(closes_m5, 200) if len(closes_m5) >= 200 else 0
        ema200_m15 = self._ema(closes_m15, 200) if len(closes_m15) >= 200 else 0
        rsi = self._rsi(closes_m5, 14)
        atr = self._atr(rates_m5, 14) if len(rates_m5) >= 15 else 0
        trend_m15 = "HAUSSIERE" if ema200_m15 and price["bid"] > ema200_m15 else "BAISSIERE" if ema200_m15 else "?"

        candle_lines = []
        for i in range(max(-10, -len(rates_m5)), 0):
            r = rates_m5[i]
            o, h, l, c = _ro(r), _rh(r), _rl(r), _rc(r)
            direction = "+" if c >= o else "-"
            candle_lines.append(
                f"  [{direction}] O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} "
                f"Body:{abs(c - o):.2f} WkH:{h - max(o, c):.2f} WkL:{min(o, c) - l:.2f}"
            )

        return {
            "bid": f"{price['bid']:.2f}",
            "ask": f"{price['ask']:.2f}",
            "spread": f"{price['spread']:.3f}",
            "ema50_m5": f"{ema50_m5:.2f}",
            "ema200_m5": f"{ema200_m5:.2f}",
            "ema200_m15": f"{ema200_m15:.2f}",
            "rsi": f"{rsi:.1f}",
            "atr": f"{atr:.3f}",
            "trend_m15": trend_m15,
            "dxy": f"{dxy:.2f}" if dxy else "N/A",
            "tick_volume": str(tick_vol),
            "candles": "\n".join(candle_lines),
        }

    # ------------------------------------------------------------------
    # Indicateurs
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(closes: np.ndarray, period: int) -> float:
        if len(closes) < period:
            return float(np.mean(closes))
        alpha = 2.0 / (period + 1.0)
        seed = float(np.mean(closes[:period]))
        result = seed
        for price in closes[period:]:
            result = alpha * price + (1 - alpha) * result
        return float(result)

    @staticmethod
    def _rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-(period + 1):])
        gains = np.maximum(deltas, 0)
        losses = np.abs(np.minimum(deltas, 0))
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    @staticmethod
    def _atr(rates: list, period: int = 14) -> float:
        if len(rates) < period + 1:
            return 0.0
        tr_values = []
        for i in range(1, len(rates)):
            r, r_prev = rates[i], rates[i - 1]
            h, l, c_prev = _rh(r), _rl(r), _rc(r_prev)
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)
        return float(np.mean(tr_values[-period:]))

    # ------------------------------------------------------------------
    # Filtres
    # ------------------------------------------------------------------

    def _is_ny_session(self) -> bool:
        now = datetime.now(timezone.utc)
        return NY_START_HOUR <= now.hour < NY_END_HOUR

    @staticmethod
    def _get_candle_time(rate) -> int:
        if hasattr(rate, 'time'):
            return int(_rtime(rate))
        elif isinstance(rate, (tuple, list)):
            return int(rate[0])
        return 0

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute_decision(self, decision: dict, volume: float = VOLUME) -> dict:
        direction = decision["action"].lower()
        sl = decision["sl_price"]
        tp = decision["tp_price"]
        logger.info(
            f"StrategyEngine: EXEC {direction.upper()} {SYMBOL} "
            f"vol={volume:.2f} sl={sl:.2f} tp={tp:.2f} conf={decision['confidence']}"
        )
        return await self.mt5.open_order(
            symbol=SYMBOL,
            order_type=direction,
            volume=volume,
            sl=sl,
            tp=tp,
            comment=f"AI: {decision.get('reasoning', '')[:50]}",
        )
