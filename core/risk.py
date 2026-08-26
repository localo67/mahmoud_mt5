"""Risque fail-closed fonde sur les specifications broker et le P&L reel."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from core.specs import loss_at_stop, round_volume_down
from core.types import (
    AccountSnapshot,
    Quote,
    RiskDecision,
    RiskLimits,
    SignalIntent,
    SymbolSpec,
)


def size_order(
    equity: float,
    risk_pct: float,
    spec: SymbolSpec,
    side: str,
    entry: float,
    sl: float,
    account_currency: str,
) -> RiskDecision:
    if account_currency != spec.currency_profit:
        return RiskDecision(False, 0.0, "CURRENCY_MISMATCH")
    if entry <= 0 or sl <= 0 or entry == sl:
        return RiskDecision(False, 0.0, "INVALID_STOP")
    budget = equity * (risk_pct / 100.0)
    loss_one_lot = abs(loss_at_stop(1.0, spec, entry, sl, side))
    if loss_one_lot <= 0:
        return RiskDecision(False, 0.0, "UNDETERMINED_RISK")
    raw_volume = budget / loss_one_lot
    volume = round_volume_down(raw_volume, spec)
    if volume < spec.volume_min:
        return RiskDecision(False, 0.0, "MIN_LOT_EXCEEDS_RISK", expected_loss=0.0)
    expected = abs(loss_at_stop(volume, spec, entry, sl, side))
    if expected > budget + (spec.volume_step * loss_one_lot):
        return RiskDecision(False, 0.0, "RISK_EXCEEDS_BUDGET", expected_loss=expected)
    return RiskDecision(True, volume, "OK", expected_loss=expected)


class RiskEngine:
    def __init__(
        self,
        limits: RiskLimits,
        spec: SymbolSpec,
        now: Callable[[], datetime],
        state_path: Optional[Path] = None,
    ):
        self.limits = limits
        self.spec = spec
        self._now = now
        self.state_path = Path(state_path) if state_path else None
        self.kill_switch = False
        self.kill_reason = ""
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.monthly_pnl = 0.0
        self.last_reset_date = ""
        self._load()

    def decide(
        self,
        intent: SignalIntent,
        quote: Quote,
        account: AccountSnapshot,
    ) -> RiskDecision:
        now = self._now()
        self._roll_calendars(now)
        if self.kill_switch:
            return RiskDecision(False, 0.0, "KILL_SWITCH")
        age = (now - quote.server_time).total_seconds()
        if age > self.limits.stale_quote_seconds:
            return RiskDecision(False, 0.0, "STALE_QUOTE")
        realized_and_open = (
            self.daily_pnl
            + account.floating_pnl
            + account.commission
            + account.swap
        )
        if realized_and_open <= -self.limits.max_daily_loss:
            return RiskDecision(False, 0.0, "DAILY_LOSS")
        if self.weekly_pnl + account.floating_pnl <= -self.limits.max_weekly_loss:
            return RiskDecision(False, 0.0, "WEEKLY_LOSS")
        if self.monthly_pnl + account.floating_pnl <= -self.limits.max_monthly_loss:
            return RiskDecision(False, 0.0, "MONTHLY_LOSS")
        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            return RiskDecision(False, 0.0, "CONSECUTIVE_LOSSES")
        if account.open_positions > 0:
            return RiskDecision(False, 0.0, "POSITION_EXISTS")
        return size_order(
            account.equity,
            self.limits.risk_pct,
            self.spec,
            intent.side,
            intent.entry,
            intent.sl,
            account.currency,
        )

    def expected_loss(self, volume: float, intent: SignalIntent) -> float:
        return abs(loss_at_stop(volume, self.spec, intent.entry, intent.sl, intent.side))

    def record_closed_trade(
        self,
        profit: float,
        commission: float = 0.0,
        swap: float = 0.0,
    ) -> None:
        net = profit + commission + swap
        self.daily_pnl += net
        self.weekly_pnl += net
        self.monthly_pnl += net
        if net < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        self._save()

    def trip_kill_switch(self, reason: str) -> None:
        self.kill_switch = True
        self.kill_reason = reason
        self._save()

    def reset_daily(self) -> None:
        """Reset quotidien chaud : ne touche pas le kill switch persistant."""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.last_reset_date = self._now().astimezone(timezone.utc).strftime("%Y-%m-%d")
        self._save()

    def _roll_calendars(self, now: datetime) -> None:
        today = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
        if self.last_reset_date != today and not self.kill_switch:
            self.daily_pnl = 0.0
            if self.last_reset_date:
                previous = datetime.fromisoformat(self.last_reset_date)
                iso = now.isocalendar()
                previous_iso = previous.isocalendar()
                if (iso.year, iso.week) != (previous_iso.year, previous_iso.week):
                    self.weekly_pnl = 0.0
                if now.month != previous.month:
                    self.monthly_pnl = 0.0
            self.last_reset_date = today
            self._save()

    def _load(self) -> None:
        if self.state_path is None:
            return
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.kill_switch = True
            self.kill_reason = "CORRUPTED_STATE"
            return
        self.kill_switch = bool(payload.get("kill_switch", False))
        self.kill_reason = str(payload.get("kill_reason", ""))
        self.consecutive_losses = int(payload.get("consecutive_losses", 0))
        self.daily_pnl = float(payload.get("daily_pnl", 0.0))
        self.weekly_pnl = float(payload.get("weekly_pnl", 0.0))
        self.monthly_pnl = float(payload.get("monthly_pnl", 0.0))
        self.last_reset_date = str(payload.get("last_reset_date", ""))

    def _save(self) -> None:
        if self.state_path is None:
            return
        payload = {
            "kill_switch": self.kill_switch,
            "kill_reason": self.kill_reason,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "weekly_pnl": self.weekly_pnl,
            "monthly_pnl": self.monthly_pnl,
            "last_reset_date": self.last_reset_date,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
