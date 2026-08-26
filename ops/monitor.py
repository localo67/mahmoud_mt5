"""Supervision fail-closed des nouvelles entrees, sans fermeture automatique."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MonitorHalt:
    halt: bool
    reason: str = ""


class Monitor:
    def __init__(self, controls=None):
        self.controls = controls

    def observe(self, snapshot: dict) -> MonitorHalt:
        halt = self._decide(snapshot)
        if halt.halt and self.controls is not None:
            self.controls.halt_entries(halt.reason)
        return halt

    @staticmethod
    def _decide(snapshot: dict) -> MonitorHalt:
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
        if snapshot.get("ambiguous_exposure"):
            return MonitorHalt(True, "AMBIGUOUS_EXPOSURE")
        return MonitorHalt(False, "OK")
