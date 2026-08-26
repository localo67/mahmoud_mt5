"""Moteur d'automation : assemble un pack + le noyau deterministe."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from config import (
    AUTHORIZED_CHAT_ID,
    MAX_CONSECUTIVE_LOSSES,
    MAX_DAILY_LOSS,
    RISK_PER_TRADE_PCT,
    STATE_FILE,
    STRATEGY_PACK,
    TRADING_MODE,
)
from core.data import ClosedBarMarketData
from core.execution import ExecutionGateway
from core.ledger import Ledger
from core.mt5_execution import MT5DemoAdapter
from core.pack import build_strategy, load_pack, resolve_pack_id
from core.risk import RiskEngine
from core.simulation import ShadowAdapter
from core.types import RiskLimits
from news_filter import NewsFilter
from ops.control import OperationalControl
from ops.monitor import Monitor
from strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


class AutomationEngine:
    """Assemble ClosedBarMarketData, pack, RiskEngine, gateway et ledger."""

    def __init__(
        self,
        application,
        mt5_client,
        ledger_path: Path | None = None,
        state_path: Path | None = None,
        control_path: Path | None = None,
        pack_id: str | None = None,
    ):
        self.app = application
        self.mt5 = mt5_client
        self.pack = load_pack(resolve_pack_id(pack_id, STRATEGY_PACK))
        spec = self.pack.fallback_spec
        mode = getattr(mt5_client, "trading_mode", TRADING_MODE)
        self.enabled: bool = mode in {"shadow", "demo"}
        self.news_filter = NewsFilter(fail_safe=self.pack.news_fail_safe)
        ledger_file = Path(ledger_path or self.pack.ledger)
        ledger_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(ledger_file)
        self.controls = OperationalControl(Path(control_path or "data/control.json"))
        self.monitor = Monitor(self.controls)
        self.market_data = ClosedBarMarketData(mt5_client)
        self.decision = build_strategy(self.pack)
        self.risk_engine = RiskEngine(
            limits=RiskLimits(
                risk_pct=RISK_PER_TRADE_PCT,
                max_daily_loss=MAX_DAILY_LOSS,
                max_consecutive_losses=MAX_CONSECUTIVE_LOSSES,
            ),
            spec=spec,
            now=lambda: datetime.now(timezone.utc),
            state_path=Path(state_path or STATE_FILE),
        )
        if mode == "shadow":
            adapter = ShadowAdapter(mt5_client, magic=self.pack.magic)
        else:
            adapter = MT5DemoAdapter(mt5_client, spec)
        self.execution = ExecutionGateway(
            mt5=mt5_client,
            ledger=self.ledger,
            spec=spec,
            magic=self.pack.magic,
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
            pack=self.pack,
        )
        self.engine.enabled = self.enabled
        self.engine.chat_id = AUTHORIZED_CHAT_ID if application is not None else None

    async def run(self) -> None:
        logger.info("AutomationEngine: pack=%s symbol=%s", self.pack.id, self.pack.symbol)
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
