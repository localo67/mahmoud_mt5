"""Interverrouillage live : reconnu, jamais execute sans nouvelle approbation."""

from __future__ import annotations

from core.specs import loss_at_stop
from core.types import SymbolSpec


class LiveInterlock:
    def __init__(self, mt5_client):
        self.mt5 = mt5_client

    def canary_allowed(self) -> bool:
        return False

    def reason(self) -> str:
        mode = getattr(self.mt5, "trading_mode", "unknown")
        if mode == "live":
            return "Mode live reconnu mais non implemente tant qu'une approbation separee n'est pas donnee."
        return "Canari live desactive."


def min_lot_risk_nogo(
    spec: SymbolSpec,
    equity: float,
    risk_pct: float,
    stop_ticks: int,
) -> bool:
    budget = equity * (risk_pct / 100.0)
    stop_distance = stop_ticks * spec.trade_tick_size
    entry = 2500.0
    sl = entry - stop_distance
    min_loss = abs(loss_at_stop(spec.volume_min, spec, entry, sl, "buy"))
    return min_loss > budget
