"""Backtest evenementiel : signal apres cloture, fill sur le tick suivant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)


class EventBacktest:
    def __init__(
        self,
        ticks: list[dict],
        commission: float = 0.0,
        slippage: float = 0.0,
        bar_period_ms: int = 300_000,
    ):
        self.ticks = sorted(ticks, key=lambda item: item["time_msc"])
        self.commission = commission
        self.slippage = slippage
        self.bar_period_ms = bar_period_ms

    def run(self, bars: list[dict], signal_fn: Callable) -> BacktestResult:
        closed: list[dict] = []
        pending: Optional[dict] = None
        position: Optional[dict] = None
        trades: list[dict] = []
        equity = [0.0]
        bar_index = 0
        ordered_bars = sorted(bars, key=lambda item: item["time"])

        for tick in self.ticks:
            now = tick["time_msc"]
            while bar_index < len(ordered_bars):
                bar = ordered_bars[bar_index]
                close_time = int(bar["time"]) + self.bar_period_ms
                if close_time > now:
                    break
                closed.append(bar)
                bar_index += 1
                if position is None and pending is None:
                    intent = signal_fn(list(closed), close_time)
                    if intent:
                        pending = {**intent, "signal_ms": close_time}

            if pending is not None and now > pending["signal_ms"] and position is None:
                side = pending["side"]
                raw = tick["ask"] if side == "buy" else tick["bid"]
                price = raw + self.slippage if side == "buy" else raw - self.slippage
                position = {
                    "side": side,
                    "entry_price": price,
                    "sl": pending["sl"],
                    "tp": pending["tp"],
                    "entry_ms": now,
                    "commission": self.commission,
                }
                pending = None

            if position is not None:
                exit_price = self._hit(position, tick)
                if exit_price is not None:
                    pnl = self._pnl(position, exit_price) - position["commission"]
                    trades.append(
                        {
                            "side": position["side"],
                            "entry_price": position["entry_price"],
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "entry_ms": position["entry_ms"],
                            "exit_ms": now,
                        }
                    )
                    equity.append(equity[-1] + pnl)
                    position = None
        return BacktestResult(trades=trades, equity=equity)

    @staticmethod
    def _hit(position: dict, tick: dict) -> Optional[float]:
        side = position["side"]
        if side == "buy":
            if tick["bid"] <= position["sl"]:
                return position["sl"]
            if tick["bid"] >= position["tp"]:
                return position["tp"]
            return None
        if tick["ask"] >= position["sl"]:
            return position["sl"]
        if tick["ask"] <= position["tp"]:
            return position["tp"]
        return None

    @staticmethod
    def _pnl(position: dict, exit_price: float) -> float:
        if position["side"] == "buy":
            return exit_price - position["entry_price"]
        return position["entry_price"] - exit_price
