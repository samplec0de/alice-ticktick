"""Tests for Alice skill handlers."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    ALICE_RESPONSE_MAX_LENGTH,
    _truncate_response,
    handle_complete_task,
    handle_create_task,
    handle_delete_confirm,
    handle_delete_reject,
    handle_delete_task,
    handle_edit_task,
    handle_goodbye,
    handle_help,
    handle_list_tasks,
    handle_overdue_tasks,
    handle_search_task,
    handle_unknown,
    handle_welcome,
)
from alice_ticktick.dialogs.router import _MAX_CONFIRM_RETRIES, on_delete_other
from alice_ticktick.dialogs.states import DeleteTaskStates
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
    client.get_inbox_tasks = AsyncMock(return_value=[])
    client.create_task = AsyncMock(return_value=tasks[0] if tasks else _make_task())
    client.complete_task = AsyncMock(return_value=None)
    client.update_task = AsyncMock(return_value=tasks[0] if tasks else _make_task())
    client.delete_task = AsyncMock(return_value=None)

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


async def test_handle_goodbye() -> None:
    message = _make_message()
    response = await handle_goodbye(message)
    assert response.text == txt.GOODBYE
    assert response.end_session is True


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


async def test_search_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_search_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED


async def test_edit_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_edit_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED


async def test_delete_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    state = _make_mock_state()
    response = await handle_delete_task(message, intent_data, state)
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

    # Verify task goes to inbox (no projectId in payload)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_projects.assert_not_called()
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id is None


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


# --- Truncation ---


class TestTruncateResponse:
    def test_short_text_unchanged(self) -> None:
        assert _truncate_response("hello") == "hello"

    def test_exact_limit_unchanged(self) -> None:
        text = "a" * ALICE_RESPONSE_MAX_LENGTH
        assert _truncate_response(text) == text

    def test_long_text_truncated(self) -> None:
        text = "a" * (ALICE_RESPONSE_MAX_LENGTH + 100)
        result = _truncate_response(text)
        assert len(result) == ALICE_RESPONSE_MAX_LENGTH
        assert result.endswith("…")


# --- Gather all tasks (parallel) ---


async def test_list_tasks_parallel_fetch() -> None:
    """Verify tasks are fetched from all projects in parallel."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    projects = [
        _make_project(project_id="p1", name="Project 1"),
        _make_project(project_id="p2", name="Project 2"),
    ]
    tasks_p1 = [_make_task(task_id="t1", title="Task A", project_id="p1", due_date=today)]
    tasks_p2 = [_make_task(task_id="t2", title="Task B", project_id="p2", due_date=today)]

    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(side_effect=[tasks_p1, tasks_p2])
    client.get_inbox_tasks = AsyncMock(return_value=[])

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_list_tasks(message, intent_data, factory)

    assert "Task A" in response.text
    assert "Task B" in response.text
    assert client.get_tasks.call_count == 2


