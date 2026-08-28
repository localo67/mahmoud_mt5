"""Session de trading : fenetre horaire, ou semaine forex (dimanche 17h NY → vendredi 17h NY)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
VALID_KINDS = frozenset({"clock", "fx_week"})


class SessionPolicy:
    def __init__(
        self,
        start_hour: int = 9,
        end_hour: int = 17,
        allow_overnight: bool = False,
        tz: ZoneInfo | str = NY_TZ,
        kind: str = "clock",
    ):
        if kind not in VALID_KINDS:
            raise ValueError(f"session kind inconnu: {kind!r}")
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.allow_overnight = allow_overnight
        self.tz = ZoneInfo(tz) if isinstance(tz, str) else tz
        self.kind = kind

    def localize(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=self.tz)
        return moment.astimezone(self.tz)

    def is_open(self, moment: datetime) -> bool:
        local = self.localize(moment)
        weekday = local.weekday()
        hour = local.hour
        if self.kind == "fx_week":
            if weekday == 5:
                return False
            if weekday == 6:
                return hour >= self.start_hour
            if weekday == 4:
                return hour < self.end_hour
            return True
        if weekday >= 5:
            return False
        return self.start_hour <= hour < self.end_hour

    def allows_new_entry(self, moment: datetime) -> bool:
        return self.is_open(moment)

    def would_be_overnight(self, moment: datetime, hold_until: datetime) -> bool:
        if self.allow_overnight:
            return False
        if self.kind == "fx_week":
            return self.is_open(moment) and not self.is_open(hold_until)
        start_local = self.localize(moment)
        end_local = self.localize(hold_until)
        if end_local.date() != start_local.date():
            return True
        return end_local.hour >= self.end_hour and start_local.hour < self.end_hour
