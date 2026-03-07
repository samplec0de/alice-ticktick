"""E2E tests: Section 3.18 — Edge cases (long names, numbers, empty lists, similar names)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Long task names (2 tests)
# ---------------------------------------------------------------------------


async def test_long_task_name(yandex_client: YandexDialogsClient) -> None:
    """Create a task with a very long name."""
    long_name = "кктест " + "подготовить очень подробный отчёт по проекту " * 5
    response = await yandex_client.send(f"создай задачу {long_name.strip()}")
    assert "Готово" in response, f"Expected 'Готово' in response: {response}"


async def test_long_task_complete(
    yandex_client: YandexDialogsClient,
) -> None:
    """Complete a task with a long name — should not be UNKNOWN."""
    long_name = "кктест " + "подготовить очень подробный отчёт по проекту " * 3
    response = await yandex_client.send(f"отметь задачу {long_name.strip()}")
    assert response != UNKNOWN, f"Intent not recognized: {response}"


# ---------------------------------------------------------------------------
# Numbers in names (2 tests)
# ---------------------------------------------------------------------------


async def test_number_in_name(yandex_client: YandexDialogsClient) -> None:
    """Create a task with numbers in the name."""
    response = await yandex_client.send("создай задачу кктест купить 3 литра молока")
    assert "Готово" in response, f"Expected 'Готово' in response: {response}"


async def test_number_in_search(
    yandex_client: YandexDialogsClient,
) -> None:
    """Search for a task with a number in the query."""
    response = await yandex_client.send("найди задачу про 10 страницу")
    assert response != UNKNOWN, f"Intent not recognized: {response}"


# ---------------------------------------------------------------------------
# Empty / no-result lists (2 tests)
# ---------------------------------------------------------------------------


async def test_empty_today(yandex_client: YandexDialogsClient) -> None:
    """List today's tasks — may have tasks or 'задач нет'."""
    response = await yandex_client.send("что на сегодня")
    assert response != UNKNOWN, f"Intent not recognized: {response}"


async def test_no_overdue(yandex_client: YandexDialogsClient) -> None:
    """Check for overdue tasks."""
    response = await yandex_client.send("какие задачи просрочены")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "просроченных" in response.lower(), f"Expected overdue-related response: {response}"


# ---------------------------------------------------------------------------
# Similar names — best match (1 test)
# ---------------------------------------------------------------------------


async def test_similar_names_best_match(
    yandex_client: YandexDialogsClient,
) -> None:
    """Complete a task with a partial name — fuzzy match should handle it."""
    response = await yandex_client.send("отметь задачу кктест купить")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
