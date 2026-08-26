"""EMA, RSI et ATR uniques, calcules uniquement sur series cloturees."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def warmup_bars(ema_period: int, rsi_period: int, atr_period: int) -> int:
    return max(ema_period, rsi_period + 1, atr_period + 1)


def ema(closes: Sequence[float], period: int) -> float:
    values = np.asarray(closes, dtype=float)
    if len(values) == 0:
        return 0.0
    if len(values) < period:
        return float(np.mean(values))
    alpha = 2.0 / (period + 1.0)
    result = float(np.mean(values[:period]))
    for price in values[period:]:
        result = alpha * float(price) + (1.0 - alpha) * result
    return float(result)


def rsi(closes: Sequence[float], period: int = 14) -> float:
    values = np.asarray(closes, dtype=float)
    if len(values) < period + 1:
        return 50.0
    deltas = np.diff(values[-(period + 1):])
    gains = np.maximum(deltas, 0.0)
    losses = np.abs(np.minimum(deltas, 0.0))
    avg_gain = float(np.mean(gains))
    avg_loss = float(np.mean(losses))
    if avg_loss == 0.0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def atr(ohlc: Sequence[tuple[float, float, float, float]], period: int = 14) -> float:
    if len(ohlc) < period + 1:
        return 0.0
    tr_values = []
    for index in range(1, len(ohlc)):
        _open, high, low, close = ohlc[index]
        prev_close = ohlc[index - 1][3]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
    return float(np.mean(tr_values[-period:]))
