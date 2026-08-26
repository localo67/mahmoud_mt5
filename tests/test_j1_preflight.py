from datetime import datetime, timezone

import pytest

from cycle_result import Blocker
from mt5_client import MT5Client
from fakes import FakeMT5


@pytest.mark.asyncio
async def test_preflight_reports_demo_account_and_symbol_specs() -> None:
    api = FakeMT5(symbols=["XAUUSD"])
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is True
    assert report["account"]["trade_mode"] == "demo"
    assert report["terminal"]["trade_allowed"] is True
    assert report["symbol"]["resolved"] == "XAUUSD"
    assert report["symbol"]["ambiguous"] is False
    assert report["specs"]["point"] == 0.01
    assert report["specs"]["volume_min"] == 0.01
    assert report["specs"]["filling_mode"] == FakeMT5.ORDER_FILLING_IOC
    assert report["rates"]["m5_closed"] >= 50
    assert report["order_check"]["called"] is True
    assert report["order_check"]["ok"] is True
    assert api.order_requests == []
    assert "password" not in str(report).lower()


@pytest.mark.asyncio
async def test_preflight_refuses_real_account() -> None:
    api = FakeMT5(account_trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL)
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is False
    assert Blocker.PREFLIGHT_FAILED.value in report["blockers"]
    assert report["account"]["trade_mode"] == "real"


@pytest.mark.asyncio
async def test_resolve_symbol_accepts_unique_suffix() -> None:
    api = FakeMT5(symbols=["XAUUSD.s"])
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    resolved = await client.resolve_symbol("XAUUSD")

    assert resolved["resolved"] == "XAUUSD.s"
    assert resolved["ambiguous"] is False
    assert resolved["candidates"] == ["XAUUSD.s"]


@pytest.mark.asyncio
async def test_resolve_symbol_does_not_guess_when_ambiguous() -> None:
    api = FakeMT5(symbols=["XAUUSD.s", "XAUUSDm"])
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    resolved = await client.resolve_symbol("XAUUSD")

    assert resolved["resolved"] is None
    assert resolved["ambiguous"] is True
    assert set(resolved["candidates"]) == {"XAUUSD.s", "XAUUSDm"}


@pytest.mark.asyncio
async def test_preflight_marks_stale_tick() -> None:
    stale = int(datetime.now(timezone.utc).timestamp()) - 600
    api = FakeMT5(tick_time=stale)
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is False
    assert Blocker.STALE_TICK.value in report["blockers"]


@pytest.mark.asyncio
async def test_preflight_marks_insufficient_closed_bars() -> None:
    api = FakeMT5(m5_count=10, m15_count=10)
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is False
    assert Blocker.INSUFFICIENT_CLOSED_BARS.value in report["blockers"]


@pytest.mark.asyncio
async def test_preflight_order_check_invalid_fill_never_sends() -> None:
    api = FakeMT5(filling=FakeMT5.ORDER_FILLING_FOK)
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is False
    assert Blocker.ORDER_CHECK_REJECTED.value in report["blockers"]
    assert api.order_requests == []
    assert api.check_requests


@pytest.mark.asyncio
async def test_preflight_unavailable_without_api() -> None:
    client = MT5Client(mt5_api=None, trading_mode="off")

    report = await client.preflight("XAUUSD")

    assert report["ok"] is False
    assert Blocker.MT5_UNAVAILABLE.value in report["blockers"]


@pytest.mark.asyncio
async def test_get_closed_rates_skips_forming_bar() -> None:
    api = FakeMT5(m5_count=5)
    client = MT5Client(mt5_api=api, trading_mode="shadow")

    rates = await client.get_closed_rates("XAUUSD", "M5", 4)

    assert rates is not None
    assert len(rates) == 4
