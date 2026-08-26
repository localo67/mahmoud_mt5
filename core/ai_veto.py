"""Veto IA optionnel : ALLOW ou VETO, jamais de direction / volume / SL / TP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union


@dataclass(frozen=True)
class VetoDecision:
    action: str
    reason: str
    side: Optional[str] = None
    volume: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None


class AIVeto:
    def __init__(
        self,
        provider: Callable[[str], Union[dict, Any]],
        timeout_seconds: float = 2.0,
    ):
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    async def review(self, signal_side: str, headline: str) -> VetoDecision:
        prompt = (
            f"Existing deterministic side={signal_side}. "
            f"Headline={headline}. Reply ALLOW or VETO only."
        )
        try:
            payload = await asyncio.wait_for(
                self._call(prompt),
                timeout=self.timeout_seconds,
            )
        except (asyncio.TimeoutError, Exception):
            return VetoDecision("VETO", "timeout_or_invalid")
        action = str((payload or {}).get("decision", "")).upper()
        if action not in {"ALLOW", "VETO"}:
            return VetoDecision("VETO", "invalid_payload")
        return VetoDecision(action, str((payload or {}).get("reason") or action))

    async def _call(self, prompt: str):
        result = self.provider(prompt)
        if asyncio.iscoroutine(result):
            return await result
        return result
