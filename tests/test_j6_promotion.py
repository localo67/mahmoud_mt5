from datetime import datetime, timezone

from ops.promotion import PromotionGates


def test_empty_evidence_is_nogo_for_every_stage() -> None:
    gates = PromotionGates()
    evidence = {
        "shadow_sessions": 0,
        "eligible_decisions": 0,
        "unexplained_divergences": 0,
        "paper_sessions": 0,
        "paper_round_trips": 0,
        "demo_sessions": 0,
        "demo_closed_trades": 0,
        "reconciliation_gaps": 0,
        "unauthorized_orders": 0,
        "code_changed_since_evidence": False,
    }
    assert gates.shadow(evidence).go is False
    assert gates.paper(evidence).go is False
    assert gates.demo(evidence).go is False


def test_shadow_requires_sessions_and_zero_divergence() -> None:
    gates = PromotionGates()
    almost = {
        "shadow_sessions": 20,
        "eligible_decisions": 50,
        "unexplained_divergences": 1,
        "unauthorized_orders": 0,
        "code_changed_since_evidence": False,
    }
    ready = dict(almost)
    ready["unexplained_divergences"] = 0
    assert gates.shadow(almost).go is False
    assert gates.shadow(ready).go is True
