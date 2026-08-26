from types import SimpleNamespace

import automation


def test_automation_is_off_at_startup(tmp_path) -> None:
    engine = automation.AutomationEngine(
        application=SimpleNamespace(),
        mt5_client=SimpleNamespace(is_trading_armed=False, trading_mode="off"),
        ledger_path=tmp_path / "ledger.sqlite",
        state_path=tmp_path / "risk.json",
        control_path=tmp_path / "control.json",
    )

    assert engine.enabled is False
    assert engine.engine.enabled is False
    assert engine.engine.decision is engine.decision
    assert engine.execution is not None


def test_automation_is_on_in_demo(tmp_path) -> None:
    engine = automation.AutomationEngine(
        application=SimpleNamespace(),
        mt5_client=SimpleNamespace(is_trading_armed=False, trading_mode="demo"),
        ledger_path=tmp_path / "ledger.sqlite",
        state_path=tmp_path / "risk.json",
        control_path=tmp_path / "control.json",
    )

    assert engine.enabled is True
    assert engine.engine.enabled is True
    assert engine.pack.id == "session_breakout_xauusd"


def test_automation_can_load_scalp_pack(tmp_path) -> None:
    engine = automation.AutomationEngine(
        application=None,
        mt5_client=SimpleNamespace(is_trading_armed=False, trading_mode="demo"),
        ledger_path=tmp_path / "ledger.sqlite",
        state_path=tmp_path / "risk.json",
        control_path=tmp_path / "control.json",
        pack_id="scalp_eurusd_m1",
    )
    assert engine.pack.symbol == "EURUSD"
    assert engine.engine._fast_tf == "M1"
    assert engine.news_filter.fail_safe is False
