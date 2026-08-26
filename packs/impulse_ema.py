"""Impulse M1 + EMA M5, filtre anti-spread. Partage entre packs forex et or."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from core.indicators import ema
from core.pack import PackConfig
from core.spread_gate import apply_spread_gate, min_sl_distance
from core.types import ClosedBar, Quote, SignalIntent, SymbolSpec


class ImpulseEmaScalp:
    def __init__(self, pack: PackConfig):
        self.pack = pack
        self._used_bars: set[int] = set()
        self._entries_day = ""
        self._entries_count = 0
        self._cooldown_until: float = 0.0

    def _roll_day(self, moment: datetime) -> None:
        local = moment.astimezone(ZoneInfo(self.pack.session_tz))
        stamp = local.date().isoformat()
        if stamp != self._entries_day:
            self._entries_day = stamp
            self._entries_count = 0

    def evaluate(
        self,
        bars_fast: Sequence[ClosedBar],
        bars_slow: Sequence[ClosedBar] = (),
        quote: Optional[Quote] = None,
        spec: Optional[SymbolSpec] = None,
    ) -> Optional[SignalIntent]:
        if quote is None or spec is None:
            return None
        if len(bars_fast) < 2 or len(bars_slow) < self.pack.ema_period:
            return None
        moment = quote.server_time
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        self._roll_day(moment)
        if self._entries_count >= self.pack.max_trades_per_day:
            return None
        if moment.timestamp() < self._cooldown_until:
            return None

        bar = bars_fast[-1]
        if bar.time in self._used_bars:
            return None
        spread = quote.spread
        body = abs(bar.close - bar.open)
        if body < self.pack.impulse_spread_mult * spread:
            return None
        high_low = bar.high - bar.low
        if high_low <= 0:
            return None

        closes = [item.close for item in bars_slow]
        now_ema = ema(closes, self.pack.ema_period)
        prev_ema = ema(closes[:-1], self.pack.ema_period)
        close_pos = (bar.close - bar.low) / high_low
        buy = (
            bar.close > bar.open
            and close_pos >= 0.7
            and now_ema >= prev_ema
            and bar.close > now_ema
        )
        sell = (
            bar.close < bar.open
            and close_pos <= 0.3
            and now_ema <= prev_ema
            and bar.close < now_ema
        )
        if buy:
            side = "buy"
            entry = quote.ask
            sl_floor = min_sl_distance(spread, spec, self.pack.sl_spread_mult)
            sl = min(bar.low, entry - sl_floor)
            risk = entry - sl
            if risk <= 0:
                return None
            tp = entry + self.pack.reward_risk * risk
        elif sell:
            side = "sell"
            entry = quote.bid
            sl_floor = min_sl_distance(spread, spec, self.pack.sl_spread_mult)
            sl = max(bar.high, entry + sl_floor)
            risk = sl - entry
            if risk <= 0:
                return None
            tp = entry - self.pack.reward_risk * risk
        else:
            return None

        ok, _reason = apply_spread_gate(
            side,
            entry,
            sl,
            tp,
            spread,
            spec,
            self.pack.max_spread,
            tp_spread_mult=self.pack.tp_spread_mult,
            sl_spread_mult=self.pack.sl_spread_mult,
        )
        if not ok:
            return None

        self._used_bars.add(bar.time)
        self._entries_count += 1
        self._cooldown_until = moment.timestamp() + self.pack.cooldown_after_sl_seconds
        return SignalIntent(
            decision_id=f"{self.pack.id}:1.0:{quote.symbol}:{self.pack.fast_timeframe}:{bar.time}",
            symbol=quote.symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=self.pack.id,
        )
