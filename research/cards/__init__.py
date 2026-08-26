"""Fiches de recherche versionnees."""

from __future__ import annotations

import json
from pathlib import Path

CARDS_DIR = Path(__file__).resolve().parent


def load_card(name: str) -> dict:
    path = CARDS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
