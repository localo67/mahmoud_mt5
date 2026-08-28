from datetime import datetime, timezone

from core.pack import available_packs, build_strategy, load_pack
from core.types import ClosedBar, Quote, SignalIntent
from packs.session_breakout_xauusd.strategy import SessionBreakout


def _bar(time: int, open_: float, high: float, low: float, close: float) -> ClosedBar:
    return ClosedBar(time=time, open=open_, high=high, low=low, close=close)


def test_available_packs_lists_runnable_ids() -> None:
    ids = available_packs()
    assert "scalp_eurusd_m1" in ids
    assert "scalp_xauusd_m1" in ids
    assert "session_breakout_xauusd" in ids
    assert "london_breakout_eurusd" not in ids


def test_load_pack_unknown_raises() -> None:
    try:
        load_pack("does_not_exist")
    except ValueError as exc:
        assert "inconnu" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_runnable_packs_use_fx_week_from_market_open() -> None:
    for pack_id in ("scalp_eurusd_m1", "scalp_xauusd_m1", "session_breakout_xauusd"):
        pack = load_pack(pack_id)
        assert pack.session_kind == "fx_week"
        assert pack.session_tz == "America/New_York"
        assert pack.session_start_hour == 17
        assert pack.session_end_hour == 17


def test_session_breakout_pack_builds_same_strategy() -> None:
    pack = load_pack("session_breakout_xauusd")
    strategy = build_strategy(pack)
    assert isinstance(strategy, SessionBreakout)
    assert pack.max_trades_per_day == 1
    assert pack.symbol == "XAUUSD"


def test_xauusd_scalp_pack_loads() -> None:
    pack = load_pack("scalp_xauusd_m1")
    strategy = build_strategy(pack)
    assert pack.symbol == "XAUUSD"
    assert pack.fast_timeframe == "M1"
    assert strategy.pack.id == "scalp_xauusd_m1"


def test_eurusd_impulse_emits_buy_and_skips_noise() -> None:
    pack = load_pack("scalp_eurusd_m1")
    strategy = build_strategy(pack)
    spec = pack.fallback_spec
    start = 1_700_000_000
    slow = [
        _bar(start + i * 300, 1.0990 + i * 0.00005, 1.0991 + i * 0.00005, 1.0989 + i * 0.00005, 1.0990 + i * 0.00005)
        for i in range(30)
    ]
    fast = [
        _bar(start + i * 60, 1.10000, 1.10002, 1.09998, 1.10001)
        for i in range(10)
    ]
    impulse = _bar(start + 11 * 60, 1.10000, 1.10025, 1.09995, 1.10022)
    quote = Quote(
        symbol="EURUSD",
        bid=1.10012,
        ask=1.10022,
        time_msc=1,
        server_time=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
    )
    noise = strategy.evaluate(fast, slow, quote, spec)
    assert noise is None
    signal = strategy.evaluate(fast + [impulse], slow, quote, spec)
    assert isinstance(signal, SignalIntent)
    assert signal.side == "buy"
    assert signal.tp - signal.entry >= 4 * quote.spread
    again = strategy.evaluate(fast + [impulse], slow, quote, spec)
    assert again is None


def test_eurusd_skips_when_spread_too_wide() -> None:
    pack = load_pack("scalp_eurusd_m1")
    strategy = build_strategy(pack)
    spec = pack.fallback_spec
    start = 1_700_000_000
    slow = [
        _bar(start + i * 300, 1.0990 + i * 0.00005, 1.0992, 1.0988, 1.0990 + i * 0.00005)
        for i in range(30)
    ]
    impulse = _bar(start, 1.10000, 1.10040, 1.09990, 1.10035)
    quote = Quote(
        symbol="EURUSD",
        bid=1.10000,
        ask=1.10030,
        time_msc=1,
        server_time=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
    )
    assert strategy.evaluate([impulse], slow, quote, spec) is None
