import pytest

from strategy_engine import StrategyEngine


class HistoryClient:
    def __init__(self):
        self.tickets: list[int] = []

    async def get_closed_profit(self, ticket: int):
        self.tickets.append(ticket)
        return 12.5


@pytest.mark.asyncio
async def test_closed_profit_uses_mt5_client_only() -> None:
    client = HistoryClient()
    engine = object.__new__(StrategyEngine)
    engine.mt5 = client

    profit = await engine._get_closed_profit(123)

    assert profit == 12.5
    assert client.tickets == [123]
