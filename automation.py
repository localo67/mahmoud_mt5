"""Moteur d'automation : assemble le noyau deterministe XAUUSD."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from telegram.ext import Application

from config import (
    AUTHORIZED_CHAT_ID,
    MAGIC_NUMBER,
    MAX_CONSECUTIVE_LOSSES,
    MAX_DAILY_LOSS,
    RISK_PER_TRADE_PCT,
    STATE_FILE,
    TRADING_MODE,
)
from core.data import ClosedBarMarketData
from core.execution import ExecutionGateway
from core.ledger import Ledger
from core.mt5_execution import MT5DemoAdapter
from core.risk import RiskEngine
from core.simulation import ShadowAdapter
from core.types import RiskLimits, SymbolSpec
from news_filter import NewsFilter
from ops.control import OperationalControl
from ops.monitor import Monitor
from strategies.session_breakout import SessionBreakout
from strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)

DEFAULT_SPEC = SymbolSpec(
    name="XAUUSD",
    digits=2,
    point=0.01,
    trade_tick_size=0.01,
    trade_tick_value=1.0,
    trade_tick_value_profit=1.0,
    trade_tick_value_loss=1.0,
    trade_contract_size=100.0,
    trade_calc_mode=0,
    currency_profit="USD",
    currency_margin="USD",
    volume_min=0.01,
    volume_max=5.0,
    volume_step=0.01,
    volume_limit=10.0,
    trade_stops_level=10,
    trade_freeze_level=0,
    filling_mode=1,
)


class AutomationEngine:
    """Assemble ClosedBarMarketData, SessionBreakout, RiskEngine, gateway et ledger."""

    def __init__(
        self,
        application: Application,
        mt5_client,
        ledger_path: Path | None = None,
        state_path: Path | None = None,
        control_path: Path | None = None,
    ):
        self.app = application
        self.mt5 = mt5_client
        mode = getattr(mt5_client, "trading_mode", TRADING_MODE)
        self.enabled: bool = mode in {"shadow", "demo"}
        self.news_filter = NewsFilter(fail_safe=True)
        self.ledger = Ledger(Path(ledger_path or "data/ledger.sqlite"))
        self.controls = OperationalControl(Path(control_path or "data/control.json"))
        self.monitor = Monitor(self.controls)
        self.market_data = ClosedBarMarketData(mt5_client)
        self.decision = SessionBreakout()
        self.risk_engine = RiskEngine(
            limits=RiskLimits(
                risk_pct=RISK_PER_TRADE_PCT,
                max_daily_loss=MAX_DAILY_LOSS,
                max_consecutive_losses=MAX_CONSECUTIVE_LOSSES,
            ),
            spec=DEFAULT_SPEC,
            now=lambda: datetime.now(timezone.utc),
            state_path=Path(state_path or STATE_FILE),
        )
        if mode == "shadow":
            adapter = ShadowAdapter(mt5_client, magic=MAGIC_NUMBER)
        else:
            adapter = MT5DemoAdapter(mt5_client, DEFAULT_SPEC)
        self.execution = ExecutionGateway(
            mt5=mt5_client,
            ledger=self.ledger,
            spec=DEFAULT_SPEC,
            magic=MAGIC_NUMBER,
            adapter=adapter,
            controls=self.controls,
        )
        self.engine = StrategyEngine(
            application=application,
            mt5_client=mt5_client,
            news_filter=self.news_filter,
            decision=self.decision,
            risk_engine=self.risk_engine,
            execution=self.execution,
            ledger=self.ledger,
            market_data=self.market_data,
            controls=self.controls,
            monitor=self.monitor,
        )
        self.engine.enabled = self.enabled
        self.engine.chat_id = AUTHORIZED_CHAT_ID

    async def run(self) -> None:
        logger.info("AutomationEngine: noyau deterministe XAUUSD")
        await self.engine.run()

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if self.engine:
            self.engine.enabled = enabled
        logger.info("AutomationEngine: %s", "ON" if enabled else "OFF")

    def get_risk_status(self) -> str:
        return self.risk_engine.get_status()

    def get_blocker_report(self) -> dict:
        return self.engine.get_blocker_report()

    def reset_risk(self) -> str:
        return (
            "Reset refuse: kill switch non resettable a chaud. "
            "Telegram est en lecture seule."
        )
