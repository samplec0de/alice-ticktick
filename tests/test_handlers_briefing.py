"""Tests for morning/evening briefing handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _build_evening_briefing_text,
    _build_morning_briefing_text,
    _reset_project_cache,
    handle_evening_briefing,  # noqa: F401
    handle_morning_briefing,  # noqa: F401
)
from alice_ticktick.ticktick.models import Project, Task

if TYPE_CHECKING:
    import datetime


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
    result = _build_morning_briefing_text(today_tasks=[], overdue_tasks=[], tz=UTC)
    assert result == txt.MORNING_BRIEFING_NO_TASKS


def test_morning_briefing_text_no_tasks_with_overdue() -> None:
    overdue = [_make_task(title="A"), _make_task(task_id="t2", title="B")]
    result = _build_morning_briefing_text(today_tasks=[], overdue_tasks=overdue, tz=UTC)
    assert "2" in result
    assert "просроч" in result.lower()


def test_morning_briefing_text_tasks_no_overdue() -> None:
    today = [_make_task(title="Задача 1")]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[], tz=UTC)
    assert "Задача 1" in result
    assert "просроч" not in result.lower()


def test_morning_briefing_text_tasks_with_overdue() -> None:
    today = [_make_task(title="Задача 1")]
    overdue = [_make_task(task_id="t2", title="Старая задача")]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=overdue, tz=UTC)
    assert "Задача 1" in result
    assert "1" in result  # overdue count
    assert "просроч" in result.lower()


def test_morning_briefing_text_caps_at_five() -> None:
    today = [_make_task(task_id=str(i), title=f"T{i}") for i in range(10)]
    result = _build_morning_briefing_text(today_tasks=today, overdue_tasks=[], tz=UTC)
    assert "T6" not in result  # только первые 5


# --- _build_evening_briefing_text ---


def test_evening_briefing_text_no_tasks() -> None:
    result = _build_evening_briefing_text(tomorrow_tasks=[], tz=UTC)
    assert result == txt.EVENING_BRIEFING_NO_TASKS


def test_evening_briefing_text_with_tasks() -> None:
    tomorrow = [_make_task(title="Завтрашняя задача")]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, tz=UTC)
    assert "Завтрашняя задача" in result
    assert "завтра" in result.lower()


def test_evening_briefing_text_caps_at_five() -> None:
    tomorrow = [_make_task(task_id=str(i), title=f"T{i}") for i in range(10)]
    result = _build_evening_briefing_text(tomorrow_tasks=tomorrow, tz=UTC)
    assert "T6" not in result
