from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cycle_result import Blocker, CycleResult
from mt5_client import MT5Client
from strategy_engine import StrategyEngine
from fakes import FakeMT5


class SilentNews:
    async def is_news_time(self):
        return False

    async def get_headlines(self, n):
        return []

    async def analyze_sentiment(self, headlines):
        return headlines

    def format_for_ai(self, headlines):
        return ""


class SilentFmp:
    async def get_forex_news(self, n):
        return []

    async def get_gold_price(self):
        return None

    async def get_treasury_rates(self):
        return None

    def format_for_ai(self, *args):
        return ""


class SilentRisk:
    def check_trade_allowed(self):
        return True, "OK"

    def get_context_for_ai(self):
        return "ok"

    def calculate_position_size(self, equity, atr):
        return 0.01

    def record_trade_result(self, profit):
        return None

    def get_status(self):
        return "ACTIF"


class WaitingAI:
    async def decide(self, **kwargs):
        return {
            "action": "WAIT",
            "confidence": 0,
            "sl_price": None,
            "tp_price": None,
            "reasoning": "no setup",
        }


class BuyAI:
    async def decide(self, **kwargs):
        return {
            "action": "BUY",
            "confidence": 80,
            "sl_price": 2490.0,
            "tp_price": 2520.0,
            "reasoning": "breakout",
        }


class LowConfidenceAI:
    async def decide(self, **kwargs):
        return {
            "action": "BUY",
            "confidence": 10,
            "sl_price": 2490.0,
            "tp_price": 2520.0,
            "reasoning": "weak",
        }


class MissingStopsAI:
    async def decide(self, **kwargs):
        return {
            "action": "BUY",
            "confidence": 90,
            "sl_price": None,
            "tp_price": None,
            "reasoning": "missing stops",
        }


def _engine(client, ai=None, news_on=False, risk=None, now=None):
    news = SilentNews()
    if news_on:
        news.is_news_time = AsyncMock(return_value=True)
    engine = StrategyEngine(
        application=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        mt5_client=client,
        risk_manager=risk or SilentRisk(),
        news_filter=news,
        news_collector=news,
        fmp_collector=SilentFmp(),
        ai_trader=ai or WaitingAI(),
        strategies=[],
    )
    engine.enabled = True
    if now is not None:
        engine._now = lambda: now
    return engine


@pytest.mark.asyncio
async def test_evaluated_candle_always_returns_structured_result() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    engine = _engine(client, now=now)

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
    engine = _engine(client, news_on=True, now=now)

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
    engine = _engine(client, ai=BuyAI(), now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.SHADOW_CANDIDATE.value in result.blockers or result.outcome == "SHADOW_CANDIDATE"
    assert result.outcome == "SHADOW_CANDIDATE"
    assert api.check_requests
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_ai_wait_is_logged_as_blocker() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    engine = _engine(client, ai=WaitingAI(), now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.AI_WAIT.value in result.blockers
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_low_confidence_and_missing_stops() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)

    low = await _engine(client, ai=LowConfidenceAI(), now=now).evaluate_closed_candle()
    missing = await _engine(client, ai=MissingStopsAI(), now=now).evaluate_closed_candle()

    assert Blocker.LOW_CONFIDENCE.value in low.blockers
    assert Blocker.ORDER_CHECK_REJECTED.value in missing.blockers or "sl" in str(missing.details).lower()


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
    engine = _engine(client, ai=BuyAI(), now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.POSITION_EXISTS.value in result.blockers
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_blocker_distribution_counts_every_evaluated_candle() -> None:
    api = FakeMT5()
    client = MT5Client(mt5_api=api, trading_mode="shadow")
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    engine = _engine(client, now=now)

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
    engine = _engine(client, now=now)

    result = await engine.evaluate_closed_candle()

    assert Blocker.SYMBOL_UNRESOLVED.value in result.blockers
