import asyncio

import pytest

from core.ai_veto import AIVeto, VetoDecision
from research.cards import load_card


def test_challenger_cards_are_separate() -> None:
    momentum = load_card("momentum")
    mean_rev = load_card("mean_reversion")
    champion = load_card("session_breakout")
    assert momentum["holdout"] != champion["splits"]["holdout"]
    assert mean_rev["holdout"] != momentum["holdout"]
    assert momentum["combinable_with_champion"] is False


@pytest.mark.asyncio
async def test_ai_veto_cannot_invent_trade_fields() -> None:
    veto = AIVeto(provider=lambda prompt: {"decision": "ALLOW", "reason": "ok"})
    result = await veto.review(signal_side="buy", headline="FOMC later")
    assert isinstance(result, VetoDecision)
    assert result.action in {"ALLOW", "VETO"}
    assert result.side is None
    assert result.volume is None
    assert result.sl is None
    assert result.tp is None


@pytest.mark.asyncio
async def test_ai_timeout_or_invalid_is_veto() -> None:
    async def hang(_prompt):
        await asyncio.sleep(0.05)
        return {"decision": "ALLOW"}

    veto = AIVeto(provider=hang, timeout_seconds=0.001)
    result = await veto.review(signal_side="sell", headline="nfp")
    assert result.action == "VETO"


def test_runtime_does_not_import_directional_ai() -> None:
    import inspect

    import automation
    import strategy_engine

    assert "AIVeto" not in inspect.getsource(automation)
    assert "AITrader" not in inspect.getsource(automation)
    assert "ai.decide" not in inspect.getsource(strategy_engine)
    assert "open_order(" not in inspect.getsource(strategy_engine)
