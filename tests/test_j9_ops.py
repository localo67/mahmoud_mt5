from ops.control import OperationalControl
from ops.decommission import DecommissionPolicy
from ops.monitor import Monitor, MonitorHalt


def test_monitor_halts_on_stale_unknown_position_or_kill() -> None:
    monitor = Monitor()
    assert monitor.observe({"stale_quote": True}).halt is True
    assert monitor.observe({"unknown_position": True}).halt is True
    assert monitor.observe({"kill_switch": True}).halt is True
    assert monitor.observe({"reconciliation_ok": True, "stale_quote": False}).halt is False


def test_decommission_archives_and_revokes() -> None:
    policy = DecommissionPolicy()
    result = policy.run(reason="edge disappeared")
    assert result["service_disabled"] is True
    assert result["access_revoked"] is True
    assert "auto-optimisation" not in result["reason"].lower()


def test_halt_entries_keeps_position_management(tmp_path) -> None:
    controls = OperationalControl(tmp_path / "control.json")
    monitor = Monitor(controls)
    halt = monitor.observe({"missing_sl": True})
    assert halt.halt is True
    assert halt.reason == "MISSING_SL"
    assert controls.state.entries_allowed is False
    assert controls.state.position_management_enabled is True
    assert controls.state.emergency_exit_requested is False


def test_reconciliation_error_halts_entries_only(tmp_path) -> None:
    controls = OperationalControl(tmp_path / "control.json")
    monitor = Monitor(controls)
    monitor.observe({"reconciliation_ok": False})
    assert controls.state.entries_allowed is False
    assert controls.state.position_management_enabled is True


def test_control_state_survives_restart(tmp_path) -> None:
    path = tmp_path / "control.json"
    first = OperationalControl(path)
    first.halt_entries("STALE_QUOTE")
    second = OperationalControl(path)
    assert second.state.entries_allowed is False
    assert second.state.reason == "STALE_QUOTE"
