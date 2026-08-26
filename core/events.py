"""Vocabulaire d'evenements canoniques shadow/demo."""

from __future__ import annotations

CANONICAL_KINDS = (
    "decision_evaluated",
    "risk_accepted",
    "risk_rejected",
    "intent",
    "check",
    "send_attempt_started",
    "accepted",
    "rejected",
    "fill_partial",
    "fill_final",
    "position_opened",
    "position_closed",
    "canceled",
    "timeout",
    "reconcile",
    "entry_halt_raised",
    "entry_halt_cleared",
)

PARITY_KINDS = (
    "intent",
    "check",
    "accepted",
    "rejected",
    "fill_partial",
    "fill_final",
    "canceled",
    "reconcile",
)


def normalize_events(events: list[dict]) -> list[dict]:
    """Compare shadow et demo sans identifiants broker."""
    normalized = []
    for event in events:
        kind = event.get("kind")
        if kind in {"send", "order_accepted"}:
            kind = "accepted"
        if kind in {"order_intent"}:
            kind = "intent"
        if kind in {"order_checked"}:
            kind = "check"
        if kind in {"result"}:
            status = str((event.get("payload") or {}).get("status") or "")
            kind = {
                "FILLED": "fill_final",
                "PARTIAL": "fill_partial",
                "REJECTED": "rejected",
                "UNKNOWN": "timeout",
            }.get(status, kind)
        if kind not in PARITY_KINDS:
            continue
        payload = dict(event.get("payload") or {})
        for key in (
            "order_id",
            "deal_id",
            "position_id",
            "ticket",
            "deal",
            "deal_ticket",
            "order_ticket",
            "comment",
            "retcode",
            "backend",
            "simulated",
            "send_attempt_id",
            "client_order_id",
        ):
            payload.pop(key, None)
        normalized.append({"kind": kind, "payload": payload})
    return normalized
