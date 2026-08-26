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
        bars_fast: Sequence[ClosedBar],
        bars_slow: Sequence[ClosedBar],
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


class ExecutionAdapter(Protocol):
    backend: str
    simulated: bool

    async def check(self, order: OrderIntent) -> dict:
        ...

    async def send(self, order: OrderIntent) -> dict:
        ...

    async def orders(self, symbol: str) -> list[dict]:
        ...

    async def history_orders(self, symbol: str) -> list[dict]:
        ...

    async def history_deals(self, symbol: str) -> list[dict]:
        ...

    async def positions(self, symbol: Optional[str] = None) -> list[dict]:
        ...
