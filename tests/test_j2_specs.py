from core.specs import SymbolSpec, round_price, round_volume_down
from core.types import RiskDecision


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


def test_volume_rounds_down_to_step() -> None:
    assert round_volume_down(0.029, GOLD) == 0.02
    assert round_volume_down(0.01, GOLD) == 0.01
    assert round_volume_down(0.009, GOLD) == 0.0


def test_price_rounds_to_tick_size() -> None:
    assert round_price(2500.124, GOLD) == 2500.12
    assert round_price(2500.125, GOLD) == 2500.13


def test_min_lot_above_risk_budget_is_wait() -> None:
    from core.risk import size_order

    decision = size_order(
        equity=1_000.0,
        risk_pct=0.1,
        spec=GOLD,
        side="buy",
        entry=2500.0,
        sl=2490.0,
        account_currency="USD",
    )
    assert isinstance(decision, RiskDecision)
    assert decision.allowed is False
    assert decision.volume == 0.0
    assert decision.reason == "MIN_LOT_EXCEEDS_RISK"
