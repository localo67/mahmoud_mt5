from core.interfaces import (
    DecisionEngine,
    ExecutionGateway,
    MarketDataProvider,
    RiskEngine,
)


def test_core_interfaces_are_importable() -> None:
    assert MarketDataProvider is not None
    assert DecisionEngine is not None
    assert RiskEngine is not None
    assert ExecutionGateway is not None
