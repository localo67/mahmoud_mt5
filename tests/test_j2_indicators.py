from datetime import datetime, timezone

from core.indicators import atr, ema, rsi, warmup_bars


def test_ema_uses_sma_seed_then_recursive_smoothing() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    result = ema(closes, 3)
    assert result == 9.0


def test_ema_vector_is_stable_for_constant_series() -> None:
    closes = [2500.0] * 50
    assert ema(closes, 20) == 2500.0


def test_rsi_known_vector() -> None:
    closes = [10.0, 11.0, 12.0, 11.0]
    result = rsi(closes, 3)
    assert round(result, 6) == 66.666667


def test_atr_known_vector() -> None:
    bars = [
        (10.0, 12.0, 9.0, 11.0),
        (11.0, 13.0, 10.0, 12.0),
        (12.0, 12.5, 11.0, 11.5),
        (11.5, 14.0, 11.0, 13.0),
    ]
    result = atr(bars, 3)
    assert round(result, 6) == 2.5


def test_warmup_uses_longest_period() -> None:
    assert warmup_bars(ema_period=200, rsi_period=14, atr_period=14) == 200
