from datetime import datetime, timezone

from research.cards import load_card
from research.validation import (
    HoldoutGuard,
    block_bootstrap_expectancy,
    cost_stress,
    evaluate_session_breakout,
    walk_forward,
)
from strategies.session_breakout import SessionBreakout


def test_research_card_is_frozen() -> None:
    card = load_card("session_breakout")
    assert card["name"] == "session_breakout"
    assert card["legacy_breakout_retest"] is False
    assert card["params"]["opening_range_minutes"] == 30
    assert card["params"]["attempts_per_session"] == 1
    assert card["allow_overnight"] is False
    assert "holdout" in card["splits"]


def test_session_breakout_fires_once_after_range() -> None:
    strategy = SessionBreakout()
    range_bars = [
        {"time": 1_700_000_000 + i * 300, "open": 2500.0, "high": 2501.0, "low": 2499.0, "close": 2500.0}
        for i in range(6)
    ]
    breakout = {
        "time": 1_700_000_000 + 6 * 300,
        "open": 2501.0,
        "high": 2503.0,
        "low": 2500.8,
        "close": 2502.5,
    }
    quote = {"bid": 2502.5, "ask": 2502.7, "spread": 0.2}
    spec_buffer = 0.2
    first = strategy.evaluate(range_bars + [breakout], quote, range_start=1_700_000_000, buffer=spec_buffer)
    second = strategy.evaluate(range_bars + [breakout], quote, range_start=1_700_000_000, buffer=spec_buffer)
    assert first is not None
    assert first.side == "buy"
    assert first.sl <= 2499.0
    assert second is None


def test_walk_forward_holdout_bootstrap_and_cost_stress() -> None:
    sessions = evaluate_session_breakout(_synthetic_sessions())
    folds = walk_forward(sessions, fold_size=10)
    assert len(folds) >= 2
    assert all("oos" in fold for fold in folds)

    guard = HoldoutGuard()
    holdout = guard.consult(sessions[-20:])
    try:
        guard.consult(sessions[-20:])
        raise AssertionError("holdout must be readable only once")
    except RuntimeError:
        pass

    ci = block_bootstrap_expectancy(holdout, block=5, draws=200, seed=7)
    stressed = cost_stress(holdout, spread_mult=2.0, slippage_mult=2.0)
    assert "low_95" in ci
    assert "expectancy" in stressed
    assert guard.consulted is True


def _synthetic_sessions() -> list[dict]:
    rows = []
    for index in range(60):
        win = index % 3 != 0
        pnl = 1.2 if win else -1.0
        rows.append(
            {
                "session": index,
                "pnl": pnl,
                "r": 1.2 if win else -1.0,
                "spread": 0.2,
                "slippage": 0.05,
                "regime": "trend" if win else "chop",
            }
        )
    return rows
