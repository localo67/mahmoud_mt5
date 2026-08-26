"""News point-in-time : first_seen_at obligatoire, jamais reconstruit."""

from __future__ import annotations


class PointInTimeNews:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, item: dict) -> None:
        if not item.get("first_seen_at"):
            raise ValueError("first_seen_at is required; historical news cannot be fabricated")
        self.rows.append(dict(item))

    def visible_at(self, timestamp: str) -> list[dict]:
        return [item for item in self.rows if item["first_seen_at"] <= timestamp]
