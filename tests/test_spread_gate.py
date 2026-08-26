from core.pack import load_pack
from core.spread_gate import apply_spread_gate, spread_too_wide
from helpers_runtime import GOLD


def test_spread_too_wide() -> None:
    assert spread_too_wide(0.00020, 0.00015) is True
    assert spread_too_wide(0.00010, 0.00015) is False


def test_tp_too_small_is_rejected() -> None:
    spec = load_pack("scalp_eurusd_m1").fallback_spec
    ok, reason = apply_spread_gate(
        "buy",
        entry=1.10000,
        sl=1.09970,
        tp=1.10010,
        spread=0.00010,
        spec=spec,
        max_spread=0.00015,
        tp_spread_mult=4.0,
        sl_spread_mult=2.0,
    )
    assert ok is False
    assert reason == "TP_TOO_SMALL"


def test_wide_enough_tp_passes() -> None:
    ok, reason = apply_spread_gate(
        "buy",
        entry=2500.20,
        sl=2499.00,
        tp=2502.00,
        spread=0.20,
        spec=GOLD,
        max_spread=0.40,
        tp_spread_mult=4.0,
        sl_spread_mult=2.0,
    )
    assert ok is True
    assert reason == "OK"
