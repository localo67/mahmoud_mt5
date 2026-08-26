"""Walk-forward, holdout unique, bootstrap par blocs et stress de couts."""

from __future__ import annotations

import random
from typing import Optional


class HoldoutGuard:
    def __init__(self):
        self.consulted = False
        self._snapshot: Optional[list[dict]] = None

    def consult(self, rows: list[dict]) -> list[dict]:
        if self.consulted:
            raise RuntimeError("holdout already consulted; retuning is forbidden")
        self.consulted = True
        self._snapshot = list(rows)
        return self._snapshot


def evaluate_session_breakout(sessions: list[dict]) -> list[dict]:
    required = {"session", "pnl", "r"}
    for row in sessions:
        missing = required - set(row)
        if missing:
            raise ValueError(f"incomplete session metrics: {missing}")
    return list(sessions)


def walk_forward(sessions: list[dict], fold_size: int) -> list[dict]:
    folds = []
    start = 0
    while start + 2 * fold_size <= len(sessions):
        train = sessions[start:start + fold_size]
        oos = sessions[start + fold_size:start + 2 * fold_size]
        folds.append(
            {
                "train": train,
                "oos": oos,
                "train_expectancy": _mean([row["r"] for row in train]),
                "oos_expectancy": _mean([row["r"] for row in oos]),
            }
        )
        start += fold_size
    return folds


def block_bootstrap_expectancy(
    rows: list[dict],
    block: int,
    draws: int,
    seed: int,
) -> dict:
    values = [row["r"] for row in rows]
    if not values:
        return {"mean": 0.0, "low_95": 0.0}
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        sample = []
        while len(sample) < len(values):
            index = rng.randrange(0, max(1, len(values) - block + 1))
            sample.extend(values[index:index + block])
        sample = sample[:len(values)]
        means.append(_mean(sample))
    means.sort()
    low_index = max(0, int(0.05 * len(means)) - 1)
    return {"mean": _mean(means), "low_95": means[low_index]}


def cost_stress(rows: list[dict], spread_mult: float, slippage_mult: float) -> dict:
    stressed = []
    for row in rows:
        extra = row.get("spread", 0.0) * (spread_mult - 1.0) + row.get("slippage", 0.0) * (
            slippage_mult - 1.0
        )
        stressed.append(row["pnl"] - extra)
    return {"expectancy": _mean(stressed), "n": len(stressed)}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
