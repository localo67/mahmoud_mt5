from types import SimpleNamespace

import pytest

import automation


class FakeStrategyEngine:
    def __init__(self, **kwargs):
        self.enabled = True
        self.chat_id = None

    async def run(self):
        return None


def _replace_automation_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(automation, "RiskManager", lambda: SimpleNamespace())
    monkeypatch.setattr(automation, "NewsFilter", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(automation, "NewsCollector", lambda: SimpleNamespace())
    monkeypatch.setattr(automation, "FMPCollector", lambda: SimpleNamespace())
    monkeypatch.setattr(automation, "AITrader", lambda: SimpleNamespace())
    monkeypatch.setattr(
        automation,
        "EmaRsiStrategy",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        automation,
        "BreakoutRetestStrategy",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        automation,
        "EngulfingStrategy",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(automation, "StrategyEngine", FakeStrategyEngine)


def test_automation_is_off_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    _replace_automation_dependencies(monkeypatch)

    engine = automation.AutomationEngine(
        application=SimpleNamespace(),
        mt5_client=SimpleNamespace(is_trading_armed=False),
    )

    assert engine.enabled is False
    assert engine.engine.enabled is False
