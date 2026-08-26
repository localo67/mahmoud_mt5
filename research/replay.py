"""Parite exacte replay / backtest pour un jeu de donnees gele."""

from __future__ import annotations

from research.backtest import EventBacktest


def golden_replay(ticks: list[dict], bars: list[dict], signal_fn) -> dict:
    first = EventBacktest(ticks).run(bars, signal_fn)
    second = EventBacktest(ticks).run(bars, signal_fn)
    payload = {
        "trades": first.trades,
        "equity": first.equity,
    }
    if payload != {"trades": second.trades, "equity": second.equity}:
        raise AssertionError("replay non deterministe")
    return payload
