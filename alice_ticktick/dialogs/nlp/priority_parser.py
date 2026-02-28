"""Map Russian priority words to TickTick numeric priority values."""

from __future__ import annotations

# TickTick priorities: 0 = none, 1 = low, 3 = medium, 5 = high
_PRIORITY_MAP: dict[str, int] = {
    # high / urgent
    "высокий": 5,
    "высокая": 5,
    "высокое": 5,
    "срочно": 5,
    "срочный": 5,
    "срочная": 5,
    "срочное": 5,
    "важно": 5,
    "важный": 5,
    "важная": 5,
    "важное": 5,
    "критический": 5,
    "критичный": 5,
    # medium
    "средний": 3,
    "средняя": 3,
    "среднее": 3,
    "нормальный": 3,
    "нормальная": 3,
    "нормальное": 3,
    # low
    "низкий": 1,
    "низкая": 1,
    "низкое": 1,
    "неважный": 1,
    "неважная": 1,
    "неважное": 1,
    # none
    "обычный": 0,
    "обычная": 0,
    "обычное": 0,
    "без приоритета": 0,
    "нет": 0,
}

VALID_PRIORITIES: frozenset[int] = frozenset({0, 1, 3, 5})


def parse_priority(text: str | None) -> int | None:
    """Return the TickTick priority for a Russian priority word.

    Returns ``None`` if the text is empty or not recognized.
    """
    if not text:
        return None
    normalized = text.strip().lower()
    return _PRIORITY_MAP.get(normalized)
