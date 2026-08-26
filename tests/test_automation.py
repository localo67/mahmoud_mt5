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
