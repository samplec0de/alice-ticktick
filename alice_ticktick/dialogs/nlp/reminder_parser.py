"""Parser for reminder NLU slots → iCal TRIGGER strings."""

from __future__ import annotations

import re

_UNIT_MAP: dict[str, str] = {
    # minutes
    "минуту": "M",
    "минута": "M",
    "минуты": "M",
    "минут": "M",
    # hours
    "час": "H",
    "часа": "H",
    "часов": "H",
    # days
    "день": "D",
    "дня": "D",
    "дней": "D",
}

# For pluralization in format_reminder
_MINUTE_FORMS = ("минуту", "минуты", "минут")  # 1, 2-4, 5+
_HOUR_FORMS = ("час", "часа", "часов")
_DAY_FORMS = ("день", "дня", "дней")

_TRIGGER_RE = re.compile(
    r"TRIGGER:(-?)P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?|(\d+)D)"
)


def build_trigger(value: int | None, unit: str | None) -> str | None:
    """Convert NLU reminder slots to an iCal TRIGGER string.

    Returns None if value or unit is missing/unknown.
    """
    if value is None or unit is None:
        return None

    if value == 0:
        return "TRIGGER:PT0S"

    code = _UNIT_MAP.get(unit.lower().strip())
    if code is None:
        return None

    if code == "D":
        return f"TRIGGER:-P{value}D"
    return f"TRIGGER:-PT{value}{code}"


def _pluralize(n: int, forms: tuple[str, str, str]) -> str:
    """Russian pluralization: 1 минуту, 2 минуты, 5 минут."""
    abs_n = abs(n)
    if abs_n % 10 == 1 and abs_n % 100 != 11:
        return f"{n} {forms[0]}"
    if abs_n % 10 in (2, 3, 4) and abs_n % 100 not in (12, 13, 14):
        return f"{n} {forms[1]}"
    return f"{n} {forms[2]}"


def format_reminder(trigger: str | None) -> str | None:
    """Convert an iCal TRIGGER string to a human-readable Russian description.

    Returns None if trigger is None.
    """
    if trigger is None:
        return None

    if trigger == "TRIGGER:PT0S":
        return "в момент задачи"

    m = _TRIGGER_RE.match(trigger)
    if not m:
        return "напоминание"

    _sign, hours, minutes, _seconds, days = m.groups()

    if days:
        return f"за {_pluralize(int(days), _DAY_FORMS)}"
    if hours:
        return f"за {_pluralize(int(hours), _HOUR_FORMS)}"
    if minutes:
        return f"за {_pluralize(int(minutes), _MINUTE_FORMS)}"

    return "напоминание"
