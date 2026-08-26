"""Breakout de session NY : strategie nouvelle, distincte du retest existant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Union

from core.types import ClosedBar, Quote, SignalIntent, SymbolSpec

VERSION = "1.0"


@dataclass(frozen=True)
class SessionBreakoutSignal:
    side: str
    sl: float
    tp: float
    range_high: float
    range_low: float


def make_decision_id(symbol: str, timeframe: str, candle_time: int, version: str = VERSION) -> str:
    return f"session_breakout:{version}:{symbol}:{timeframe}:{candle_time}"


class SessionBreakout:
    def __init__(self, opening_bars: int = 6, reward_risk: float = 1.5):
        self.opening_bars = opening_bars
        self.reward_risk = reward_risk
        self._used_sessions: set[int] = set()

    def evaluate(
        self,
        bars_m5,
        bars_m15=None,
        quote=None,
        spec=None,
        range_start: Optional[int] = None,
        buffer: float = 0.0,
    ) -> Optional[Union[SessionBreakoutSignal, SignalIntent]]:
        if bars_m5 and isinstance(bars_m5[0], dict):
            quote_dict = bars_m15 if isinstance(bars_m15, dict) else quote
            return self.evaluate_range(
                bars_m5,
                quote_dict,
                range_start=range_start,
                buffer=buffer,
            )
        return self.evaluate_market(bars_m5, quote, spec, range_start=range_start, buffer=buffer)

    def evaluate_range(
        self,
        bars: list[dict],
        quote: dict,
        range_start: Optional[int] = None,
        buffer: float = 0.0,
    ) -> Optional[SessionBreakoutSignal]:
        if range_start is None and bars:
            range_start = int(bars[0]["time"])
        if range_start in self._used_sessions:
            return None
        if len(bars) <= self.opening_bars:
            return None
        opening = bars[: self.opening_bars]
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

    def evaluate_market(
        self,
        bars_m5: Sequence[ClosedBar],
        quote: Quote,
        spec: Optional[SymbolSpec] = None,
        range_start: Optional[int] = None,
        buffer: float = 0.0,
    ) -> Optional[SignalIntent]:
        bars = [
            {
                "time": bar.time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
            for bar in bars_m5
        ]
        quote_dict = {"bid": quote.bid, "ask": quote.ask, "spread": quote.spread}
        if buffer <= 0 and spec is not None:
            buffer = max(quote.spread, spec.trade_tick_size)
        signal = self.evaluate_range(bars, quote_dict, range_start=range_start, buffer=buffer)
        if signal is None:
            return None
        candle_time = bars_m5[-1].time if bars_m5 else 0
        entry = quote.ask if signal.side == "buy" else quote.bid
        return SignalIntent(
            decision_id=make_decision_id(quote.symbol, "M5", candle_time),
            symbol=quote.symbol,
            side=signal.side,
            entry=entry,
            sl=signal.sl,
            tp=signal.tp,
            reason="session_breakout",
        )


def build(pack):
    return SessionBreakout(reward_risk=pack.reward_risk)
