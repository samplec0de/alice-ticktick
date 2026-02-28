"""Fuzzy search over task titles using rapidfuzz."""

from __future__ import annotations

from rapidfuzz import fuzz, process
from rapidfuzz import utils as rf_utils


def find_best_match(
    query: str,
    candidates: list[str],
    *,
    threshold: int = 60,
) -> tuple[str, int] | None:
    """Find the best fuzzy match for *query* among *candidates*.

    Uses ``token_sort_ratio`` for resilience to word reordering in
    mixed Russian/English text.

    Returns ``(candidate, index)`` of the best match, or ``None`` if
    no candidate scores at or above *threshold*.
    """
    if not query or not candidates:
        return None

    result = process.extractOne(
        query,
        candidates,
        scorer=fuzz.token_sort_ratio,
        processor=rf_utils.default_process,
        score_cutoff=threshold,
    )
    if result is None:
        return None
    match, _score, index = result
    return str(match), int(index)


def find_matches(
    query: str,
    candidates: list[str],
    *,
    threshold: int = 60,
    limit: int = 5,
) -> list[tuple[str, float, int]]:
    """Return up to *limit* matches above *threshold*.

    Each element is ``(candidate, score, index)``.
    """
    if not query or not candidates:
        return []

    results = process.extract(
        query,
        candidates,
        scorer=fuzz.token_sort_ratio,
        processor=rf_utils.default_process,
        score_cutoff=threshold,
        limit=limit,
    )
    return [(str(match), float(score), int(idx)) for match, score, idx in results]
