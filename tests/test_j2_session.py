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


def _fx_week() -> SessionPolicy:
    return SessionPolicy(start_hour=17, end_hour=17, kind="fx_week")


def test_fx_week_opens_sunday_1700_new_york() -> None:
    policy = _fx_week()
    assert policy.is_open(_utc(2026, 8, 23, 20, 59)) is False
    assert policy.is_open(_utc(2026, 8, 23, 21, 0)) is True
    assert policy.is_open(_utc(2026, 1, 18, 21, 59)) is False
    assert policy.is_open(_utc(2026, 1, 18, 22, 0)) is True


def test_fx_week_closes_friday_1700_new_york() -> None:
    policy = _fx_week()
    assert policy.is_open(_utc(2026, 8, 21, 20, 59)) is True
    assert policy.is_open(_utc(2026, 8, 21, 21, 0)) is False
    assert policy.is_open(_utc(2026, 1, 16, 21, 59)) is True
    assert policy.is_open(_utc(2026, 1, 16, 22, 0)) is False


def test_fx_week_open_midweek_night_closed_saturday() -> None:
    policy = _fx_week()
    assert policy.is_open(_utc(2026, 8, 25, 3, 0)) is True
    assert policy.is_open(_utc(2026, 8, 22, 15, 0)) is False


def test_fx_week_overnight_only_past_friday_close() -> None:
    policy = SessionPolicy(start_hour=17, end_hour=17, kind="fx_week", allow_overnight=False)
    monday_night = _utc(2026, 8, 25, 3, 0)
    tuesday = _utc(2026, 8, 25, 14, 0)
    friday_close = _utc(2026, 8, 21, 21, 0)
    friday_afternoon = _utc(2026, 8, 21, 18, 0)
    assert policy.would_be_overnight(monday_night, hold_until=tuesday) is False
    assert policy.would_be_overnight(friday_afternoon, hold_until=friday_close) is True
