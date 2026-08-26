from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.risk import RiskEngine
from core.types import AccountSnapshot, Quote, RiskLimits, SignalIntent, SymbolSpec


GOLD = SymbolSpec(
    name="XAUUSD",
    digits=2,
    point=0.01,
    trade_tick_size=0.01,
    trade_tick_value=1.0,
    trade_tick_value_profit=1.0,
    trade_tick_value_loss=1.0,
    trade_contract_size=100.0,
    trade_calc_mode=0,
    currency_profit="USD",
    currency_margin="USD",
    volume_min=0.01,
    volume_max=5.0,
    volume_step=0.01,
    volume_limit=10.0,
    trade_stops_level=10,
    trade_freeze_level=0,
    filling_mode=1,
)


def _intent() -> SignalIntent:
    return SignalIntent(
        decision_id="dec-1",
        symbol="XAUUSD",
        side="buy",
        entry=2500.0,
        sl=2499.0,
        tp=2502.0,
        reason="test",
    )


def _quote(now: datetime, age_seconds: int = 1) -> Quote:
    ts = now - timedelta(seconds=age_seconds)
    return Quote(
        symbol="XAUUSD",
        bid=2500.0,
        ask=2500.2,
        time_msc=int(ts.timestamp() * 1000),
        server_time=ts,
    )


def _account(**kwargs) -> AccountSnapshot:
    values = {
        "equity": 10_000.0,
        "balance": 10_000.0,
        "currency": "USD",
        "free_margin": 10_000.0,
        "floating_pnl": 0.0,
        "commission": 0.0,
        "swap": 0.0,
        "open_positions": 0,
    }
    values.update(kwargs)
    return AccountSnapshot(**values)


def test_size_stays_within_risk_budget_to_one_volume_step() -> None:
    engine = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
        state_path=None,
    )
    decision = engine.decide(_intent(), _quote(datetime(2026, 8, 25, 15, tzinfo=timezone.utc)), _account())
    assert decision.allowed is True
    loss = abs(engine.expected_loss(decision.volume, _intent()))
    budget = 10_000.0 * 0.005
    assert loss <= budget + GOLD.volume_step * GOLD.trade_tick_value_loss * (
        abs(_intent().entry - _intent().sl) / GOLD.trade_tick_size
    )


def test_stale_quote_is_rejected() -> None:
    now = datetime(2026, 8, 25, 15, tzinfo=timezone.utc)
    engine = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: now,
        state_path=None,
    )
    decision = engine.decide(_intent(), _quote(now, age_seconds=180), _account())
    assert decision.allowed is False
    assert decision.reason == "STALE_QUOTE"


def test_kill_switch_survives_restart_and_is_not_hot_resettable(tmp_path: Path) -> None:
    path = tmp_path / "risk-state.json"
    now = datetime(2026, 8, 25, 15, tzinfo=timezone.utc)
    first = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: now,
        state_path=path,
    )
    first.trip_kill_switch("manual")
    first.reset_daily()

    second = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: now,
        state_path=path,
    )
    decision = second.decide(_intent(), _quote(now), _account())
    assert second.kill_switch is True
    assert decision.allowed is False
    assert decision.reason == "KILL_SWITCH"


def test_corrupted_state_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "risk-state.json"
    path.write_text("{not-json", encoding="utf-8")
    engine = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
        state_path=path,
    )
    assert engine.kill_switch is True
    decision = engine.decide(
        _intent(),
        _quote(datetime(2026, 8, 25, 15, tzinfo=timezone.utc)),
        _account(),
    )
    assert decision.allowed is False


def test_consecutive_losses_use_realized_pnl() -> None:
    engine = RiskEngine(
        limits=RiskLimits(risk_pct=0.5, max_daily_loss=50, max_consecutive_losses=2),
        spec=GOLD,
        now=lambda: datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
        state_path=None,
    )
    engine.record_closed_trade(-2.0, commission=-0.2, swap=-0.1)
    engine.record_closed_trade(-1.0, commission=0.0, swap=0.0)
    assert engine.consecutive_losses == 2
    decision = engine.decide(
        _intent(),
        _quote(datetime(2026, 8, 25, 15, tzinfo=timezone.utc)),
        _account(floating_pnl=-1.0),
    )
    assert decision.allowed is False
    assert decision.reason == "CONSECUTIVE_LOSSES"
