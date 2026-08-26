from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.types import ClosedBar, Quote, SignalIntent, SymbolSpec
from fakes import FakeMT5
from mt5_client import MT5Client
from strategy_engine import StrategyEngine


GOLD = SymbolSpec(
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
    filling_mode=FakeMT5.ORDER_FILLING_IOC,
)


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


class AlwaysBuy:
    def evaluate(self, bars_m5, bars_m15, quote, spec):
        entry = quote.ask if hasattr(quote, "ask") else quote["ask"]
        symbol = quote.symbol if hasattr(quote, "symbol") else "XAUUSD"
        return SignalIntent(
            decision_id="dec-test",
            symbol=symbol,
            side="buy",
            entry=float(entry),
            sl=float(entry) - 10.0,
            tp=float(entry) + 15.0,
            reason="test-breakout",
        )


class NeverSignal:
    def evaluate(self, bars_m5, bars_m15, quote, spec):
        return None


def gold_quote(symbol: str = "XAUUSD") -> Quote:
    return Quote(
        symbol=symbol,
        bid=2500.0,
        ask=2500.2,
        time_msc=1_700_000_000_000,
        server_time=datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
    )


def closed(time: int, close: float = 2500.0) -> ClosedBar:
    return ClosedBar(time=time, open=close, high=close + 1, low=close - 1, close=close)


def make_engine(client, decision=None, risk=None, execution=None, ledger=None, now=None, **kwargs):
    engine = StrategyEngine(
        application=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        mt5_client=client,
        risk_manager=risk or SilentRisk(),
        news_filter=kwargs.get("news_filter") or SilentNews(),
        news_collector=kwargs.get("news_collector") or SilentNews(),
        fmp_collector=kwargs.get("fmp_collector") or SilentFmp(),
        ai_trader=kwargs.get("ai_trader"),
        strategies=kwargs.get("strategies") or [],
        decision=decision,
        risk_engine=kwargs.get("risk_engine"),
        execution=execution,
        ledger=ledger,
        market_data=kwargs.get("market_data"),
        controls=kwargs.get("controls"),
        monitor=kwargs.get("monitor"),
    )
    engine.enabled = True
    if now is not None:
        engine._now = lambda: now
    return engine


def demo_client(api=None, armed=True, mode="demo"):
    client = MT5Client(mt5_api=api or FakeMT5(), trading_mode=mode)
    if armed and mode == "demo":
        client.arm_trading()
    return client
