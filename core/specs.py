"""Arrondis et specifications broker, sans constante de pip."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from core.types import SymbolSpec

__all__ = ["SymbolSpec", "round_price", "round_volume_down", "loss_at_stop"]


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def round_price(price: float, spec: SymbolSpec) -> float:
    tick = _decimal(spec.trade_tick_size)
    if tick <= 0:
        return price
    quantized = (_decimal(price) / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
    return float(quantized)


def round_volume_down(volume: float, spec: SymbolSpec) -> float:
    step = _decimal(spec.volume_step)
    if step <= 0:
        return 0.0
    steps = (_decimal(volume) / step).to_integral_value(rounding=ROUND_DOWN)
    rounded = float(steps * step)
    if rounded < spec.volume_min and volume < spec.volume_min:
        return 0.0
    return min(spec.volume_max, rounded)


def ticks_between(price_a: float, price_b: float, spec: SymbolSpec) -> float:
    tick = spec.trade_tick_size or spec.point
    if tick <= 0:
        raise ValueError("tick size indeterminable")
    return abs(price_a - price_b) / tick


def loss_at_stop(volume: float, spec: SymbolSpec, entry: float, sl: float, side: str) -> float:
    distance = ticks_between(entry, sl, spec)
    tick_value = spec.trade_tick_value_loss or spec.trade_tick_value
    signed = distance * tick_value * volume
    return -abs(signed)
