"""Parser for YANDEX.DATETIME NLU slots into Python datetime objects."""

from __future__ import annotations

import calendar
import datetime
from typing import TypedDict


class YandexDateTime(TypedDict, total=False):
    """Typed structure for YANDEX.DATETIME NLU slot values."""

    year: int
    month: int
    day: int
    hour: int
    minute: int
    year_is_relative: bool
    month_is_relative: bool
    day_is_relative: bool
    hour_is_relative: bool
    minute_is_relative: bool


def parse_yandex_datetime(
    slot: YandexDateTime,
    *,
    now: datetime.datetime | None = None,
) -> datetime.date | datetime.datetime:
    """Convert a YANDEX.DATETIME slot dict into a date or datetime.

    The slot dict has optional keys: year, month, day, hour, minute.
    Each value is an int. If the companion bool key ``<field>_is_relative``
    is ``True``, the value is treated as an offset from *now*.

    Returns ``datetime.date`` when hour/minute are absent,
    ``datetime.datetime`` otherwise.

    Raises:
        ValueError: If the slot is empty or contains no usable fields.
    """
    if not slot:
        raise ValueError("Empty YANDEX.DATETIME slot")

    if now is None:
        now = datetime.datetime.now(tz=datetime.UTC)

    # Start from now, then apply absolute or relative values for each field.
    base = now

    # Apply year
    if "year" in slot:
        if slot.get("year_is_relative", False):
            base = _add_years(base, slot["year"])
        else:
            base = base.replace(year=slot["year"])

    # Apply month
    if "month" in slot:
        if slot.get("month_is_relative", False):
            base = _add_months(base, slot["month"])
        else:
            base = base.replace(month=slot["month"])

    # Apply day
    if "day" in slot:
        if slot.get("day_is_relative", False):
            base = base + datetime.timedelta(days=slot["day"])
        else:
            base = base.replace(day=slot["day"])

    has_time = "hour" in slot or "minute" in slot

    # Apply hour
    if "hour" in slot:
        if slot.get("hour_is_relative", False):
            base = base + datetime.timedelta(hours=slot["hour"])
        else:
            base = base.replace(hour=slot["hour"])

    # Apply minute
    if "minute" in slot:
        if slot.get("minute_is_relative", False):
            base = base + datetime.timedelta(minutes=slot["minute"])
        else:
            base = base.replace(minute=slot["minute"])

    if has_time:
        return base

    return base.date()


def _add_months(dt: datetime.datetime, months: int) -> datetime.datetime:
    """Add *months* to *dt*, clamping the day to the last valid day."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def _add_years(dt: datetime.datetime, years: int) -> datetime.datetime:
    """Add *years* to *dt*, clamping Feb 29 to Feb 28 on non-leap years."""
    year = dt.year + years
    max_day = calendar.monthrange(year, dt.month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, day=day)
