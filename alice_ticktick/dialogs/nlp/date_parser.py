"""Parser for YANDEX.DATETIME NLU slots into Python datetime objects."""

from __future__ import annotations

import calendar
import contextlib
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from aliceio.types import NLU


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


@dataclass
class ExtractedDates:
    """Dates extracted from NLU entities with cleaned task name."""

    task_name: str
    start_date: datetime.date | datetime.datetime | None = None
    end_date: datetime.date | datetime.datetime | None = None


def extract_dates_from_nlu(
    nlu: NLU,
    *,
    command_token_count: int = 2,
) -> ExtractedDates:
    """Extract DATETIME entities from NLU and build a clean task name.

    Looks at ``nlu.entities`` for YANDEX.DATETIME entries,
    removes their token ranges from the task name tokens,
    and parses the dates.

    *command_token_count* is the number of leading tokens to skip
    (e.g. "создай задачу" = 2 tokens).
    """
    from aliceio.types import DateTimeEntity

    tokens = nlu.tokens

    # Collect DATETIME entities that are AFTER the command tokens
    dt_entities = []
    for entity in nlu.entities:
        if entity.type != "YANDEX.DATETIME":
            continue
        if entity.tokens.start < command_token_count:
            continue
        if not isinstance(entity.value, DateTimeEntity):
            continue
        dt_entities.append(entity)

    # Sort by token position
    dt_entities.sort(key=lambda e: e.tokens.start)

    # Build set of token indices occupied by DATETIME entities
    dt_token_indices: set[int] = set()
    for entity in dt_entities:
        dt_token_indices.update(range(entity.tokens.start, entity.tokens.end))

    # Task name = tokens after command, excluding DATETIME token ranges
    name_tokens = [
        tokens[i] for i in range(command_token_count, len(tokens)) if i not in dt_token_indices
    ]
    # Strip prepositions and date words left at the edges.
    # Yandex NLU may not include "завтра" in DATETIME entity token range
    # even though its semantics are captured in the entity value.
    _strip = {
        "на",
        "с",
        "в",
        "до",
        "по",
        "к",  # prepositions
        "завтра",
        "сегодня",
        "послезавтра",
        "вчера",  # date words
    }
    while name_tokens and name_tokens[-1] in _strip:
        name_tokens.pop()
    while name_tokens and name_tokens[0] in _strip:
        name_tokens.pop(0)

    task_name = " ".join(name_tokens)

    # Parse dates
    start_date = None
    end_date = None

    if len(dt_entities) >= 1:
        val = dt_entities[0].value
        slot = _datetime_entity_to_slot(val)
        with contextlib.suppress(ValueError):
            start_date = parse_yandex_datetime(slot)

    if len(dt_entities) >= 2:
        val = dt_entities[-1].value
        slot = _datetime_entity_to_slot(val)
        with contextlib.suppress(ValueError):
            # Parse end date relative to start date's base
            if start_date and isinstance(start_date, datetime.datetime):
                end_date = parse_yandex_datetime(slot, now=start_date)
            else:
                end_date = parse_yandex_datetime(slot)

    return ExtractedDates(
        task_name=task_name,
        start_date=start_date,
        end_date=end_date,
    )


def _datetime_entity_to_slot(entity: object) -> YandexDateTime:
    """Convert aliceio DateTimeEntity to our YandexDateTime dict."""
    slot: YandexDateTime = {}
    for field in ("year", "month", "day", "hour", "minute"):
        val = getattr(entity, field, None)
        if val is not None:
            slot[field] = val
        rel_key = f"{field}_is_relative"
        rel_val = getattr(entity, rel_key, None)
        if rel_val:
            slot[rel_key] = rel_val  # type: ignore[literal-required]
    return slot
