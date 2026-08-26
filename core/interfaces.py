"""Interfaces du noyau : donnees, decision, risque, execution."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from core.types import (
    AccountSnapshot,
    ClosedBar,
    ExecutionResult,
    OrderIntent,
    Quote,
    RiskDecision,
    SignalIntent,
    SymbolSpec,
)


class MarketDataProvider(Protocol):
    async def closed_bars(self, symbol: str, timeframe: str, count: int) -> Sequence[ClosedBar]:
        ...

    async def quote(self, symbol: str) -> Quote:
        ...

    async def specs(self, symbol: str) -> Optional[SymbolSpec]:
        ...


class DecisionEngine(Protocol):
    def evaluate(
        self,
        bars_m5: Sequence[ClosedBar],
        bars_m15: Sequence[ClosedBar],
        quote: Quote,
        spec: SymbolSpec,
    ) -> Optional[SignalIntent]:
        ...


class RiskEngine(Protocol):
    def decide(
        self,
        intent: SignalIntent,
        quote: Quote,
        account: AccountSnapshot,
    ) -> RiskDecision:
        ...


class ExecutionGateway(Protocol):
    async def submit(self, order: OrderIntent) -> ExecutionResult:
        ...
