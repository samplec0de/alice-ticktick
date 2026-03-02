"""Parser for task duration from voice input."""

from __future__ import annotations

import datetime

_HOUR_WORDS = frozenset({"час", "часа", "часов"})
_MINUTE_WORDS = frozenset({"минута", "минуту", "минуты", "минут"})
_HALF_HOUR_WORDS = frozenset({"полчаса"})


def parse_duration(
    duration_value: int | None,
    duration_unit: str | None,
) -> datetime.timedelta | None:
    """Convert duration slot values into a timedelta.

    *duration_unit* is a Russian word (e.g. "час", "минута", "полчаса").
    *duration_value* is the count (None → 1, ignored for "полчаса").
    """
    if duration_unit is None:
        return None

    unit = duration_unit.lower().strip()

    if unit in _HALF_HOUR_WORDS:
        return datetime.timedelta(minutes=30)

    n = duration_value if duration_value is not None else 1

    if unit in _HOUR_WORDS:
        return datetime.timedelta(hours=n)
    if unit in _MINUTE_WORDS:
        return datetime.timedelta(minutes=n)

    return None
