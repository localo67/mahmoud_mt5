"""Portes de promotion shadow / paper / demo. Les fenetres empiriques restent a collecter."""

from __future__ import annotations

from dataclasses import dataclass

from core.events import normalize_events


@dataclass(frozen=True)
class GateResult:
    go: bool
    stage: str
    reasons: list[str]


class PromotionGates:
    SHADOW_SESSIONS = 20
    SHADOW_DECISIONS = 50
    PAPER_SESSIONS = 20
    PAPER_ROUND_TRIPS = 30
    DEMO_SESSIONS = 60
    DEMO_TRADES = 100

    def shadow(self, evidence: dict) -> GateResult:
        reasons = []
        if evidence.get("code_changed_since_evidence"):
            reasons.append("evidence reset required after code change")
        if evidence.get("shadow_sessions", 0) < self.SHADOW_SESSIONS:
            reasons.append("insufficient shadow sessions")
        if evidence.get("eligible_decisions", 0) < self.SHADOW_DECISIONS:
            reasons.append("insufficient eligible decisions")
        if evidence.get("unexplained_divergences", 0) != 0:
            reasons.append("unexplained replay divergence")
        if evidence.get("unauthorized_orders", 0) != 0:
            reasons.append("unauthorized order")
        return GateResult(not reasons, "shadow", reasons)

    def paper(self, evidence: dict) -> GateResult:
        reasons = []
        if evidence.get("code_changed_since_evidence"):
            reasons.append("evidence reset required after code change")
        if not self.shadow(evidence).go:
            reasons.append("shadow not passed")
        if evidence.get("paper_sessions", 0) < self.PAPER_SESSIONS:
            reasons.append("insufficient paper sessions")
        if evidence.get("paper_round_trips", 0) < self.PAPER_ROUND_TRIPS:
            reasons.append("insufficient paper round trips")
        if evidence.get("unauthorized_orders", 0) != 0:
            reasons.append("unauthorized order")
        return GateResult(not reasons, "paper", reasons)

    def demo(self, evidence: dict) -> GateResult:
        reasons = []
        if evidence.get("code_changed_since_evidence"):
            reasons.append("evidence reset required after code change")
        if not self.paper(evidence).go:
            reasons.append("paper not passed")
        if evidence.get("demo_sessions", 0) < self.DEMO_SESSIONS:
            reasons.append("insufficient demo sessions")
        if evidence.get("demo_closed_trades", 0) < self.DEMO_TRADES:
            reasons.append("insufficient demo closed trades")
        if evidence.get("reconciliation_gaps", 0) != 0:
            reasons.append("reconciliation gap")
        if evidence.get("unauthorized_orders", 0) != 0:
            reasons.append("unauthorized order")
        return GateResult(not reasons, "demo", reasons)


def evidence_from_ledger(ledger, meta: dict | None = None) -> dict:
    meta = dict(meta or {})
    events = ledger.all_events()
    kinds = [item["kind"] for item in events]
    fills = kinds.count("fill_final") + kinds.count("result")
    decisions = kinds.count("decision_evaluated") + kinds.count("intent")
    unauthorized = meta.get("unauthorized_orders", 0)
    if any(item.get("payload", {}).get("unauthorized") for item in events):
        unauthorized += 1
    current_artifact = meta.get("current_artifact_id")
    evidence_artifact = meta.get("artifact_id")
    code_changed = bool(meta.get("code_changed_since_evidence"))
    if current_artifact and evidence_artifact and current_artifact != evidence_artifact:
        code_changed = True
    return {
        "shadow_sessions": int(meta.get("shadow_sessions", 0)),
        "eligible_decisions": int(meta.get("eligible_decisions", decisions)),
        "unexplained_divergences": int(meta.get("unexplained_divergences", 0)),
        "paper_sessions": int(meta.get("paper_sessions", 0)),
        "paper_round_trips": int(meta.get("paper_round_trips", 0)),
        "demo_sessions": int(meta.get("demo_sessions", 0)),
        "demo_closed_trades": int(meta.get("demo_closed_trades", fills)),
        "reconciliation_gaps": int(meta.get("reconciliation_gaps", 0)),
        "unauthorized_orders": unauthorized,
        "code_changed_since_evidence": code_changed,
        "normalized_events": normalize_events(events),
    }
