from datetime import datetime, timezone

from research.archive import TickArchive
from research.backtest import EventBacktest
from research.lookahead import LookAheadError, assert_no_lookahead
from research.quality import quality_report
from research.replay import golden_replay


def _tick(ms, bid, ask, symbol="XAUUSD"):
    return {
        "time_msc": ms,
        "bid": bid,
        "ask": ask,
        "symbol": symbol,
        "latency_ms": 8,
    }


def test_archive_stores_bid_ask_and_exports_parquet(tmp_path) -> None:
    archive = TickArchive(tmp_path / "ticks.sqlite", tmp_path / "ticks.parquet")
    archive.append(_tick(1_700_000_000_000, 2500.0, 2500.2))
    archive.append(_tick(1_700_000_000_200, 2500.1, 2500.3))
    archive.flush()

    rows = archive.load()
    assert len(rows) == 2
    assert rows[0]["bid"] == 2500.0
    assert rows[0]["ask"] == 2500.2
    assert (tmp_path / "ticks.parquet").exists()


def test_quality_report_flags_gaps_duplicates_and_crossed_quotes(tmp_path) -> None:
    archive = TickArchive(tmp_path / "ticks.sqlite", tmp_path / "ticks.parquet")
    archive.append(_tick(1_000, 2500.0, 2500.2))
    archive.append(_tick(1_000, 2500.0, 2500.2))
    archive.append(_tick(60_000, 2501.0, 2500.9))
    archive.flush()
    report = quality_report(archive.load(), max_gap_ms=1_000)

    assert report["duplicates"] == 1
    assert report["crossed_quotes"] == 1
    assert report["gaps"] >= 1
    assert report["ok"] is False


def test_event_backtest_executes_on_next_tick_with_ask_bid() -> None:
    ticks = [
        _tick(0, 2500.0, 2500.2),
        _tick(300_000, 2501.0, 2501.2),
        _tick(300_100, 2501.1, 2501.3),
        _tick(600_000, 2503.0, 2503.2),
    ]
    bars = [{"time": 0, "open": 2500.0, "high": 2500.5, "low": 2499.5, "close": 2501.0}]

    def signal(closed_bars, now_ms):
        if closed_bars and closed_bars[-1]["close"] >= 2501.0 and now_ms == 300_000:
            return {"side": "buy", "sl": 2499.0, "tp": 2503.0}
        return None

    result = EventBacktest(ticks, commission=0.1, slippage=0.0).run(bars, signal)
    assert result.trades
    assert result.trades[0]["entry_price"] == 2501.3
    assert result.trades[0]["exit_price"] == 2503.0


def test_golden_replay_is_deterministic() -> None:
    ticks = [_tick(i * 1000, 2500.0 + i * 0.01, 2500.2 + i * 0.01) for i in range(10)]
    bars = [{"time": 0, "open": 2500.0, "high": 2500.4, "low": 2499.9, "close": 2500.2}]

    def signal(closed_bars, now_ms):
        return None

    first = golden_replay(ticks, bars, signal)
    second = golden_replay(ticks, bars, signal)
    assert first == second


def test_lookahead_detector_rejects_future_bars() -> None:
    bars = [
        {"time": 0, "close": 1.0},
        {"time": 300, "close": 2.0},
    ]
    try:
        assert_no_lookahead(bars, now=100, accessor=lambda items: items[-1]["time"])
    except LookAheadError:
        return
    raise AssertionError("lookahead should have been detected")


def test_news_without_first_seen_at_cannot_be_used() -> None:
    from research.news_pit import PointInTimeNews

    store = PointInTimeNews()
    try:
        store.add({"headline": "FOMC", "published_at": datetime.now(timezone.utc).isoformat()})
    except ValueError as exc:
        assert "first_seen_at" in str(exc)
        return
    raise AssertionError("news without first_seen_at must be rejected")
