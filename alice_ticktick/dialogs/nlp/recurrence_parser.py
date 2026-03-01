"""Parser for recurrence NLU slots → RRULE strings (RFC 5545)."""

from __future__ import annotations

# Mapping: normalized rec_freq value → (FREQ, optional BYDAY)
_FREQ_MAP: dict[str, tuple[str, str | None]] = {
    # Basic frequencies
    "день": ("DAILY", None),
    "дня": ("DAILY", None),
    "дней": ("DAILY", None),
    "ежедневно": ("DAILY", None),
    "неделю": ("WEEKLY", None),
    "неделя": ("WEEKLY", None),
    "недели": ("WEEKLY", None),
    "недель": ("WEEKLY", None),
    "еженедельно": ("WEEKLY", None),
    "месяц": ("MONTHLY", None),
    "месяца": ("MONTHLY", None),
    "месяцев": ("MONTHLY", None),
    "ежемесячно": ("MONTHLY", None),
    "год": ("YEARLY", None),
    "года": ("YEARLY", None),
    "лет": ("YEARLY", None),
    "ежегодно": ("YEARLY", None),
    # Days of week
    "понедельник": ("WEEKLY", "MO"),
    "вторник": ("WEEKLY", "TU"),
    "среду": ("WEEKLY", "WE"),
    "среда": ("WEEKLY", "WE"),
    "четверг": ("WEEKLY", "TH"),
    "пятницу": ("WEEKLY", "FR"),
    "пятница": ("WEEKLY", "FR"),
    "субботу": ("WEEKLY", "SA"),
    "суббота": ("WEEKLY", "SA"),
    "воскресенье": ("WEEKLY", "SU"),
    # Groups
    "будни": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "будний": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "будням": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "выходные": ("WEEKLY", "SA,SU"),
    "выходным": ("WEEKLY", "SA,SU"),
}

# Reverse mapping for format_recurrence
_BYDAY_TO_RU: dict[str, str] = {
    "MO": "понедельник",
    "TU": "вторник",
    "WE": "среду",
    "TH": "четверг",
    "FR": "пятницу",
    "SA": "субботу",
    "SU": "воскресенье",
}

_FREQ_TO_RU: dict[str, tuple[str, tuple[str, str, str]]] = {
    # (singular "каждый X", (1-form, 2-4-form, 5+-form) for interval)
    "DAILY": ("каждый день", ("день", "дня", "дней")),
    "WEEKLY": ("каждую неделю", ("неделю", "недели", "недель")),
    "MONTHLY": ("каждый месяц", ("месяц", "месяца", "месяцев")),
    "YEARLY": ("каждый год", ("год", "года", "лет")),
}


def _pluralize_interval(n: int, forms: tuple[str, str, str]) -> str:
    """Russian pluralization: 1 день, 2 дня, 5 дней."""
    abs_n = abs(n)
    if abs_n % 10 == 1 and abs_n % 100 != 11:
        return f"{n} {forms[0]}"
    if abs_n % 10 in (2, 3, 4) and abs_n % 100 not in (12, 13, 14):
        return f"{n} {forms[1]}"
    return f"{n} {forms[2]}"


def build_rrule(
    *,
    rec_freq: str | None = None,
    rec_interval: int | None = None,
    rec_monthday: int | None = None,
) -> str | None:
    """Convert NLU recurrence slots to an RRULE string.

    Returns None if no valid recurrence could be built.
    """
    # Monthday takes priority: "каждое 15 число"
    if rec_monthday is not None:
        return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={rec_monthday}"

    if rec_freq is None:
        return None

    normalized = rec_freq.lower().strip()
    entry = _FREQ_MAP.get(normalized)
    if entry is None:
        return None

    freq, byday = entry

    parts = [f"FREQ={freq}"]
    if rec_interval is not None and rec_interval > 1:
        parts.append(f"INTERVAL={rec_interval}")
    if byday is not None:
        parts.append(f"BYDAY={byday}")

    return "RRULE:" + ";".join(parts)


def format_recurrence(rrule: str | None) -> str | None:
    """Convert an RRULE string to a human-readable Russian description.

    Returns None if rrule is None.
    """
    if rrule is None:
        return None

    # Parse RRULE components
    body = rrule.removeprefix("RRULE:")
    params: dict[str, str] = {}
    for part in body.split(";"):
        if "=" in part:
            key, val = part.split("=", 1)
            params[key] = val

    freq = params.get("FREQ")
    interval = params.get("INTERVAL")
    byday = params.get("BYDAY")
    bymonthday = params.get("BYMONTHDAY")

    if bymonthday is not None:
        return f"каждое {bymonthday} число"

    if byday is not None:
        if byday == "MO,TU,WE,TH,FR":
            return "по будням"
        if byday == "SA,SU":
            return "по выходным"
        day_name = _BYDAY_TO_RU.get(byday)
        if day_name:
            return f"каждый {day_name}" if byday in ("MO", "TU", "TH") else f"каждую {day_name}"

    if freq and freq in _FREQ_TO_RU:
        singular, plural_forms = _FREQ_TO_RU[freq]
        if interval:
            return f"каждые {_pluralize_interval(int(interval), plural_forms)}"
        return singular

    return "повторяется"
