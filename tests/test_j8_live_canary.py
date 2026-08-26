from core.live_interlock import LiveInterlock, min_lot_risk_nogo
from core.specs import SymbolSpec
from mt5_client import MT5Client


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
    volume_min=1.0,
    volume_max=5.0,
    volume_step=1.0,
    volume_limit=10.0,
    trade_stops_level=10,
    trade_freeze_level=0,
    filling_mode=1,
)


def test_live_mode_is_recognized_but_not_implemented() -> None:
    client = MT5Client(mt5_api=object(), trading_mode="live")
    lock = LiveInterlock(client)
    assert lock.canary_allowed() is False
    assert "non implemente" in lock.reason().lower() or "not implemented" in lock.reason().lower()


def test_min_lot_above_risk_is_nogo() -> None:
    assert min_lot_risk_nogo(GOLD, equity=1_000, risk_pct=0.1, stop_ticks=100) is True
    small = GOLD.__class__(**{**GOLD.__dict__, "volume_min": 0.01, "volume_step": 0.01})
    assert min_lot_risk_nogo(small, equity=10_000, risk_pct=0.5, stop_ticks=10) is False
