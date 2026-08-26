"""Controles operationnels persistants: entrees, gestion, urgence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ControlState:
    entries_allowed: bool = True
    position_management_enabled: bool = True
    emergency_exit_requested: bool = False
    reason: str = ""
    updated_at: str = ""


class OperationalControl:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = ControlState()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._save()
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.state.entries_allowed = False
            self.state.reason = "CORRUPTED_CONTROL"
            self._save()
            return
        self.state = ControlState(
            entries_allowed=bool(payload.get("entries_allowed", True)),
            position_management_enabled=bool(payload.get("position_management_enabled", True)),
            emergency_exit_requested=bool(payload.get("emergency_exit_requested", False)),
            reason=str(payload.get("reason") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def _save(self) -> None:
        self.state.updated_at = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")

    def halt_entries(self, reason: str) -> ControlState:
        self.state.entries_allowed = False
        self.state.reason = reason
        self._save()
        return self.state

    def allow_entries(self, reason: str = "cleared") -> ControlState:
        self.state.entries_allowed = True
        self.state.reason = reason
        self._save()
        return self.state

    def disable_position_management(self, reason: str) -> ControlState:
        self.state.position_management_enabled = False
        self.state.reason = reason
        self._save()
        return self.state

    def request_emergency_exit(self, reason: str) -> ControlState:
        self.state.emergency_exit_requested = True
        self.state.reason = reason
        self._save()
        return self.state
