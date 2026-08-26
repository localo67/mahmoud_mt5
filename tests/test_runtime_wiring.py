import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

from automation import AutomationEngine
from core.data import ClosedBarMarketData
from core.execution import ExecutionGateway
from core.ledger import Ledger
from core.risk import RiskEngine
from fakes import FakeMT5
from mt5_client import MT5Client
from strategies.session_breakout import SessionBreakout
import strategy_engine as strategy_engine_module
from strategy_engine import StrategyEngine


def test_automation_assembles_deterministic_core(tmp_path) -> None:
    client = MT5Client(mt5_api=FakeMT5(), trading_mode="shadow")
    engine = AutomationEngine(
        application=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
        mt5_client=client,
        ledger_path=tmp_path / "ledger.sqlite",
        state_path=tmp_path / "risk.json",
        control_path=tmp_path / "control.json",
    )
    inner = engine.engine
    assert isinstance(inner.market_data, ClosedBarMarketData)
    assert isinstance(inner.decision, SessionBreakout)
    assert inner.pack.id == "session_breakout_xauusd"
    assert isinstance(inner.risk_engine, RiskEngine)
    assert isinstance(inner.execution, ExecutionGateway)
    assert isinstance(inner.ledger, Ledger)
    source = inspect.getsource(AutomationEngine.__init__)
    assert "EmaRsiStrategy" not in source
    assert "BreakoutRetestStrategy" not in source
    assert "EngulfingStrategy" not in source
    assert "RiskManager" not in source


def test_strategy_engine_does_not_call_ai_or_direct_open_order() -> None:
    source = inspect.getsource(strategy_engine_module)
    assert "ai.decide" not in source
    assert "open_order(" not in source
    assert "_execute_with_retry" not in source
    assert "_execute_decision" not in source
    assert inspect.signature(StrategyEngine.__init__).parameters["decision"].name == "decision"
