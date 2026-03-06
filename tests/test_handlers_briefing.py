"""Tests for morning/evening briefing handlers."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _build_evening_briefing_text,
    _build_morning_briefing_text,
    _reset_project_cache,
    handle_evening_briefing,
    handle_morning_briefing,
)
from alice_ticktick.ticktick.models import Project, Task


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _reset_project_cache()


def _make_task(
    *,
    task_id: str = "t1",
    title: str = "Test",
    due_date: datetime.datetime | None = None,
    status: int = 0,
) -> Task:
    return Task(
        id=task_id,
        title=title,
        projectId="proj-1",
        priority=0,
        status=status,
        dueDate=due_date,
    )


def _make_message(*, access_token: str | None = "token") -> MagicMock:
    msg = MagicMock()
    msg.command = ""
    msg.nlu = None
    if access_token is not None:
        msg.user = MagicMock()
        msg.user.access_token = access_token
    else:
        msg.user = None
    return msg


def _make_mock_client(tasks: list[Task]) -> MagicMock:
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=[Project(id="proj-1", name="Inbox")])
    client.get_tasks = AsyncMock(return_value=tasks)
    client.get_inbox_tasks = AsyncMock(return_value=[])
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


UTC = ZoneInfo("UTC")


# --- _build_morning_briefing_text ---


def test_morning_briefing_text_no_tasks_no_overdue() -> None:
    result = _build_morning_briefing_text(today_tasks=[], overdue_tasks=[])
    assert result == txt.MORNING_BRIEFING_NO_TASKS


def test_morning_briefing_text_no_tasks_with_overdue() -> None:
    overdue = [_make_task(title="A"), _make_task(task_id="t2", title="B")]
    result = _build_morning_briefing_text(today_tasks=[], overdue_tasks=overdue)
    assert "2" in result
    assert "просроч" in result.lower()


def test_morning_briefing_text_tasks_no_overdue() -> None:
    today = [_make_task(title="Задача 1")]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[])
    assert "Задача 1" in result
    assert "просроч" not in result.lower()


def test_morning_briefing_text_tasks_with_overdue() -> None:
    today = [_make_task(title="Задача 1")]
    overdue = [_make_task(task_id="t2", title="Старая задача")]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=overdue)
    assert "Задача 1" in result
    assert "1" in result  # overdue count
    assert "просроч" in result.lower()


def test_morning_briefing_text_caps_at_five() -> None:
    today = [_make_task(task_id=str(i), title=f"T{i}") for i in range(10)]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[])
    assert "T6" not in result  # только первые 5


def test_morning_briefing_text_shows_remaining_count() -> None:
    """UX-10: morning briefing with 7 tasks shows 5 + 'и ещё 2.'"""
    today = [_make_task(task_id=str(i), title=f"Задача {i}") for i in range(7)]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[])
    assert "и ещё 2" in result
    assert "Задача 0" in result
    assert "Задача 4" in result
    assert "Задача 5" not in result


def test_morning_briefing_text_no_remaining_when_five_or_less() -> None:
    today = [_make_task(task_id=str(i), title=f"Задача {i}") for i in range(5)]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[])
    assert "и ещё" not in result


# --- _build_evening_briefing_text ---


def test_evening_briefing_text_no_tasks() -> None:
    result = _build_evening_briefing_text(tomorrow_tasks=[], overdue_tasks=[])
    assert result == txt.EVENING_BRIEFING_NO_TASKS


def test_evening_briefing_text_no_tasks_with_overdue() -> None:
    overdue = [_make_task(title="A"), _make_task(task_id="t2", title="B")]
    result = _build_evening_briefing_text(tomorrow_tasks=[], overdue_tasks=overdue)
    assert "2" in result
    assert "просроч" in result.lower()


def test_evening_briefing_text_with_tasks() -> None:
    tomorrow = [_make_task(title="Завтрашняя задача")]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, overdue_tasks=[])
    assert "Завтрашняя задача" in result
    assert "завтра" in result.lower()


def test_evening_briefing_text_tasks_with_overdue() -> None:
    tomorrow = [_make_task(title="Завтрашняя задача")]
    overdue = [_make_task(task_id="t2", title="Старая")]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, overdue_tasks=overdue)
    assert "Завтрашняя задача" in result
    assert "просроч" in result.lower()


def test_evening_briefing_text_caps_at_five() -> None:
    tomorrow = [_make_task(task_id=str(i), title=f"T{i}") for i in range(10)]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, overdue_tasks=[])
    assert "T6" not in result


def test_evening_briefing_text_shows_remaining_count() -> None:
    """UX-10: evening briefing with 7 tasks shows 5 + 'и ещё 2.'"""
    tomorrow = [_make_task(task_id=str(i), title=f"Задача {i}") for i in range(7)]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, overdue_tasks=[])
    assert "и ещё 2" in result
    assert "Задача 0" in result
    assert "Задача 4" in result
    assert "Задача 5" not in result


def test_evening_briefing_text_no_remaining_when_five_or_less() -> None:
    tomorrow = [_make_task(task_id=str(i), title=f"Задача {i}") for i in range(5)]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, overdue_tasks=[])
    assert "и ещё" not in result


# --- handle_morning_briefing ---


async def test_morning_briefing_auth_required() -> None:
    msg = _make_message(access_token=None)
    response = await handle_morning_briefing(msg)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_morning_briefing_no_tasks() -> None:
    msg = _make_message()
    factory = _make_mock_client([])
    response = await handle_morning_briefing(msg, ticktick_client_factory=factory)
    assert response.text == txt.MORNING_BRIEFING_NO_TASKS


async def test_morning_briefing_with_today_tasks() -> None:
    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.now(tz=tz).replace(hour=12, microsecond=0)
    tasks = [_make_task(title="Задача сегодня", due_date=today)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_morning_briefing(msg, ticktick_client_factory=factory)
    assert "Задача сегодня" in response.text
    assert "Доброе утро" in response.text


async def test_morning_briefing_with_overdue() -> None:
    tz = ZoneInfo("UTC")
    yesterday = datetime.datetime.now(tz=tz) - datetime.timedelta(days=1)
    yesterday = yesterday.replace(hour=12, microsecond=0)
    tasks = [_make_task(title="Просроченная", due_date=yesterday)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_morning_briefing(msg, ticktick_client_factory=factory)
    assert "просроч" in response.text.lower()
    assert "задач нет" in response.text  # today has no tasks


async def test_morning_briefing_api_error() -> None:
    msg = _make_message()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("API down"))
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    response = await handle_morning_briefing(msg, ticktick_client_factory=factory)
    assert response.text == txt.API_ERROR


# --- handle_evening_briefing ---


async def test_evening_briefing_auth_required() -> None:
    msg = _make_message(access_token=None)
    response = await handle_evening_briefing(msg)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_evening_briefing_no_tasks() -> None:
    msg = _make_message()
    factory = _make_mock_client([])
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert response.text == txt.EVENING_BRIEFING_NO_TASKS


async def test_evening_briefing_with_tomorrow_tasks() -> None:
    tz = ZoneInfo("Europe/Moscow")
    tomorrow = (datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)).replace(
        hour=12, microsecond=0
    )
    tasks = [_make_task(title="Завтрашняя задача", due_date=tomorrow)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert "Завтрашняя задача" in response.text
    assert "Итоги дня" in response.text


async def test_evening_briefing_ignores_today_tasks() -> None:
    tz = ZoneInfo("UTC")
    today = datetime.datetime.now(tz=tz).replace(hour=12, microsecond=0)
    tasks = [_make_task(title="Сегодняшняя задача", due_date=today)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert "задач нет" in response.text  # tomorrow is empty


async def test_evening_briefing_with_overdue() -> None:
    tz = ZoneInfo("UTC")
    yesterday = (datetime.datetime.now(tz=tz) - datetime.timedelta(days=1)).replace(
        hour=12, microsecond=0
    )
    tasks = [_make_task(title="Просроченная", due_date=yesterday)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert "просроч" in response.text.lower()
    assert "задач нет" in response.text  # tomorrow is empty


async def test_evening_briefing_tomorrow_and_overdue() -> None:
    tz = ZoneInfo("Europe/Moscow")
    tomorrow = (datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)).replace(
        hour=12, microsecond=0
    )
    yesterday = (datetime.datetime.now(tz=tz) - datetime.timedelta(days=1)).replace(
        hour=12, microsecond=0
    )
    tasks = [
        _make_task(task_id="t1", title="Завтрашняя", due_date=tomorrow),
        _make_task(task_id="t2", title="Просроченная", due_date=yesterday),
    ]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert "Завтрашняя" in response.text
    assert "просроч" in response.text.lower()


async def test_morning_briefing_many_tasks_shows_remaining() -> None:
    """UX-10: morning briefing handler with 7 tasks shows 'и ещё 2'."""
    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.now(tz=tz).replace(hour=12, microsecond=0)
    tasks = [_make_task(task_id=str(i), title=f"Задача {i}", due_date=today) for i in range(7)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_morning_briefing(msg, ticktick_client_factory=factory)
    assert "и ещё 2" in response.text


async def test_evening_briefing_many_tasks_shows_remaining() -> None:
    """UX-10: evening briefing handler with 7 tasks shows 'и ещё 2'."""
    tz = ZoneInfo("Europe/Moscow")
    tomorrow = (datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)).replace(
        hour=12, microsecond=0
    )
    tasks = [_make_task(task_id=str(i), title=f"Задача {i}", due_date=tomorrow) for i in range(7)]
    msg = _make_message()
    factory = _make_mock_client(tasks)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert "и ещё 2" in response.text


async def test_evening_briefing_api_error() -> None:
    msg = _make_message()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("API down"))
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    response = await handle_evening_briefing(msg, ticktick_client_factory=factory)
    assert response.text == txt.API_ERROR
