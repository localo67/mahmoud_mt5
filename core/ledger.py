"""Journal SQLite append-only des decisions d'execution."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.order_state import reduce_events
from core.types import ExecutionResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    client_order_id TEXT,
    send_attempt_id TEXT,
    order_ticket INTEGER,
    deal_ticket INTEGER,
    position_id INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id);
CREATE INDEX IF NOT EXISTS idx_events_decision ON events(decision_id, id);
CREATE INDEX IF NOT EXISTS idx_events_client ON events(client_order_id);
CREATE INDEX IF NOT EXISTS idx_events_deal ON events(deal_ticket);
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;
CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only');
END;
"""


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._migrate()
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def _migrate(self) -> None:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()
        if row is None:
            return
        cols = {item[1] for item in self._conn.execute("PRAGMA table_info(events)")}
        additions = {
            "event_id": "TEXT",
            "client_order_id": "TEXT",
            "send_attempt_id": "TEXT",
            "order_ticket": "INTEGER",
            "deal_ticket": "INTEGER",
            "position_id": "INTEGER",
        }
        for name, decl in additions.items():
            if name not in cols:
                self._conn.execute(f"ALTER TABLE events ADD COLUMN {name} {decl}")
        missing_ids = self._conn.execute(
            "SELECT id FROM events WHERE event_id IS NULL OR event_id = ''"
        ).fetchall()
        for item in missing_ids:
            self._conn.execute(
                "UPDATE events SET event_id = ? WHERE id = ?",
                (f"legacy-{item['id']}", item["id"]),
            )
        self._conn.commit()

    def append(
        self,
        decision_id: str,
        kind: str,
        payload: dict[str, Any],
        ts: Optional[str] = None,
        event_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        send_attempt_id: Optional[str] = None,
        order_ticket: Optional[int] = None,
        deal_ticket: Optional[int] = None,
        position_id: Optional[int] = None,
    ) -> bool:
        stamp = ts or datetime.now(timezone.utc).isoformat()
        payload = dict(payload or {})
        client_order_id = client_order_id or payload.get("client_order_id")
        send_attempt_id = send_attempt_id or payload.get("send_attempt_id")
        order_ticket = order_ticket or payload.get("order_id") or payload.get("order_ticket")
        deal_ticket = deal_ticket or payload.get("deal_id") or payload.get("deal_ticket")
        position_id = position_id or payload.get("position_id")
        if event_id is None:
            event_id = self._default_event_id(
                decision_id, kind, payload, client_order_id, send_attempt_id, deal_ticket
            )
        try:
            self._conn.execute(
                """
                INSERT INTO events (
                    event_id, ts, decision_id, kind, payload,
                    client_order_id, send_attempt_id, order_ticket, deal_ticket, position_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    stamp,
                    decision_id,
                    kind,
                    json.dumps(payload, default=str),
                    client_order_id,
                    send_attempt_id,
                    int(order_ticket) if order_ticket is not None else None,
                    int(deal_ticket) if deal_ticket is not None else None,
                    int(position_id) if position_id is not None else None,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def _default_event_id(
        decision_id: str,
        kind: str,
        payload: dict,
        client_order_id: Optional[str],
        send_attempt_id: Optional[str],
        deal_ticket: Optional[int],
    ) -> str:
        unique = payload.get("event_id")
        if unique:
            return str(unique)
        if kind in {"intent", "check", "send_attempt_started", "timeout", "rejected"}:
            key = f"{decision_id}:{kind}:{send_attempt_id or client_order_id or ''}"
        elif deal_ticket is not None:
            key = f"{decision_id}:{kind}:deal:{deal_ticket}"
        else:
            key = f"{decision_id}:{kind}:{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

    def events(self, decision_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, kind, payload, event_id, client_order_id, send_attempt_id, "
            "order_ticket, deal_ticket, position_id FROM events "
            "WHERE decision_id = ? ORDER BY id",
            (decision_id,),
        ).fetchall()
        return [self._row(row) for row in rows]

    def all_events(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, kind, payload, event_id, client_order_id, send_attempt_id, "
            "order_ticket, deal_ticket, position_id, decision_id FROM events ORDER BY id"
        ).fetchall()
        items = []
        for row in rows:
            item = self._row(row)
            item["decision_id"] = row["decision_id"]
            items.append(item)
        return items

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return {
            "ts": row["ts"],
            "kind": row["kind"],
            "payload": json.loads(row["payload"]),
            "event_id": row["event_id"],
            "client_order_id": row["client_order_id"],
            "send_attempt_id": row["send_attempt_id"],
            "order_ticket": row["order_ticket"],
            "deal_ticket": row["deal_ticket"],
            "position_id": row["position_id"],
        }

    def status(self, decision_id: str) -> Optional[str]:
        items = self.events(decision_id)
        if not items:
            return None
        for item in reversed(items):
            if item["kind"] == "reconcile" and item["payload"].get("ok"):
                return "RECONCILED"
            if item["kind"] == "result":
                return item["payload"].get("status")
        view = reduce_events(items, decision_id)
        return view.state

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

    def order_view(self, decision_id: str, requested_qty: float = 0.0):
        return reduce_events(self.events(decision_id), decision_id, requested_qty)

    def mapping(self, decision_id: str) -> dict[str, Any]:
        payload = {
            "client_order_id": None,
            "send_attempt_id": None,
            "order_ticket": None,
            "deal_tickets": [],
            "position_id": None,
        }
        deals: list[int] = []
        for item in self.events(decision_id):
            payload["client_order_id"] = item.get("client_order_id") or payload["client_order_id"]
            payload["send_attempt_id"] = item.get("send_attempt_id") or payload["send_attempt_id"]
            payload["order_ticket"] = item.get("order_ticket") or payload["order_ticket"]
            payload["position_id"] = item.get("position_id") or payload["position_id"]
            if item.get("deal_ticket") is not None:
                deals.append(int(item["deal_ticket"]))
        payload["deal_tickets"] = list(dict.fromkeys(deals))
        return payload

    def backup(self, dest: Path) -> dict:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        target = sqlite3.connect(dest)
        try:
            self._conn.backup(target)
            target.commit()
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            target.close()
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        return {
            "ok": integrity == "ok",
            "path": str(dest),
            "sha256": digest,
            "integrity": integrity,
        }

    def restore_to(self, backup_path: Path, dest: Path) -> dict:
        backup_path = Path(backup_path)
        dest = Path(dest)
        check = sqlite3.connect(backup_path)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            count = check.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            check.close()
        if integrity != "ok":
            return {"ok": False, "integrity": integrity, "path": str(dest)}
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".restore")
        source = sqlite3.connect(backup_path)
        target = sqlite3.connect(tmp)
        try:
            source.backup(target)
            target.commit()
        finally:
            source.close()
            target.close()
        tmp.replace(dest)
        return {
            "ok": True,
            "path": str(dest),
            "integrity": integrity,
            "events": count,
            "armed": False,
        }

    def close(self) -> None:
        self._conn.close()
