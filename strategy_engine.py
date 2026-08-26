"""Orchestrateur deterministe: donnees cloturees -> decision -> risque -> execution."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from telegram.ext import Application

from config import (
    CANDLE_COUNT,
    DAILY_REPORT_HOUR,
    MAX_SPREAD_POINTS,
    NY_END_HOUR,
    NY_START_HOUR,
    SYMBOL,
    TRADING_MODE,
)
from core.data import ClosedBarMarketData
from core.session import SessionPolicy
from core.types import AccountSnapshot, OrderIntent, Quote, SignalIntent
from cycle_result import (
    Blocker,
    CycleResult,
    MIN_CLOSED_BARS,
    STALE_TICK_SECONDS,
)
from strategies.session_breakout import SessionBreakout

logger = logging.getLogger(__name__)

PIP_VALUE = 0.01
HEARTBEAT_INTERVAL = 30


class StrategyEngine:
    """Orchestrateur mince autour du noyau deterministe."""

    def __init__(
        self,
        application: Application,
        mt5_client,
        risk_manager=None,
        news_filter=None,
        news_collector=None,
        fmp_collector=None,
        ai_trader=None,
        strategies=None,
        decision=None,
        risk_engine=None,
        execution=None,
        ledger=None,
        market_data=None,
        controls=None,
        monitor=None,
    ):
        self.app = application
        self.mt5 = mt5_client
        self.risk_mgr = risk_manager
        self.news_filter = news_filter
        self.news_collector = news_collector
        self.fmp = fmp_collector
        self.ai = ai_trader
        self.strategies = strategies or []
        self.decision = decision if decision is not None else SessionBreakout()
        self.risk_engine = risk_engine
        self.execution = execution
        self.ledger = ledger
        self.market_data = market_data or ClosedBarMarketData(mt5_client)
        self.controls = controls
        self.monitor = monitor
        self.chat_id: Optional[int] = None
        self.enabled: bool = True
        self._last_candle_time: int = 0
        self._evaluated_candles: int = 0
        self._blocker_counts: Counter[str] = Counter()
        self._last_cycle: Optional[CycleResult] = None
        self._resolved_symbol: Optional[str] = None
        self._symbol_fingerprint: Optional[tuple] = None
        self._last_heartbeat: float = 0.0
        self._consecutive_errors: int = 0
        self._emergency_stop: bool = False
        self._session = SessionPolicy(
            start_hour=NY_START_HOUR,
            end_hour=NY_END_HOUR,
            allow_overnight=False,
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def get_blocker_report(self) -> dict:
        return {
            "evaluated_candles": self._evaluated_candles,
            "distribution": dict(self._blocker_counts),
            "last_outcome": self._last_cycle.outcome if self._last_cycle else None,
            "last_blockers": list(self._last_cycle.blockers) if self._last_cycle else [],
            "mode": getattr(self.mt5, "trading_mode", TRADING_MODE),
        }

    def _record_cycle(self, result: CycleResult) -> CycleResult:
        self._evaluated_candles += 1
        self._blocker_counts.update(result.blockers)
        self._last_cycle = result
        if self.ledger is not None:
            self.ledger.append(
                str(result.candle_time or "cycle"),
                "decision_evaluated",
                {"outcome": result.outcome, "blockers": list(result.blockers)},
            )
        return result

    async def evaluate_closed_candle(self) -> CycleResult:
        blockers: list[str] = []
        details: dict = {}
        candle_time: Optional[int] = None
        now = self._now()
        symbol = SYMBOL
        quote: Optional[Quote] = None
        spec = None
        bars_m5 = []
        bars_m15 = []

        if self.controls is not None and not self.controls.state.entries_allowed:
            blockers.append(Blocker.ENTRIES_HALTED.value)

        try:
            resolved = await self.mt5.resolve_symbol(SYMBOL)
            details["symbol"] = {
                "requested": resolved.get("requested"),
                "resolved": resolved.get("resolved"),
                "candidates": resolved.get("candidates"),
                "ambiguous": resolved.get("ambiguous"),
            }
            if not resolved.get("resolved"):
                blockers.append(Blocker.SYMBOL_UNRESOLVED.value)
            else:
                symbol = resolved["resolved"]
                self._resolved_symbol = symbol
        except Exception as exc:
            blockers.append(Blocker.MT5_UNAVAILABLE.value)
            details["mt5_error"] = str(exc)
            return self._record_cycle(CycleResult(None, blockers, "BLOCKED", details))

        if Blocker.SYMBOL_UNRESOLVED.value not in blockers:
            try:
                spec = await self.market_data.specs(symbol)
                quote = await self.market_data.quote(symbol)
                fingerprint = None
                if spec:
                    fingerprint = (
                        spec.point,
                        spec.trade_tick_size,
                        spec.volume_min,
                        spec.filling_mode,
                    )
                    if (
                        self._symbol_fingerprint is not None
                        and fingerprint != self._symbol_fingerprint
                    ):
                        blockers.append(Blocker.SYMBOL_SPEC_CHANGED.value)
                    self._symbol_fingerprint = fingerprint
                details["tick"] = {
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "spread": quote.spread,
                    "age_seconds": int(now.timestamp()) - int(quote.server_time.timestamp()),
                }
                if details["tick"]["age_seconds"] > STALE_TICK_SECONDS:
                    blockers.append(Blocker.STALE_TICK.value)
            except Exception as exc:
                blockers.append(Blocker.STALE_TICK.value)
                details["tick_error"] = str(exc)

            try:
                bars_m5 = list(await self.market_data.closed_bars(symbol, "M5", CANDLE_COUNT))
                bars_m15 = list(await self.market_data.closed_bars(symbol, "M15", CANDLE_COUNT))
                details["rates"] = {"m5_closed": len(bars_m5), "m15_closed": len(bars_m15)}
                if len(bars_m5) < MIN_CLOSED_BARS or len(bars_m15) < MIN_CLOSED_BARS:
                    blockers.append(Blocker.INSUFFICIENT_CLOSED_BARS.value)
                elif bars_m5:
                    candle_time = bars_m5[-1].time
            except Exception as exc:
                blockers.append(Blocker.INSUFFICIENT_CLOSED_BARS.value)
                details["rates_error"] = str(exc)

        if not self._session.is_open(now):
            blockers.append(Blocker.OUTSIDE_SESSION.value)

        if self.news_filter is not None:
            try:
                if await self.news_filter.is_news_time():
                    blockers.append(Blocker.NEWS_BLOCK.value)
            except Exception as exc:
                blockers.append(Blocker.NEWS_BLOCK.value)
                details["news_error"] = str(exc)

        if self.risk_mgr is not None:
            allowed, reason = self.risk_mgr.check_trade_allowed()
            if not allowed:
                blockers.append(Blocker.RISK_BLOCK.value)
                details["risk"] = reason

        if quote is not None and quote.spread / PIP_VALUE > MAX_SPREAD_POINTS:
            blockers.append(Blocker.SPREAD_BLOCK.value)

        if not await self._margin_sufficient():
            blockers.append(Blocker.MARGIN_BLOCK.value)

        try:
            positions = await self.mt5.get_positions(symbol=symbol)
            if positions:
                blockers.append(Blocker.POSITION_EXISTS.value)
                details["open_positions"] = len(positions)
        except Exception as exc:
            details["position_error"] = str(exc)

        snapshot = {
            "kill_switch": bool(getattr(self.risk_engine, "kill_switch", False)),
            "stale_quote": Blocker.STALE_TICK.value in blockers,
            "unknown_position": False,
            "reconciliation_ok": True,
            "missing_sl": False,
        }
        if self.monitor is not None:
            halt = self.monitor.observe(snapshot)
            if halt.halt:
                blockers.append(halt.reason or Blocker.ENTRIES_HALTED.value)

        hard = {
            Blocker.MT5_UNAVAILABLE.value,
            Blocker.SYMBOL_UNRESOLVED.value,
            Blocker.STALE_TICK.value,
            Blocker.INSUFFICIENT_CLOSED_BARS.value,
            Blocker.OUTSIDE_SESSION.value,
            Blocker.NEWS_BLOCK.value,
            Blocker.RISK_BLOCK.value,
            Blocker.SPREAD_BLOCK.value,
            Blocker.MARGIN_BLOCK.value,
            Blocker.POSITION_EXISTS.value,
            Blocker.SYMBOL_SPEC_CHANGED.value,
            Blocker.ENTRIES_HALTED.value,
        }
        if set(blockers) & hard or quote is None or spec is None:
            return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))

        intent = self.decision.evaluate(bars_m5, bars_m15, quote, spec)
        if not isinstance(intent, SignalIntent):
            blockers.append(Blocker.NO_SIGNAL.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "WAIT", details))

        details["decision"] = {
            "action": intent.side,
            "has_sl": intent.sl is not None,
            "has_tp": intent.tp is not None,
            "decision_id": intent.decision_id,
        }
        if intent.sl is None or intent.tp is None:
            blockers.append(Blocker.ORDER_CHECK_REJECTED.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "WAIT", details))

        volume = 0.01
        if self.risk_engine is not None:
            account_raw = await self.mt5.get_account_info()
            account = AccountSnapshot(
                equity=float(account_raw["equity"]),
                balance=float(account_raw["balance"]),
                currency=str(account_raw.get("currency") or "USD"),
                free_margin=float(account_raw.get("free_margin") or 0.0),
                open_positions=1 if details.get("open_positions") else 0,
            )
            risk = self.risk_engine.decide(intent, quote, account)
            details["risk_engine"] = {"allowed": risk.allowed, "reason": risk.reason}
            if self.ledger is not None:
                kind = "risk_accepted" if risk.allowed else "risk_rejected"
                self.ledger.append(intent.decision_id, kind, {"reason": risk.reason, "volume": risk.volume})
            if not risk.allowed:
                blockers.append(Blocker.RISK_BLOCK.value)
                return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))
            volume = risk.volume

        trading_mode = getattr(self.mt5, "trading_mode", TRADING_MODE)
        order = OrderIntent(
            decision_id=intent.decision_id,
            symbol=symbol,
            side=intent.side,
            volume=volume,
            price=intent.entry,
            sl=intent.sl,
            tp=intent.tp,
            filling_mode=spec.filling_mode if spec.filling_mode in {0, 1, 2, 3} else 1,
            comment=f"id:{intent.decision_id}",
            client_order_id=f"c:{intent.decision_id}",
        )

        if (
            trading_mode == "demo"
            and not getattr(self.mt5, "is_trading_armed", False)
        ):
            blockers.append(Blocker.NOT_ARMED.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))

        if self.execution is not None:
            result = await self.execution.submit(order)
            details["execution"] = {"status": result.status, "ambiguous": result.ambiguous}
            simulated = bool(getattr(self.execution.adapter, "simulated", False))
            if result.ambiguous:
                blockers.append(Blocker.SEND_AMBIGUOUS.value)
                return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))
            if result.status == "REJECTED":
                blockers.append(Blocker.ORDER_CHECK_REJECTED.value)
                return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))
            if trading_mode != "demo" or simulated:
                blockers.append(Blocker.SHADOW_CANDIDATE.value)
                return self._record_cycle(
                    CycleResult(candle_time, blockers, "SHADOW_CANDIDATE", details)
                )
            blockers.append(Blocker.EXECUTED.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "EXECUTED", details))

        check = await self.mt5.check_order(
            symbol,
            intent.side,
            volume,
            sl=intent.sl,
            tp=intent.tp,
            comment=f"id:{intent.decision_id}",
        )
        details["order_check"] = {
            "ok": check.get("ok"),
            "retcode": check.get("retcode"),
            "called": check.get("called"),
        }
        if not check.get("ok"):
            blockers.append(Blocker.ORDER_CHECK_REJECTED.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))
        if trading_mode != "demo":
            blockers.append(Blocker.SHADOW_CANDIDATE.value)
            return self._record_cycle(
                CycleResult(candle_time, blockers, "SHADOW_CANDIDATE", details)
            )
        if not getattr(self.mt5, "is_trading_armed", False):
            blockers.append(Blocker.NOT_ARMED.value)
            return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))
        blockers.append(Blocker.NOT_ARMED.value)
        details["execution"] = "gateway required"
        return self._record_cycle(CycleResult(candle_time, blockers, "BLOCKED", details))

    async def _margin_sufficient(self) -> bool:
        try:
            info = await self.mt5.get_account_info()
            return float(info.get("free_margin", 0)) >= 5.0
        except Exception:
            return False

    async def run(self) -> None:
        logger.info("StrategyEngine: noyau deterministe session_breakout")
        report_task = asyncio.create_task(self._daily_report_scheduler())
        try:
            while True:
                try:
                    await asyncio.sleep(10)
                    if not self.enabled:
                        continue
                    if self._emergency_stop:
                        continue
                    if not await self._heartbeat():
                        continue
                    await self._session_exit_if_needed()
                    peek_symbol = self._resolved_symbol or SYMBOL
                    try:
                        peek = await self.mt5.get_closed_rates(peek_symbol, "M5", 2)
                    except Exception:
                        peek = None
                    if peek:
                        peek_time = int(getattr(peek[-1], "time", peek[-1][0]))
                        if peek_time == self._last_candle_time:
                            continue
                    cycle = await self.evaluate_closed_candle()
                    if cycle.candle_time is not None:
                        self._last_candle_time = cycle.candle_time
                    logger.info(
                        "StrategyEngine: cycle outcome=%s blockers=%s",
                        cycle.outcome,
                        ",".join(cycle.blockers) or "-",
                    )
                    self._consecutive_errors = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._consecutive_errors += 1
                    logger.error("StrategyEngine: error #%s — %s", self._consecutive_errors, exc)
                    if self._consecutive_errors >= 10:
                        self._emergency_stop = True
                        if self.controls is not None:
                            self.controls.halt_entries("consecutive_errors")
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("StrategyEngine: arret")
        finally:
            report_task.cancel()
            try:
                await report_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self) -> bool:
        now = asyncio.get_event_loop().time()
        if now - self._last_heartbeat < HEARTBEAT_INTERVAL:
            return True
        self._last_heartbeat = now
        if not await self.mt5.check_connection():
            if not await self.mt5.initialize():
                return False
        return True

    async def _get_closed_profit(self, ticket: int):
        return await self.mt5.get_closed_profit(ticket)

    async def _session_exit_if_needed(self) -> None:
        if self.execution is None:
            return
        if self.controls is not None and not self.controls.state.position_management_enabled:
            return
        if self._session.is_open(self._now()):
            return
        try:
            positions = await self.mt5.get_positions(symbol=self._resolved_symbol or SYMBOL)
        except Exception:
            return
        for position in positions:
            if "id:" not in str(position.get("comment") or ""):
                continue
            await self.execution.close_owned(position["ticket"])

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
            report = self.get_blocker_report()
            text = (
                f"RAPPORT QUOTIDIEN {datetime.now(timezone.utc).strftime('%d/%m/%Y')}\n"
                f"Compte: {info['balance']:,.2f} {info['currency']}\n"
                f"Mode: {report.get('mode')}\n"
                f"Bougies: {report.get('evaluated_candles')}\n"
            )
            await self.app.bot.send_message(chat_id=self.chat_id, text=text)
        except Exception as exc:
            logger.error("Rapport quotidien error: %s", exc)
