from core.order_state import (
    AMBIGUOUS,
    CONFIRMED,
    apply_event,
    can_resend,
    empty_order,
    is_terminal_state,
)


def test_valid_lifecycle_intent_to_filled() -> None:
    order = empty_order("dec-1")
    order = apply_event(order, "intent")
    assert order.state == "INTENT_RECORDED"
    order = apply_event(order, "check")
    assert order.state == "CHECKED"
    order = apply_event(order, "send_attempt_started")
    assert order.state == "SUBMITTED"
    order = apply_event(order, "accepted")
    assert order.state == "ACCEPTED"
    order = apply_event(order, "fill_final", {"volume": 0.01})
    assert order.state == "FILLED"
    assert order.outcome_class == CONFIRMED
    assert is_terminal_state(order.state)


def test_submitted_can_fill_before_accepted() -> None:
    order = empty_order("dec-2")
    for kind in ("intent", "check", "send_attempt_started", "fill_final"):
        order = apply_event(order, kind, {"volume": 0.01})
    assert order.state == "FILLED"
    late = apply_event(order, "accepted")
    assert late.state == "FILLED"


def test_late_event_does_not_regress_filled() -> None:
    order = empty_order("dec-3")
    for kind in ("intent", "check", "send_attempt_started", "fill_final"):
        order = apply_event(order, kind)
    rejected = apply_event(order, "rejected")
    canceled = apply_event(order, "canceled")
    assert rejected.state == "FILLED"
    assert canceled.state == "FILLED"


def test_duplicate_deals_are_idempotent() -> None:
    order = empty_order("dec-4")
    for kind in ("intent", "check", "send_attempt_started"):
        order = apply_event(order, kind)
    order = apply_event(order, "fill_partial", {"deal_ticket": 11, "volume": 0.01})
    again = apply_event(order, "fill_partial", {"deal_ticket": 11, "volume": 0.01})
    assert again.filled_qty == 0.01
    assert again.state == "PARTIALLY_FILLED"
    completed = apply_event(again, "fill_final", {"deal_ticket": 12, "volume": 0.01})
    assert completed.filled_qty == 0.02
    assert completed.state == "FILLED"


def test_timeout_is_ambiguous_and_forbids_resend() -> None:
    order = empty_order("dec-5")
    for kind in ("intent", "check", "send_attempt_started", "timeout"):
        order = apply_event(order, kind)
    assert order.state == "SUBMITTED"
    assert order.outcome_class == AMBIGUOUS
    assert is_terminal_state(order.state) is False
    assert can_resend(order) is False


def test_rejected_before_send_is_not_ambiguous() -> None:
    order = empty_order("dec-6")
    order = apply_event(order, "intent")
    order = apply_event(order, "rejected")
    assert order.state == "REJECTED"
    assert order.outcome_class == "VENUE_REJECTED"
    assert can_resend(order) is False
