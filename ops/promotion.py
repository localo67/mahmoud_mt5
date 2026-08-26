"""Portes de promotion shadow / paper / demo. Les fenetres empiriques restent a collecter."""

from __future__ import annotations

from dataclasses import dataclass


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
        if evidence.get("shadow_sessions", 0) < self.SHADOW_SESSIONS:
            reasons.append("insufficient shadow sessions")
        if evidence.get("eligible_decisions", 0) < self.SHADOW_DECISIONS:
            reasons.append("insufficient eligible decisions")
        if evidence.get("unexplained_divergences", 0) != 0:
            reasons.append("unexplained replay divergence")
        if evidence.get("unauthorized_orders", 0) != 0:
            reasons.append("unauthorized order")
        if evidence.get("code_changed_since_evidence"):
            reasons.append("evidence reset required after code change")
        return GateResult(not reasons, "shadow", reasons)

    def paper(self, evidence: dict) -> GateResult:
        reasons = []
        if not self.shadow(evidence).go and evidence.get("shadow_sessions", 0):
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
        if evidence.get("demo_sessions", 0) < self.DEMO_SESSIONS:
            reasons.append("insufficient demo sessions")
        if evidence.get("demo_closed_trades", 0) < self.DEMO_TRADES:
            reasons.append("insufficient demo closed trades")
        if evidence.get("reconciliation_gaps", 0) != 0:
            reasons.append("reconciliation gap")
        if evidence.get("unauthorized_orders", 0) != 0:
            reasons.append("unauthorized order")
        return GateResult(not reasons, "demo", reasons)
