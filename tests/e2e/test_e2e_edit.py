"""E2E tests: Section 3.8 — Edit task (date, priority, rename, move, recurrence, reminder)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

TASK_NAME = "кктест редактирования"


def _edit_ok(response: str, *success_words: str) -> bool:
    """Check that the response contains any of the expected outcome words."""
    r = response.lower()
    return any(w in r for w in success_words)


# --- Date and priority ---


async def test_edit_date(yandex_client: YandexDialogsClient) -> None:
    """Edit task date: перенеси задачу на завтра."""
    response = await yandex_client.send(f"перенеси задачу {TASK_NAME} на завтра")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "обновлена")


async def test_edit_priority(yandex_client: YandexDialogsClient) -> None:
    """Edit task priority: поменяй приоритет на высокий."""
    response = await yandex_client.send(f"поменяй приоритет задачи {TASK_NAME} на высокий")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "обновлена")


async def test_edit_date_monday(yandex_client: YandexDialogsClient) -> None:
    """Edit task date to Monday: перенеси задачу на понедельник."""
    response = await yandex_client.send(f"перенеси задачу {TASK_NAME} на понедельник")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "обновлена")


# --- Rename ---


async def test_edit_rename(yandex_client: YandexDialogsClient) -> None:
    """Rename task: переименуй задачу X в Y."""
    response = await yandex_client.send(f"переименуй задачу {TASK_NAME} в кктест переименования")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "обновлена")


# --- Move between projects ---


async def test_edit_move_project(yandex_client: YandexDialogsClient) -> None:
    """Move task to project: перемести задачу в проект."""
    response = await yandex_client.send(f"перемести задачу {TASK_NAME} в проект Inbox")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "перемещена", "уже в проекте")


async def test_edit_move_project_alt(yandex_client: YandexDialogsClient) -> None:
    """Move task to project (alt phrasing): перекинь задачу в список."""
    response = await yandex_client.send(f"перекинь задачу {TASK_NAME} в список Inbox")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "перемещена", "уже в проекте")


# --- Recurrence changes ---


@pytest.mark.xfail(
    reason="Transient TickTick API error (timeout/rate limit in _gather_all_tasks)",
    strict=False,
)
async def test_edit_recurrence_daily(yandex_client: YandexDialogsClient) -> None:
    """Edit recurrence to daily."""
    response = await yandex_client.send(f"поменяй повторение задачи {TASK_NAME} на каждый день")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


@pytest.mark.xfail(
    reason="Transient TickTick API error (timeout/rate limit in _gather_all_tasks)",
    strict=False,
)
async def test_edit_recurrence_weekly(yandex_client: YandexDialogsClient) -> None:
    """Edit recurrence to weekly."""
    response = await yandex_client.send(f"измени повтор задачи {TASK_NAME} на каждую неделю")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


async def test_edit_recurrence_monthly(yandex_client: YandexDialogsClient) -> None:
    """Edit recurrence to monthly (15th)."""
    response = await yandex_client.send(
        f"поменяй повторение задачи {TASK_NAME} на каждое 15 число"
    )
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


# --- Remove recurrence ---


async def test_edit_remove_recurrence(yandex_client: YandexDialogsClient) -> None:
    """Remove recurrence: убери повторение."""
    response = await yandex_client.send(f"убери повторение задачи {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "убрано")


async def test_edit_remove_recurrence_alt(yandex_client: YandexDialogsClient) -> None:
    """Remove recurrence (alt phrasing): отмени повтор."""
    response = await yandex_client.send(f"отмени повтор задачи {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "убрано")


# --- Reminder changes ---


async def test_edit_reminder_30min(yandex_client: YandexDialogsClient) -> None:
    """Edit reminder to 30 minutes."""
    response = await yandex_client.send(f"поменяй напоминание задачи {TASK_NAME} за 30 минут")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


@pytest.mark.xfail(
    reason="Transient TickTick API error (timeout/rate limit in _gather_all_tasks)",
    strict=False,
)
async def test_edit_reminder_hour(yandex_client: YandexDialogsClient) -> None:
    """Edit reminder to 1 hour."""
    response = await yandex_client.send(f"измени напоминание задачи {TASK_NAME} за час")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


async def test_edit_reminder_day(yandex_client: YandexDialogsClient) -> None:
    """Edit reminder to 1 day."""
    response = await yandex_client.send(f"измени напоминание задачи {TASK_NAME} за 1 день")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "изменено")


# --- Remove reminder ---


async def test_edit_remove_reminder(yandex_client: YandexDialogsClient) -> None:
    """Remove reminder: убери напоминание."""
    response = await yandex_client.send(f"убери напоминание задачи {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "убрано")


async def test_edit_remove_reminder_alt(yandex_client: YandexDialogsClient) -> None:
    """Remove reminder (alt phrasing): отмени напоминание."""
    response = await yandex_client.send(f"отмени напоминание задачи {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert _edit_ok(response, "убрано")
