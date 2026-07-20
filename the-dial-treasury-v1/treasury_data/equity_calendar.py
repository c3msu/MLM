"""Shared U.S. equity-session timing used by refresh and health gates."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


NEW_YORK_TZ = ZoneInfo("America/New_York")
DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES = 20


def _observed_fixed_holiday(month: int, day: int, year: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    cursor = date(year, month, 1)
    offset = (weekday - cursor.weekday()) % 7
    return cursor + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    cursor = next_month - timedelta(days=1)
    return cursor - timedelta(days=(cursor.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Return Gregorian Easter using the Anonymous Gregorian computus."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def us_equity_market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed_holiday(1, 1, year),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed_fixed_holiday(7, 4, year),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed_fixed_holiday(12, 25, year),
    }
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(6, 19, year))
    return holidays


def is_us_equity_session(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = set().union(
        *(us_equity_market_holidays(year) for year in (day.year - 1, day.year, day.year + 1))
    )
    return day not in holidays


def previous_us_equity_session(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_us_equity_session(cursor):
        cursor -= timedelta(days=1)
    return cursor


def us_equity_sessions_between(start: date, end: date) -> int:
    """Count exchange sessions strictly after ``start`` through ``end``."""

    if end <= start:
        return 0
    count = 0
    cursor = start + timedelta(days=1)
    while cursor <= end:
        if is_us_equity_session(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count


def _ceil_positive_minutes(delta: timedelta) -> int:
    return max(0, int((delta.total_seconds() + 59) // 60))


def _floor_positive_minutes(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


def equity_bar_timing(
    now: datetime | None = None,
    *,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    ny_now = current.astimezone(NEW_YORK_TZ)
    ny_today = ny_now.date()
    close_time = ny_now.replace(hour=16, minute=0, second=0, microsecond=0)
    ready_time = close_time + timedelta(minutes=after_close_lag_minutes)
    if not is_us_equity_session(ny_today):
        expected = previous_us_equity_session(ny_today)
        phase = "non_trading_day"
        minutes_until_expected = None
        minutes_since_expected = None
    elif ny_now < close_time:
        expected = previous_us_equity_session(ny_today)
        phase = "trading_session"
        minutes_until_expected = _ceil_positive_minutes(ready_time - ny_now)
        minutes_since_expected = None
    elif ny_now < ready_time:
        expected = previous_us_equity_session(ny_today)
        phase = "post_close_wait"
        minutes_until_expected = _ceil_positive_minutes(ready_time - ny_now)
        minutes_since_expected = None
    else:
        expected = ny_today
        phase = "daily_bar_due"
        minutes_until_expected = 0
        minutes_since_expected = _floor_positive_minutes(ny_now - ready_time)
    return {
        "expectedDate": expected,
        "marketDate": ny_today,
        "marketTime": ny_now.isoformat(),
        "readyAt": ready_time.isoformat() if is_us_equity_session(ny_today) else None,
        "phase": phase,
        "minutesUntilExpected": minutes_until_expected,
        "minutesSinceExpected": minutes_since_expected,
        "afterCloseLagMinutes": after_close_lag_minutes,
    }


def expected_equity_bar_date(
    now: datetime | None = None,
    *,
    after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> date:
    expected = equity_bar_timing(
        now,
        after_close_lag_minutes=after_close_lag_minutes,
    )["expectedDate"]
    if not isinstance(expected, date):
        raise TypeError("equity_bar_timing expectedDate must be a date")
    return expected
