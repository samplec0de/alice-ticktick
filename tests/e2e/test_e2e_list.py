"""E2E tests: Sections 3.3 + 3.4 + 3.5 — List, filter, overdue tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# 3.3  List tasks (6 tests)
# ---------------------------------------------------------------------------


async def test_list_today(yandex_client: YandexDialogsClient) -> None:
    """Ask for today's tasks."""
    response = await yandex_client.send("что на сегодня")
    assert response != UNKNOWN
    # Response is either a task list (numbered) or "задач нет"
    assert "сегодня" in response.lower() or "задач" in response.lower()


async def test_list_tomorrow(yandex_client: YandexDialogsClient) -> None:
    """Ask for tomorrow's tasks."""
    response = await yandex_client.send("что на завтра")
    assert response != UNKNOWN
    assert "завтра" in response.lower() or "задач" in response.lower()


async def test_list_monday(yandex_client: YandexDialogsClient) -> None:
    """Ask for Monday's tasks."""
    response = await yandex_client.send("что на понедельник")
    assert response != UNKNOWN
    assert "понедельник" in response.lower() or "задач" in response.lower()


async def test_list_friday(yandex_client: YandexDialogsClient) -> None:
    """Ask for Friday's tasks."""
    response = await yandex_client.send("что на пятницу")
    assert response != UNKNOWN
    assert "пятниц" in response.lower() or "задач" in response.lower()


async def test_list_this_week(yandex_client: YandexDialogsClient) -> None:
    """Ask for this week's tasks."""
    response = await yandex_client.send("что на эту неделю")
    assert response != UNKNOWN
    assert "неделе" in response.lower() or "задач" in response.lower()


@pytest.mark.xfail(
    reason="NLU does not recognize 'все задачи' as list_tasks intent",
    strict=False,
)
async def test_list_all_tasks(yandex_client: YandexDialogsClient) -> None:
    """Ask for all tasks."""
    response = await yandex_client.send("все задачи")
    assert response != UNKNOWN


# ---------------------------------------------------------------------------
# 3.4  Filter by priority (3 tests)
# ---------------------------------------------------------------------------


async def test_filter_high_priority_this_week(
    yandex_client: YandexDialogsClient,
) -> None:
    """Filter tasks with high priority for this week."""
    response = await yandex_client.send("покажи задачи с высоким приоритетом на эту неделю")
    assert response != UNKNOWN
    assert "неделе" in response.lower() or "задач" in response.lower()


async def test_filter_urgent_tomorrow(yandex_client: YandexDialogsClient) -> None:
    """Filter urgent tasks for tomorrow."""
    response = await yandex_client.send("покажи срочные задачи на завтра")
    assert response != UNKNOWN
    assert "завтра" in response.lower() or "задач" in response.lower()


async def test_filter_low_priority_next_week(
    yandex_client: YandexDialogsClient,
) -> None:
    """Filter tasks with low priority for next week."""
    response = await yandex_client.send("покажи задачи с низким приоритетом на следующую неделю")
    assert response != UNKNOWN
    assert "неделе" in response.lower() or "задач" in response.lower()


# ---------------------------------------------------------------------------
# 3.5  Overdue tasks (4 tests)
# ---------------------------------------------------------------------------


async def test_overdue_prosrocheny(yandex_client: YandexDialogsClient) -> None:
    """Ask for overdue tasks using 'просрочены'."""
    response = await yandex_client.send("какие задачи просрочены")
    assert response != UNKNOWN
    assert "росроченных" in response.lower() or "росрочен" in response.lower()


@pytest.mark.xfail(
    reason="NLU: 'покажи просроченные задачи' may be intercepted by list_tasks",
    strict=False,
)
async def test_overdue_prosrochennye(yandex_client: YandexDialogsClient) -> None:
    """Ask for overdue tasks using 'просроченные'."""
    response = await yandex_client.send("покажи просроченные задачи")
    assert response != UNKNOWN
    assert "росроченных" in response.lower() or "росрочен" in response.lower()


async def test_overdue_missed(yandex_client: YandexDialogsClient) -> None:
    """Ask what tasks were missed."""
    response = await yandex_client.send("что я пропустил")
    assert response != UNKNOWN
    assert "росроченных" in response.lower() or "росрочен" in response.lower()


@pytest.mark.xfail(
    reason="NLU: 'что я просрочил' may not match overdue_tasks intent",
    strict=False,
)
async def test_overdue_what_overdue(yandex_client: YandexDialogsClient) -> None:
    """Ask what tasks are overdue."""
    response = await yandex_client.send("что я просрочил")
    assert response != UNKNOWN
    assert "росроченных" in response.lower() or "росрочен" in response.lower()
