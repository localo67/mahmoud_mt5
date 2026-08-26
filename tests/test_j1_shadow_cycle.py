from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cycle_result import Blocker, CycleResult
from fakes import FakeMT5
from helpers_runtime import AlwaysBuy, NeverSignal, SilentNews, make_engine
from mt5_client import MT5Client


@pytest.mark.asyncio
async def test_evaluated_candle_always_returns_structured_result() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    engine = make_engine(client, now=now)

    result = await engine.evaluate_closed_candle()

    assert isinstance(result, CycleResult)
    assert result.blockers
    assert Blocker.OUTSIDE_SESSION.value in result.blockers
    assert result.candle_time is not None
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_collects_multiple_blockers_together() -> None:
    api = FakeMT5(m5_count=10, m15_count=10, tick_time=1_600_000_000)
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    news = SilentNews()
    news.is_news_time = AsyncMock(return_value=True)
    engine = make_engine(client, now=now, news_filter=news)

    result = await engine.evaluate_closed_candle()

    assert Blocker.OUTSIDE_SESSION.value in result.blockers
    assert Blocker.NEWS_BLOCK.value in result.blockers
    assert Blocker.STALE_TICK.value in result.blockers
    assert Blocker.INSUFFICIENT_CLOSED_BARS.value in result.blockers


@pytest.mark.asyncio
async def test_shadow_candidate_calls_order_check_never_order_send() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    engine = make_engine(client, decision=AlwaysBuy(), now=now)

    result = await engine.evaluate_closed_candle()

    assert result.outcome == "SHADOW_CANDIDATE"
    assert Blocker.SHADOW_CANDIDATE.value in result.blockers
    assert api.check_requests
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_no_signal_is_logged_as_wait() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    engine = make_engine(client, decision=NeverSignal(), now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.NO_SIGNAL.value in result.blockers
    assert result.outcome == "WAIT"
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_position_existing_blocks_without_send() -> None:
    api = FakeMT5()
    api.positions = [
        SimpleNamespace(
            ticket=1,
            symbol="XAUUSD",
            type=0,
            volume=0.01,
            price_open=2500.0,
            price_current=2501.0,
            sl=2490.0,
            tp=2520.0,
            profit=1.0,
            swap=0.0,
            commission=0.0,
            comment="x",
            time=0,
            identifier=1,
        )
    ]
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    engine = make_engine(client, decision=AlwaysBuy(), now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.POSITION_EXISTS.value in result.blockers
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_blocker_distribution_counts_every_evaluated_candle() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    engine = make_engine(client, now=now)

    await engine.evaluate_closed_candle()
    await engine.evaluate_closed_candle()
    report = engine.get_blocker_report()

    assert report["evaluated_candles"] == 2
    assert report["distribution"][Blocker.OUTSIDE_SESSION.value] == 2
    assert "password" not in report


@pytest.mark.asyncio
async def test_unresolved_symbol_is_explicit() -> None:
    api = FakeMT5(symbols=["EURUSD"])
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    engine = make_engine(client, now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.SYMBOL_UNRESOLVED.value in result.blockers


@pytest.mark.asyncio
async def test_shadow_and_demo_share_canonical_events(tmp_path) -> None:
    from config import MAGIC_NUMBER
    from core.events import normalize_events
    from core.execution import ExecutionGateway
    from core.ledger import Ledger
    from core.mt5_execution import MT5DemoAdapter
    from core.simulation import ShadowAdapter
    from helpers_runtime import GOLD, demo_client

    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    shadow_api = FakeMT5()
    demo_api = FakeMT5()
    shadow_ledger = Ledger(tmp_path / "shadow.sqlite")
    demo_ledger = Ledger(tmp_path / "demo.sqlite")
    shadow_client = MT5Client(mt5_api=shadow_api, trading_mode="shadow")
    demo_client_ = demo_client(demo_api, armed=True)
    shadow_exec = ExecutionGateway(
        shadow_client,
        shadow_ledger,
        GOLD,
        MAGIC_NUMBER,
        adapter=ShadowAdapter(shadow_client, magic=MAGIC_NUMBER),
    )
    demo_exec = ExecutionGateway(
        demo_client_,
        demo_ledger,
        GOLD,
        MAGIC_NUMBER,
        adapter=MT5DemoAdapter(demo_client_, GOLD),
    )
    shadow_engine = make_engine(
        shadow_client, decision=AlwaysBuy(), execution=shadow_exec, ledger=shadow_ledger, now=now
    )
    demo_engine = make_engine(
        demo_client_, decision=AlwaysBuy(), execution=demo_exec, ledger=demo_ledger, now=now
    )

    shadow_result = await shadow_engine.evaluate_closed_candle()
    demo_result = await demo_engine.evaluate_closed_candle()

    assert shadow_result.outcome == "SHADOW_CANDIDATE"
    assert demo_result.outcome == "EXECUTED"
    assert shadow_api.order_requests == []
    assert demo_api.order_requests
    assert normalize_events(shadow_ledger.events("dec-test")) == normalize_events(
        demo_ledger.events("dec-test")
    )
