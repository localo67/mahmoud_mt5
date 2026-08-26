"""Rapport de qualite des ticks, sans secret."""

from __future__ import annotations


def quality_report(ticks: list[dict], max_gap_ms: int = 5_000) -> dict:
    duplicates = 0
    crossed = 0
    gaps = 0
    unordered = 0
    spec_changes = 0
    seen: set[tuple] = set()
    previous_ms = None
    previous_specs = None
    for tick in ticks:
        key = (tick["time_msc"], tick["bid"], tick["ask"], tick.get("symbol"))
        if key in seen:
            duplicates += 1
        seen.add(key)
        if tick["bid"] > tick["ask"]:
            crossed += 1
        if previous_ms is not None:
            if tick["time_msc"] < previous_ms:
                unordered += 1
            if tick["time_msc"] - previous_ms > max_gap_ms:
                gaps += 1
        specs = tick.get("specs")
        if previous_specs is not None and specs is not None and specs != previous_specs:
            spec_changes += 1
        previous_ms = tick["time_msc"]
        if specs is not None:
            previous_specs = specs
    ok = duplicates == 0 and crossed == 0 and unordered == 0
    return {
        "count": len(ticks),
        "duplicates": duplicates,
        "crossed_quotes": crossed,
        "gaps": gaps,
        "unordered": unordered,
        "spec_changes": spec_changes,
        "ok": ok,
    }
