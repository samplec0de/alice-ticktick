"""Tests for Alice skill handlers."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    handle_complete_task,
    handle_create_task,
    handle_help,
    handle_list_tasks,
    handle_overdue_tasks,
    handle_unknown,
    handle_welcome,
)
from alice_ticktick.ticktick.models import Project, Task


def _make_message(
    *,
    access_token: str | None = "test-token",
    new: bool = False,
    command: str = "",
    intents: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Message object."""
    message = MagicMock()
    message.command = command
    message.original_utterance = command
    message.session.new = new
    message.session.session_id = "test-session-id"
    message.session.skill_id = "test-skill-id"

    if access_token is not None:
        message.user = MagicMock()
        message.user.access_token = access_token
    else:
        message.user = None

    if intents is not None:
        message.nlu = MagicMock()
        message.nlu.intents = intents
    else:
        message.nlu = None

    return message


def _make_task(
    *,
    task_id: str = "task-1",
    title: str = "Test task",
    project_id: str = "proj-1",
    priority: int = 0,
    status: int = 0,
    due_date: datetime.datetime | None = None,
) -> Task:
    """Create a Task instance."""
    return Task(
        id=task_id,
        title=title,
        projectId=project_id,
        priority=priority,
        status=status,
        dueDate=due_date,
    )


def _make_project(*, project_id: str = "proj-1", name: str = "Inbox") -> Project:
    """Create a Project instance."""
    return Project(id=project_id, name=name)


def _make_mock_client(
    projects: list[Project] | None = None,
    tasks: list[Task] | None = None,
) -> type:
    """Create a mock TickTickClient factory class."""
    if projects is None:
        projects = [_make_project()]
    if tasks is None:
        tasks = []

    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(return_value=tasks)
    client.create_task = AsyncMock(return_value=tasks[0] if tasks else _make_task())
    client.complete_task = AsyncMock(return_value=None)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    return factory


# --- Welcome / Help ---


async def test_handle_welcome() -> None:
    message = _make_message(new=True)
    response = await handle_welcome(message)
    assert response.text == txt.WELCOME


async def test_handle_help() -> None:
    message = _make_message()
    response = await handle_help(message)
    assert response.text == txt.HELP


async def test_handle_unknown() -> None:
    message = _make_message()
    response = await handle_unknown(message)
    assert response.text == txt.UNKNOWN


# --- Auth required ---


async def test_create_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED


async def test_list_tasks_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_list_tasks(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED


async def test_overdue_tasks_auth_required() -> None:
    message = _make_message(access_token=None)
    response = await handle_overdue_tasks(message)
    assert response.text == txt.AUTH_REQUIRED


async def test_complete_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_complete_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED


# --- Create task ---


async def test_create_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED


async def test_create_task_success() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Купить молоко"}},
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "Готово" in response.text


async def test_create_task_with_date() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Купить молоко"},
            "date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "завтра" in response.text


async def test_create_task_with_priority() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Важное дело"},
            "priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Важное дело" in response.text


async def test_create_task_api_error() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Тест"}},
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_create_task(message, intent_data, mock_factory)
    assert response.text == txt.CREATE_ERROR


# --- List tasks ---


async def test_list_tasks_no_tasks() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    mock_factory = _make_mock_client(tasks=[])
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert response.text == txt.NO_TASKS_TODAY


async def test_list_tasks_with_tasks() -> None:
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Задача 1", priority=5, due_date=today),
        _make_task(task_id="task-2", title="Задача 2", due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Задача 1" in response.text
    assert "Задача 2" in response.text
    assert "сегодня" in response.text


async def test_list_tasks_for_specific_date() -> None:
    tomorrow = datetime.datetime.now(tz=datetime.UTC).date() + datetime.timedelta(days=1)
    tomorrow_dt = datetime.datetime.combine(
        tomorrow,
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [_make_task(title="Завтрашняя", due_date=tomorrow_dt)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"date": {"value": {"day": 1, "day_is_relative": True}}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Завтрашняя" in response.text
    assert "завтра" in response.text


async def test_list_tasks_api_error() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert response.text == txt.API_ERROR


# --- Overdue tasks ---


async def test_overdue_tasks_none() -> None:
    message = _make_message()
    mock_factory = _make_mock_client(tasks=[])
    response = await handle_overdue_tasks(message, mock_factory)
    assert response.text == txt.NO_OVERDUE


async def test_overdue_tasks_found() -> None:
    yesterday = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date() - datetime.timedelta(days=1),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [_make_task(title="Просроченная", due_date=yesterday)]
    message = _make_message()
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_overdue_tasks(message, mock_factory)
    assert "Просроченная" in response.text


async def test_overdue_tasks_api_error() -> None:
    message = _make_message()
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_overdue_tasks(message, mock_factory)
    assert response.text == txt.API_ERROR


# --- Complete task ---


async def test_complete_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_complete_task(message, intent_data)
    assert response.text == txt.COMPLETE_NAME_REQUIRED


async def test_complete_task_success() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "выполненной" in response.text


async def test_complete_task_not_found() -> None:
    tasks = [_make_task(title="Совсем другая задача")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "xxxxxx"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, mock_factory)
    assert "не найдена" in response.text


async def test_complete_task_no_active_tasks() -> None:
    tasks = [_make_task(title="Done", status=2)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Done"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, mock_factory)
    assert "не найдена" in response.text


async def test_complete_task_api_error() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Тест"}},
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_complete_task(message, intent_data, mock_factory)
    assert response.text == txt.COMPLETE_ERROR


# --- Responses ---


class TestPluralizeTask:
    def test_one(self) -> None:
        assert txt.pluralize_tasks(1) == "1 задача"

    def test_two(self) -> None:
        assert txt.pluralize_tasks(2) == "2 задачи"

    def test_five(self) -> None:
        assert txt.pluralize_tasks(5) == "5 задач"

    def test_eleven(self) -> None:
        assert txt.pluralize_tasks(11) == "11 задач"

    def test_twenty_one(self) -> None:
        assert txt.pluralize_tasks(21) == "21 задача"

    def test_twenty_two(self) -> None:
        assert txt.pluralize_tasks(22) == "22 задачи"
