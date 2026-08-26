"""Machine d'etats ordre / deal / position. AMBIGUOUS n'est pas un etat terminal."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

AMBIGUOUS = "AMBIGUOUS"
CONFIRMED = "CONFIRMED"
NOT_SENT = "NOT_SENT"
VENUE_REJECTED = "VENUE_REJECTED"

TERMINAL_STATES = frozenset({"FILLED", "REJECTED", "CANCELED", "EXPIRED"})
ALLOWED = {
    None: frozenset({"INTENT_RECORDED"}),
    "INTENT_RECORDED": frozenset({"CHECKED", "REJECTED"}),
    "CHECKED": frozenset({"SUBMITTED", "REJECTED"}),
    "SUBMITTED": frozenset(
        {"ACCEPTED", "REJECTED", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED"}
    ),
    "ACCEPTED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED"}),
    "PARTIALLY_FILLED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED"}),
    "FILLED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELED": frozenset(),
    "EXPIRED": frozenset(),
}


@dataclass(frozen=True)
class OrderView:
    decision_id: str
    state: Optional[str] = None
    outcome_class: str = NOT_SENT
    filled_qty: float = 0.0
    requested_qty: float = 0.0
    deal_tickets: frozenset[int] = field(default_factory=frozenset)


def empty_order(decision_id: str, requested_qty: float = 0.02) -> OrderView:
    return OrderView(decision_id=decision_id, requested_qty=requested_qty)


def is_terminal_state(state: Optional[str]) -> bool:
    return state in TERMINAL_STATES


def can_resend(order: OrderView) -> bool:
    if order.outcome_class == AMBIGUOUS:
        return False
    if order.state in TERMINAL_STATES:
        return False
    if order.state in {"SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED"}:
        return False
    return True


def _normalize_kind(kind: str, payload: dict) -> str:
    if kind == "result":
        status = str(payload.get("status") or "")
        mapping = {
            "REJECTED": "rejected",
            "FILLED": "fill_final",
            "PARTIAL": "fill_partial",
            "UNKNOWN": "timeout",
        }
        return mapping.get(status, kind)
    aliases = {
        "order_intent": "intent",
        "order_checked": "check",
        "order_accepted": "accepted",
        "order_rejected": "rejected",
        "send": "accepted",
    }
    return aliases.get(kind, kind)


def _target_for(kind: str) -> Optional[str]:
    return {
        "intent": "INTENT_RECORDED",
        "check": "CHECKED",
        "send_attempt_started": "SUBMITTED",
        "accepted": "ACCEPTED",
        "fill_partial": "PARTIALLY_FILLED",
        "fill_final": "FILLED",
        "rejected": "REJECTED",
        "canceled": "CANCELED",
        "expired": "EXPIRED",
    }.get(kind)


def apply_event(order: OrderView, kind: str, payload: Optional[dict] = None) -> OrderView:
    payload = dict(payload or {})
    kind = _normalize_kind(kind, payload)
    if kind == "timeout":
        state = order.state or "SUBMITTED"
        return replace(order, state=state, outcome_class=AMBIGUOUS)

    target = _target_for(kind)
    if target is None:
        return order
    if order.state in TERMINAL_STATES:
        return order
    allowed = ALLOWED.get(order.state)
    if allowed is None or target not in allowed:
        return order

    filled = order.filled_qty
    deals = set(order.deal_tickets)
    if kind in {"fill_partial", "fill_final"}:
        deal = payload.get("deal_ticket")
        volume = float(payload.get("volume") or 0.0)
        if deal is not None:
            if int(deal) in deals:
                volume = 0.0
            else:
                deals.add(int(deal))
        filled = round(filled + volume, 8)
        if kind == "fill_partial":
            if order.requested_qty and filled + 1e-12 >= order.requested_qty:
                target = "FILLED"
            else:
                target = "PARTIALLY_FILLED"
        else:
            target = "FILLED"

    outcome = order.outcome_class
    if kind == "rejected":
        outcome = VENUE_REJECTED
    elif kind in {"accepted", "fill_partial", "fill_final", "check", "intent", "send_attempt_started"}:
        if outcome != AMBIGUOUS:
            if kind in {"accepted", "fill_partial", "fill_final"}:
                outcome = CONFIRMED
    return replace(
        order,
        state=target,
        filled_qty=filled,
        deal_tickets=frozenset(deals),
        outcome_class=outcome,
    )


def reduce_events(
    events: list[dict],
    decision_id: str,
    requested_qty: float = 0.0,
) -> OrderView:
    order = empty_order(decision_id, requested_qty=requested_qty)
    for event in events:
        order = apply_event(order, event.get("kind", ""), event.get("payload") or {})
    return order
