"""Filtres de spread : un TP trop petit est refuse, un spread trop large aussi."""

from __future__ import annotations

from core.types import SymbolSpec


def broker_stop_distance(spec: SymbolSpec) -> float:
    tick = spec.trade_tick_size or spec.point or 0.0
    return max(0.0, float(spec.trade_stops_level) * tick)


def min_tp_distance(spread: float, spec: SymbolSpec, tp_spread_mult: float = 4.0) -> float:
    return max(float(spread) * float(tp_spread_mult), broker_stop_distance(spec))


def min_sl_distance(spread: float, spec: SymbolSpec, sl_spread_mult: float = 2.0) -> float:
    return max(float(spread) * float(sl_spread_mult), broker_stop_distance(spec))


def spread_too_wide(spread: float, max_spread: float) -> bool:
    return float(spread) > float(max_spread)


def apply_spread_gate(
    side: str,
    entry: float,
    sl: float,
    tp: float,
    spread: float,
    spec: SymbolSpec,
    max_spread: float,
    tp_spread_mult: float = 4.0,
    sl_spread_mult: float = 2.0,
) -> tuple[bool, str]:
    if spread_too_wide(spread, max_spread):
        return False, "SPREAD_TOO_WIDE"
    sl_need = min_sl_distance(spread, spec, sl_spread_mult)
    tp_need = min_tp_distance(spread, spec, tp_spread_mult)
    if side == "buy":
        sl_dist = entry - sl
        tp_dist = tp - entry
    else:
        sl_dist = sl - entry
        tp_dist = entry - tp
    if sl_dist < sl_need:
        return False, "SL_TOO_TIGHT"
    if tp_dist < tp_need:
        return False, "TP_TOO_SMALL"
    return True, "OK"
