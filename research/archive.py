"""Archive ticks bid/ask : SQLite evenementiel + export colonnes parquet-compatible."""

from __future__ import annotations

import json
import sqlite3
import struct
import zlib
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_msc INTEGER NOT NULL,
    bid REAL NOT NULL,
    ask REAL NOT NULL,
    symbol TEXT NOT NULL,
    latency_ms INTEGER,
    specs TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticks_time ON ticks(time_msc);
"""


class TickArchive:
    def __init__(self, sqlite_path: Path, parquet_path: Path):
        self.sqlite_path = Path(sqlite_path)
        self.parquet_path = Path(parquet_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.sqlite_path)
        self._conn.executescript(SCHEMA)
        self._pending: list[dict] = []

    def append(self, tick: dict, specs: dict | None = None) -> None:
        row = dict(tick)
        if specs is not None:
            row["specs"] = json.dumps(specs)
        self._pending.append(row)

    def flush(self) -> None:
        if not self._pending:
            self._export_parquet()
            return
        self._conn.executemany(
            "INSERT INTO ticks (time_msc, bid, ask, symbol, latency_ms, specs) "
            "VALUES (:time_msc, :bid, :ask, :symbol, :latency_ms, :specs)",
            [
                {
                    "time_msc": int(item["time_msc"]),
                    "bid": float(item["bid"]),
                    "ask": float(item["ask"]),
                    "symbol": item.get("symbol", "XAUUSD"),
                    "latency_ms": int(item.get("latency_ms") or 0),
                    "specs": item.get("specs"),
                }
                for item in self._pending
            ],
        )
        self._conn.commit()
        self._pending.clear()
        self._export_parquet()

    def load(self) -> list[dict]:
        self.flush()
        rows = self._conn.execute(
            "SELECT time_msc, bid, ask, symbol, latency_ms, specs FROM ticks ORDER BY id"
        ).fetchall()
        result = []
        for time_msc, bid, ask, symbol, latency_ms, specs in rows:
            item = {
                "time_msc": time_msc,
                "bid": bid,
                "ask": ask,
                "symbol": symbol,
                "latency_ms": latency_ms,
            }
            if specs:
                item["specs"] = json.loads(specs)
            result.append(item)
        return result

    def _export_parquet(self) -> None:
        rows = self._conn.execute(
            "SELECT time_msc, bid, ask, symbol, latency_ms FROM ticks ORDER BY id"
        ).fetchall()
        payload = json.dumps(
            {
                "columns": ["time_msc", "bid", "ask", "symbol", "latency_ms"],
                "rows": [list(row) for row in rows],
            }
        ).encode("utf-8")
        compressed = zlib.compress(payload)
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        with self.parquet_path.open("wb") as handle:
            handle.write(b"MT5PARQ1")
            handle.write(struct.pack(">I", len(compressed)))
            handle.write(compressed)
