import pytest

from core.data import ClosedBarMarketData
from mt5_client import MT5Client
from fakes import FakeMT5


@pytest.mark.asyncio
async def test_market_data_uses_closed_bars_only() -> None:
    api = FakeMT5(m5_count=6)
    client = MT5Client(mt5_api=api, trading_mode="off")
    provider = ClosedBarMarketData(client)

    bars = await provider.closed_bars("XAUUSD", "M5", 5)

    assert len(bars) == 5
    assert all(bar.close > 0 for bar in bars)
