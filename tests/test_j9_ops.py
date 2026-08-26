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
