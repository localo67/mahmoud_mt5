"""Types explicites du noyau de decision, sans secret."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_tick_value_profit: float
    trade_tick_value_loss: float
    trade_contract_size: float
    trade_calc_mode: int
    currency_profit: str
    currency_margin: str
    volume_min: float
    volume_max: float
    volume_step: float
    volume_limit: float
    trade_stops_level: int
    trade_freeze_level: int
    filling_mode: int


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    time_msc: int
    server_time: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class ClosedBar:
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int = 0
    real_volume: int = 0


@dataclass(frozen=True)
class SignalIntent:
    decision_id: str
    symbol: str
    side: Side
    entry: float
    sl: float
    tp: float
    reason: str
    volume_hint: Optional[float] = None


@dataclass(frozen=True)
class RiskLimits:
    risk_pct: float
    max_daily_loss: float
    max_consecutive_losses: int
    max_weekly_loss: float = 150.0
    max_monthly_loss: float = 400.0
    stale_quote_seconds: int = 120


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    balance: float
    currency: str
    free_margin: float
    floating_pnl: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    open_positions: int = 0


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    volume: float
    reason: str
    expected_loss: float = 0.0
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OrderIntent:
    decision_id: str
    symbol: str
    side: Side
    volume: float
    price: float
    sl: float
    tp: float
    filling_mode: int
    comment: str = ""
    client_order_id: str = ""
    send_attempt_id: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    decision_id: str
    status: str
    order_id: Optional[int] = None
    deal_id: Optional[int] = None
    position_id: Optional[int] = None
    volume: float = 0.0
    price: float = 0.0
    comment: str = ""
    retcode: Optional[int] = None
    ambiguous: bool = False
