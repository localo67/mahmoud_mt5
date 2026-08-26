from datetime import datetime, timezone

from core.session import SessionPolicy


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_winter_session_follows_eastern_standard_time() -> None:
    policy = SessionPolicy(start_hour=9, end_hour=17)
    assert policy.is_open(_utc(2026, 1, 15, 13, 59)) is False
    assert policy.is_open(_utc(2026, 1, 15, 14, 0)) is True
    assert policy.is_open(_utc(2026, 1, 15, 21, 59)) is True
    assert policy.is_open(_utc(2026, 1, 15, 22, 0)) is False


def test_summer_session_follows_eastern_daylight_time() -> None:
    policy = SessionPolicy(start_hour=9, end_hour=17)
    assert policy.is_open(_utc(2026, 7, 15, 12, 59)) is False
    assert policy.is_open(_utc(2026, 7, 15, 13, 0)) is True
    assert policy.is_open(_utc(2026, 7, 15, 20, 59)) is True
    assert policy.is_open(_utc(2026, 7, 15, 21, 0)) is False


def test_weekend_is_closed() -> None:
    policy = SessionPolicy(start_hour=9, end_hour=17)
    assert policy.is_open(_utc(2026, 8, 22, 15, 0)) is False


def test_validation_forbids_overnight_hold() -> None:
    policy = SessionPolicy(start_hour=9, end_hour=17, allow_overnight=False)
    now = _utc(2026, 7, 15, 20, 30)
    assert policy.would_be_overnight(now, hold_until=_utc(2026, 7, 16, 13, 0)) is True
    assert policy.allows_new_entry(now) is True
    assert policy.allows_new_entry(_utc(2026, 7, 15, 21, 0)) is False
