"""Session America/New_York avec DST, sans overnight pendant la validation."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


class SessionPolicy:
    def __init__(
        self,
        start_hour: int = 9,
        end_hour: int = 17,
        allow_overnight: bool = False,
        tz: ZoneInfo = NY_TZ,
    ):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.allow_overnight = allow_overnight
        self.tz = tz

    def localize(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=self.tz)
        return moment.astimezone(self.tz)

    def is_open(self, moment: datetime) -> bool:
        local = self.localize(moment)
        if local.weekday() >= 5:
            return False
        return self.start_hour <= local.hour < self.end_hour

    def allows_new_entry(self, moment: datetime) -> bool:
        return self.is_open(moment)

    def would_be_overnight(self, moment: datetime, hold_until: datetime) -> bool:
        if self.allow_overnight:
            return False
        start_local = self.localize(moment)
        end_local = self.localize(hold_until)
        if end_local.date() != start_local.date():
            return True
        return end_local.hour >= self.end_hour and start_local.hour < self.end_hour
