"""Breakout de session NY : strategie nouvelle, distincte du retest existant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SessionBreakoutSignal:
    side: str
    sl: float
    tp: float
    range_high: float
    range_low: float


class SessionBreakout:
    def __init__(self, opening_bars: int = 6, reward_risk: float = 1.5):
        self.opening_bars = opening_bars
        self.reward_risk = reward_risk
        self._used_sessions: set[int] = set()

    def evaluate(
        self,
        bars: list[dict],
        quote: dict,
        range_start: int,
        buffer: float,
    ) -> Optional[SessionBreakoutSignal]:
        if range_start in self._used_sessions:
            return None
        if len(bars) <= self.opening_bars:
            return None
        opening = bars[:self.opening_bars]
        signal_bar = bars[self.opening_bars]
        range_high = max(bar["high"] for bar in opening)
        range_low = min(bar["low"] for bar in opening)
        close = signal_bar["close"]
        entry = quote["ask"] if close > range_high else quote["bid"]
        if close > range_high + buffer:
            sl = range_low
            risk = entry - sl
            if risk <= 0:
                return None
            signal = SessionBreakoutSignal(
                "buy", sl, entry + self.reward_risk * risk, range_high, range_low
            )
        elif close < range_low - buffer:
            sl = range_high
            risk = sl - entry
            if risk <= 0:
                return None
            signal = SessionBreakoutSignal(
                "sell", sl, entry - self.reward_risk * risk, range_high, range_low
            )
        else:
            return None
        self._used_sessions.add(range_start)
        return signal
