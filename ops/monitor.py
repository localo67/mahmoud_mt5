"""Supervision fail-closed des nouvelles entrees."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorHalt:
    halt: bool
    reason: str = ""


class Monitor:
    def observe(self, snapshot: dict) -> MonitorHalt:
        if snapshot.get("kill_switch"):
            return MonitorHalt(True, "KILL_SWITCH")
        if snapshot.get("stale_quote"):
            return MonitorHalt(True, "STALE_QUOTE")
        if snapshot.get("unknown_position"):
            return MonitorHalt(True, "UNKNOWN_POSITION")
        if snapshot.get("reconciliation_ok") is False:
            return MonitorHalt(True, "RECONCILIATION_ERROR")
        if snapshot.get("missing_sl"):
            return MonitorHalt(True, "MISSING_SL")
        return MonitorHalt(False, "OK")
