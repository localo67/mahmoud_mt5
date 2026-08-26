"""Journal SQLite append-only des decisions d'execution."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.types import ExecutionResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_decision ON events(decision_id, id);
"""


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def append(self, decision_id: str, kind: str, payload: dict[str, Any], ts: Optional[str] = None) -> None:
        stamp = ts or datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO events (ts, decision_id, kind, payload) VALUES (?, ?, ?, ?)",
            (stamp, decision_id, kind, json.dumps(payload, default=str)),
        )
        self._conn.commit()

    def events(self, decision_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, kind, payload FROM events WHERE decision_id = ? ORDER BY id",
            (decision_id,),
        ).fetchall()
        return [
            {"ts": row["ts"], "kind": row["kind"], "payload": json.loads(row["payload"])}
            for row in rows
        ]

    def status(self, decision_id: str) -> Optional[str]:
        items = self.events(decision_id)
        if not items:
            return None
        for item in reversed(items):
            if item["kind"] == "reconcile" and item["payload"].get("ok"):
                return "RECONCILED"
            if item["kind"] == "result":
                return item["payload"].get("status")
        return items[-1]["kind"].upper()

    def last_result(self, decision_id: str) -> Optional[ExecutionResult]:
        for item in reversed(self.events(decision_id)):
            if item["kind"] != "result":
                continue
            payload = item["payload"]
            return ExecutionResult(
                decision_id=decision_id,
                status=payload.get("status", "UNKNOWN"),
                order_id=payload.get("order_id"),
                deal_id=payload.get("deal_id"),
                position_id=payload.get("position_id"),
                volume=float(payload.get("volume") or 0.0),
                price=float(payload.get("price") or 0.0),
                comment=str(payload.get("comment") or ""),
                retcode=payload.get("retcode"),
                ambiguous=bool(payload.get("ambiguous", False)),
            )
        return None

    def close(self) -> None:
        self._conn.close()
