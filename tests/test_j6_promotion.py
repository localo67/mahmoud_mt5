from datetime import datetime, timezone

from ops.promotion import PromotionGates, evidence_from_ledger


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


def _full_evidence(**overrides) -> dict:
    payload = {
        "shadow_sessions": 20,
        "eligible_decisions": 50,
        "unexplained_divergences": 0,
        "paper_sessions": 20,
        "paper_round_trips": 30,
        "demo_sessions": 60,
        "demo_closed_trades": 100,
        "reconciliation_gaps": 0,
        "unauthorized_orders": 0,
        "code_changed_since_evidence": False,
    }
    payload.update(overrides)
    return payload


def test_paper_requires_shadow_go() -> None:
    gates = PromotionGates()
    paper_only = _full_evidence(shadow_sessions=0, eligible_decisions=0)
    assert gates.paper(paper_only).go is False
    assert gates.paper(_full_evidence()).go is True


def test_demo_requires_paper_go() -> None:
    gates = PromotionGates()
    demo_only = _full_evidence(paper_sessions=0, paper_round_trips=0, shadow_sessions=0)
    assert gates.demo(demo_only).go is False
    assert gates.demo(_full_evidence()).go is True


def test_code_change_resets_all_gates() -> None:
    gates = PromotionGates()
    changed = _full_evidence(code_changed_since_evidence=True)
    assert gates.shadow(changed).go is False
    assert gates.paper(changed).go is False
    assert gates.demo(changed).go is False


def test_evidence_from_ledger_marks_artifact_mismatch(tmp_path) -> None:
    from core.ledger import Ledger

    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.append("dec-1", "intent", {"symbol": "XAUUSD"})
    ledger.append("dec-1", "fill_final", {"volume": 0.01})
    evidence = evidence_from_ledger(
        ledger,
        {
            "artifact_id": "aaa",
            "current_artifact_id": "bbb",
            "shadow_sessions": 20,
            "eligible_decisions": 50,
        },
    )
    assert evidence["code_changed_since_evidence"] is True
    assert evidence["normalized_events"]
