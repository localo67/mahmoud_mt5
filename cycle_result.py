"""Resultats structures d'un cycle de decision, sans secrets."""

from dataclasses import dataclass, field
from enum import Enum


class Blocker(str, Enum):
    MT5_UNAVAILABLE = "MT5_UNAVAILABLE"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    NOT_ARMED = "NOT_ARMED"
    SYMBOL_UNRESOLVED = "SYMBOL_UNRESOLVED"
    STALE_TICK = "STALE_TICK"
    INSUFFICIENT_CLOSED_BARS = "INSUFFICIENT_CLOSED_BARS"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"
    NEWS_BLOCK = "NEWS_BLOCK"
    RISK_BLOCK = "RISK_BLOCK"
    SPREAD_BLOCK = "SPREAD_BLOCK"
    MARGIN_BLOCK = "MARGIN_BLOCK"
    POSITION_EXISTS = "POSITION_EXISTS"
    AI_WAIT = "AI_WAIT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SYMBOL_SPEC_CHANGED = "SYMBOL_SPEC_CHANGED"
    ORDER_CHECK_REJECTED = "ORDER_CHECK_REJECTED"
    SHADOW_CANDIDATE = "SHADOW_CANDIDATE"
    SEND_AMBIGUOUS = "SEND_AMBIGUOUS"
    RECONCILIATION_ERROR = "RECONCILIATION_ERROR"
    ENTRIES_HALTED = "ENTRIES_HALTED"
    NO_SIGNAL = "NO_SIGNAL"
    AMBIGUOUS_EXPOSURE = "AMBIGUOUS_EXPOSURE"
    EXECUTED = "EXECUTED"


MIN_CLOSED_BARS = 50
STALE_TICK_SECONDS = 120


@dataclass
class CycleResult:
    candle_time: int | None
    blockers: list[str]
    outcome: str
    details: dict = field(default_factory=dict)

    def to_public_dict(self) -> dict:
        return {
            "candle_time": self.candle_time,
            "blockers": list(self.blockers),
            "outcome": self.outcome,
            "details": dict(self.details),
        }