async def test_list_tasks_includes_inbox() -> None:
    """Verify inbox tasks are included alongside project tasks."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    inbox_task = _make_task(
        task_id="t-inbox",
        title="Inbox Task",
        project_id="inbox123",
        due_date=today,
    )
    project_task = _make_task(
        task_id="t-proj",
        title="Project Task",
        project_id="p1",
        due_date=today,
    )

    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=[_make_project(project_id="p1")])
    client.get_tasks = AsyncMock(return_value=[project_task])
    client.get_inbox_tasks = AsyncMock(return_value=[inbox_task])

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_list_tasks(message, intent_data, factory)

    assert "Inbox Task" in response.text
    assert "Project Task" in response.text
    client.get_inbox_tasks.assert_called_once()


# --- FSM state helper ---


def _make_mock_state(data: dict[str, Any] | None = None) -> AsyncMock:
    """Create a mock FSMContext."""
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.set_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# --- Search task ---


async def test_search_task_query_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_search_task(message, intent_data)
    assert response.text == txt.SEARCH_QUERY_REQUIRED


async def test_search_task_success() -> None:
    tasks = [
        _make_task(title="Купить молоко"),
        _make_task(task_id="t2", title="Купить хлеб"),
        _make_task(task_id="t3", title="Позвонить маме"),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"query": {"value": "купить"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "Купить хлеб" in response.text


async def test_search_task_no_results() -> None:
    tasks = [_make_task(title="Совсем другая задача")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"query": {"value": "xxxxxx"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "ничего не найдено" in response.text


async def test_search_task_api_error() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"query": {"value": "тест"}},
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_search_task(message, intent_data, mock_factory)
    assert response.text == txt.API_ERROR


# --- Edit task ---


async def test_edit_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_edit_task(message, intent_data)
    assert response.text == txt.EDIT_NAME_REQUIRED


async def test_edit_task_no_changes() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Купить молоко"}},
    }
    response = await handle_edit_task(message, intent_data)
    assert response.text == txt.EDIT_NO_CHANGES


async def test_edit_task_reschedule() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "обновлена" in response.text
    assert "Купить молоко" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.due_date is not None
    assert isinstance(call_args.due_date, datetime.datetime)


async def test_edit_task_change_priority() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.priority == 5  # TaskPriority.HIGH


async def test_edit_task_rename() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_name": {"value": "Купить кефир"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.title == "Купить кефир"


async def test_edit_task_not_found() -> None:
    tasks = [_make_task(title="Совсем другая задача")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "xxxxxx"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "не найдена" in response.text


async def test_edit_task_fetch_api_error() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "тест"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert response.text == txt.API_ERROR


async def test_edit_task_update_api_error() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.update_task = AsyncMock(side_effect=Exception("API error"))
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert response.text == txt.EDIT_ERROR


# --- Delete task ---


async def test_delete_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    state = _make_mock_state()
    response = await handle_delete_task(message, intent_data, state)
    assert response.text == txt.DELETE_NAME_REQUIRED


async def test_delete_task_starts_confirmation() -> None:
    tasks = [_make_task(title="Купить молоко", task_id="t1", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    state = _make_mock_state()
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_delete_task(message, intent_data, state, mock_factory)
    assert "Удалить задачу" in response.text
    assert "Купить молоко" in response.text
    state.set_state.assert_called_once_with(DeleteTaskStates.confirm)
    state.set_data.assert_called_once()
    call_data = state.set_data.call_args[0][0]
    assert call_data["task_id"] == "t1"
    assert call_data["project_id"] == "p1"


async def test_delete_confirm_success() -> None:
    message = _make_message()
    state = _make_mock_state(
        data={"task_id": "t1", "project_id": "p1", "task_name": "Купить молоко"}
    )
    mock_factory = _make_mock_client()
    response = await handle_delete_confirm(message, state, mock_factory)
    assert "удалена" in response.text
    assert "Купить молоко" in response.text
    state.clear.assert_called_once()


async def test_delete_reject() -> None:
    message = _make_message()
    state = _make_mock_state(
        data={"task_id": "t1", "project_id": "p1", "task_name": "Купить молоко"}
    )
    response = await handle_delete_reject(message, state)
    assert response.text == txt.DELETE_CANCELLED
    state.clear.assert_called_once()


async def test_delete_confirm_api_error() -> None:
    """Verify DELETE_ERROR returned and state.clear() called on API error."""
    message = _make_message()
    state = _make_mock_state(
        data={"task_id": "t1", "project_id": "p1", "task_name": "Купить молоко"}
    )
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("API error"))
    response = await handle_delete_confirm(message, state, mock_factory)
    assert response.text == txt.DELETE_ERROR
    state.clear.assert_called_once()


async def test_delete_confirm_auth_required() -> None:
    """Verify AUTH_REQUIRED returned and state.clear() called when no token."""
    message = _make_message(access_token=None)
    state = _make_mock_state(
        data={"task_id": "t1", "project_id": "p1", "task_name": "Купить молоко"}
    )
    response = await handle_delete_confirm(message, state)
    assert response.text == txt.AUTH_REQUIRED
    state.clear.assert_called_once()


async def test_delete_confirm_corrupted_state() -> None:
    """Verify DELETE_ERROR and state.clear() when state data is empty/corrupted."""
    message = _make_message()
    state = _make_mock_state(data={})  # No task_id, project_id, task_name
    response = await handle_delete_confirm(message, state)
    assert response.text == txt.DELETE_ERROR
    state.clear.assert_called_once()


async def test_delete_task_api_error() -> None:
    """Verify API_ERROR returned when task fetch fails during delete."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "тест"}},
    }
    state = _make_mock_state()
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(side_effect=Exception("API error"))
    response = await handle_delete_task(message, intent_data, state, mock_factory)
    assert response.text == txt.API_ERROR


async def test_delete_other_reprompts_before_max_retries() -> None:
    """Verify DELETE_CONFIRM_PROMPT returned and retry counter incremented when retries < max."""
    message = _make_message()
    state = _make_mock_state(data={"task_id": "t1", "project_id": "p1", "_confirm_retries": 0})
    response = await on_delete_other(message, state)
    assert response.text == txt.DELETE_CONFIRM_PROMPT
    state.clear.assert_not_called()
    state.set_data.assert_called_once()
    updated_data = state.set_data.call_args[0][0]
    assert updated_data["_confirm_retries"] == 1


async def test_delete_other_escape_after_retries() -> None:
    """Verify state cleared after _MAX_CONFIRM_RETRIES unexpected inputs."""
    message = _make_message()
    state = _make_mock_state(data={"_confirm_retries": _MAX_CONFIRM_RETRIES - 1})
    response = await on_delete_other(message, state)
    assert response.text == txt.DELETE_CANCELLED
    state.clear.assert_called_once()


# --- Search edge cases ---


async def test_search_task_all_completed() -> None:
    """Verify SEARCH_NO_RESULTS when all tasks are completed."""
    tasks = [_make_task(title="Купить молоко", status=2)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"query": {"value": "купить"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "ничего не найдено" in response.text
