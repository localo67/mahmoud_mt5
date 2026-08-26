"""Fournisseur de donnees : bougies cloturees uniquement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from core.types import ClosedBar, Quote, SymbolSpec


def bar_from_rate(rate) -> ClosedBar:
    if hasattr(rate, "time"):
        return ClosedBar(
            time=int(rate.time),
            open=float(rate.open),
            high=float(rate.high),
            low=float(rate.low),
            close=float(rate.close),
            tick_volume=int(getattr(rate, "tick_volume", 0)),
            spread=int(getattr(rate, "spread", 0)),
            real_volume=int(getattr(rate, "real_volume", 0)),
        )
    return ClosedBar(
        time=int(rate[0]),
        open=float(rate[1]),
        high=float(rate[2]),
        low=float(rate[3]),
        close=float(rate[4]),
        tick_volume=int(rate[5]) if len(rate) > 5 else 0,
        spread=int(rate[6]) if len(rate) > 6 else 0,
        real_volume=int(rate[7]) if len(rate) > 7 else 0,
    )


class ClosedBarMarketData:
    def __init__(self, mt5_client, clock=None):
        self.mt5 = mt5_client
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def closed_bars(self, symbol: str, timeframe: str, count: int) -> Sequence[ClosedBar]:
        rates = await self.mt5.get_closed_rates(symbol, timeframe, count)
        if not rates:
            return []
        return [bar_from_rate(rate) for rate in rates]

    async def quote(self, symbol: str) -> Quote:
        tick = await self.mt5.get_current_price(symbol)
        server_time = datetime.fromtimestamp(int(tick["time"]), tz=timezone.utc)
        return Quote(
            symbol=symbol,
            bid=float(tick["bid"]),
            ask=float(tick["ask"]),
            time_msc=int(tick.get("time_msc") or tick["time"] * 1000),
            server_time=server_time,
        )

    async def specs(self, symbol: str) -> Optional[SymbolSpec]:
        info = await self.mt5.get_symbol_info(symbol)
        if not info:
            return None
        required = (
            "point",
            "trade_tick_size",
            "volume_min",
            "volume_step",
            "filling_mode",
        )
        if any(info.get(key) is None for key in required):
            return None
        return SymbolSpec(
            name=info.get("symbol") or symbol,
            digits=int(info.get("digits") or 2),
            point=float(info["point"]),
            trade_tick_size=float(info["trade_tick_size"]),
            trade_tick_value=float(info.get("trade_tick_value") or 0.0),
            trade_tick_value_profit=float(info.get("trade_tick_value_profit") or 0.0),
            trade_tick_value_loss=float(info.get("trade_tick_value_loss") or 0.0),
            trade_contract_size=float(info.get("trade_contract_size") or 0.0),
            trade_calc_mode=int(info.get("trade_calc_mode") or 0),
            currency_profit=str(info.get("currency_profit") or ""),
            currency_margin=str(info.get("currency_margin") or ""),
            volume_min=float(info["volume_min"]),
            volume_max=float(info.get("volume_max") or info["volume_min"]),
            volume_step=float(info["volume_step"]),
            volume_limit=float(info.get("volume_limit") or 0.0),
            trade_stops_level=int(info.get("trade_stops_level") or 0),
            trade_freeze_level=int(info.get("trade_freeze_level") or 0),
            filling_mode=int(info["filling_mode"]),
        )
