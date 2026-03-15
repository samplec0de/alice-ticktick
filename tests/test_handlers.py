"""Tests for Alice skill handlers."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    ALICE_RESPONSE_MAX_LENGTH,
    _auth_required_response,
    _format_priority_label,
    _format_priority_short,
    _format_task_context,
    _reset_project_cache,
    _truncate_response,
    handle_add_reminder,
    handle_complete_task,
    handle_create_recurring_task,
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
from alice_ticktick.ticktick.client import TickTickUnauthorizedError
from alice_ticktick.ticktick.models import ChecklistItem, Project, Task


@pytest.fixture(autouse=True)
def _clear_project_cache() -> None:
    """Reset the project cache before each test."""
    _reset_project_cache()


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


def _make_state(data: dict[str, Any] | None = None) -> AsyncMock:
    """Create a mock FSMContext."""
    state = AsyncMock()
    _state_data = dict(data) if data else {}

    async def _get_data() -> dict[str, Any]:
        return dict(_state_data)

    async def _set_data(new_data: dict[str, Any]) -> None:
        _state_data.clear()
        _state_data.update(new_data)

    async def _clear() -> None:
        _state_data.clear()

    state.get_data = AsyncMock(side_effect=_get_data)
    state.set_data = AsyncMock(side_effect=_set_data)
    state.set_state = AsyncMock()
    state.clear = AsyncMock(side_effect=_clear)
    return state


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
    client.move_task = AsyncMock(return_value=None)
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
    assert response.tts == txt.WELCOME_TTS
    assert "Слушаю" in response.tts


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


# --- Auth required response helper ---


async def test_auth_required_no_linking_when_no_update() -> None:
    """Without event_update, returns NO_LINKING text and no directives."""
    response = _auth_required_response(None)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING
    assert response.directives is None


async def test_auth_required_no_linking_when_no_interfaces() -> None:
    """When meta.interfaces.account_linking is None, returns NO_LINKING."""
    mock_update = MagicMock()
    mock_update.meta.interfaces.account_linking = None
    response = _auth_required_response(mock_update)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING
    assert response.directives is None


async def test_auth_required_with_linking() -> None:
    """When account_linking is supported, returns LINKING text and directive."""
    mock_update = MagicMock()
    mock_update.meta.interfaces.account_linking = {}
    response = _auth_required_response(mock_update)
    assert response.text == txt.AUTH_REQUIRED_LINKING
    assert response.directives is not None
    assert response.directives.start_account_linking == {}


# --- Auth required ---


async def test_create_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_list_tasks_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_list_tasks(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_overdue_tasks_auth_required() -> None:
    message = _make_message(access_token=None)
    response = await handle_overdue_tasks(message)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_complete_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_complete_task(message, intent_data, _make_state())
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_search_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_search_task(message, intent_data)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_edit_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_edit_task(message, intent_data, _make_state())
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_delete_task_auth_required() -> None:
    message = _make_message(access_token=None)
    intent_data: dict[str, Any] = {"slots": {}}
    state = _make_mock_state()
    response = await handle_delete_task(message, intent_data, state)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


# --- Create task ---


async def test_create_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED


async def test_create_task_name_is_stopword_asks_for_name() -> None:
    """Если task_name — это только слово 'задачу', переспросить название."""
    message = _make_message(command="создай задачу")
    message.nlu = None
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задачу"}}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED


async def test_create_task_name_is_zadacha_variant_asks_for_name() -> None:
    """'задача', 'задачи' тоже стоп-слова."""
    message = _make_message(command="новая задача")
    message.nlu = None
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задача"}}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED


async def test_create_task_strips_reminder_suffix_from_name() -> None:
    """task_name 'встреча с напоминанием за 30 минут' -> должно стать 'встреча'."""
    message = _make_message(command="создай задачу встреча с напоминанием за 30 минут")
    message.nlu = None
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча с напоминанием за 30 минут"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        }
    }
    await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    created_payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert created_payload.title == "Встреча"


async def test_create_task_strips_reminder_suffix_without_value() -> None:
    """'позвонить врачу с напоминанием за час' -> 'Позвонить врачу'."""
    message = _make_message(command="создай задачу позвонить врачу с напоминанием за час")
    message.nlu = None
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "позвонить врачу с напоминанием за час"},
            "reminder_unit": {"value": "час"},
        }
    }
    await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    created_payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert created_payload.title == "Позвонить врачу"


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


async def test_create_task_with_time_range() -> None:
    """Create task with start and end time via NLU entities (hybrid approach)."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    # Simulates "добавь задачу кино на завтра с 19:00 до 21:30"
    # Tokens below match the utterance above
    # NLU entities: 2 DATETIME entities after command tokens (indices 0-1)
    entity_start = Entity(
        type="YANDEX.DATETIME",
        tokens=TokensEntity(start=3, end=7),
        value=DateTimeEntity(day=1, day_is_relative=True, hour=19, minute=0),
    )
    entity_end = Entity(
        type="YANDEX.DATETIME",
        tokens=TokensEntity(start=7, end=9),
        value=DateTimeEntity(hour=21, minute=30),
    )

    message = _make_message()
    message.nlu = MagicMock()
    message.nlu.tokens = ["добавь", "задачу", "кино", "на", "завтра", "с", "19:00", "до", "21:30"]
    message.nlu.entities = [entity_start, entity_end]

    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Кино"}},
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "кино" in response.text.lower()

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.start_date is not None
    assert call_args.due_date is not None
    assert call_args.start_date != call_args.due_date
    # start should be 19:00, end should be 21:30
    start_dt = datetime.datetime.strptime(call_args.start_date, "%Y-%m-%dT%H:%M:%S.000+0300")
    end_dt = datetime.datetime.strptime(call_args.due_date, "%Y-%m-%dT%H:%M:%S.000+0300")
    assert start_dt.hour == 19
    assert end_dt.hour == 21
    assert end_dt.minute == 30


async def test_create_task_without_end_date_no_start() -> None:
    """Create task with only date — no startDate, only dueDate."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Купить молоко"},
            "date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.start_date is None
    assert call_args.due_date is not None


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


async def test_create_task_with_priority_confirms() -> None:
    """Create task with priority shows priority in confirmation."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Важный отчёт"},
            "priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=[_make_task()])
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Важный отчёт" in response.text
    assert "приоритет" in response.text.lower()
    assert "высокий" in response.text.lower()


async def test_create_task_with_date_and_priority_confirms() -> None:
    """Create task with date + priority shows both."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Отчёт"},
            "priority": {"value": "средний"},
            "date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(tasks=[_make_task()])
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Отчёт" in response.text
    assert "завтра" in response.text
    assert "средний" in response.text.lower()


async def test_create_task_capitalizes_first_letter() -> None:
    """Task name should have its first letter capitalized."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.title == "Купить молоко"


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
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=tz).date(),
        datetime.time(),
        tzinfo=tz,
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
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    tomorrow = datetime.datetime.now(tz=tz).date() + datetime.timedelta(days=1)
    tomorrow_dt = datetime.datetime.combine(
        tomorrow,
        datetime.time(),
        tzinfo=tz,
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
    assert "Произошла ошибка при обращении к TickTick" in response.text


async def test_list_tasks_filter_by_priority() -> None:
    """Filter tasks by priority — only high-priority tasks returned."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=tz).date(),
        datetime.time(),
        tzinfo=tz,
    )
    tasks = [
        _make_task(title="Важная", priority=5, due_date=today),
        _make_task(task_id="task-2", title="Обычная", priority=0, due_date=today),
        _make_task(task_id="task-3", title="Ещё важная", priority=5, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "высокий"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Важная" in response.text
    assert "Ещё важная" in response.text
    assert "Обычная" not in response.text
    assert "высоким приоритетом" in response.text


async def test_list_tasks_filter_by_priority_no_matches() -> None:
    """Filter by priority when no tasks match — specific empty message."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Обычная", priority=0, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "высокий"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "высоким приоритетом" in response.text
    assert "нет" in response.text


async def test_list_tasks_filter_by_priority_with_date() -> None:
    """Filter tasks by priority + specific date."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    tomorrow = datetime.datetime.now(tz=tz).date() + datetime.timedelta(days=1)
    tomorrow_dt = datetime.datetime.combine(
        tomorrow,
        datetime.time(),
        tzinfo=tz,
    )
    tasks = [
        _make_task(title="Срочная", priority=5, due_date=tomorrow_dt),
        _make_task(task_id="task-2", title="Несрочная", priority=1, due_date=tomorrow_dt),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "date": {"value": {"day": 1, "day_is_relative": True}},
            "priority": {"value": "срочный"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Срочная" in response.text
    assert "Несрочная" not in response.text
    assert "завтра" in response.text


async def test_list_tasks_unknown_priority_ignored() -> None:
    """Unknown priority string — ignore filter, show all tasks."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=tz).date(),
        datetime.time(),
        tzinfo=tz,
    )
    tasks = [
        _make_task(title="Задача 1", priority=5, due_date=today),
        _make_task(task_id="task-2", title="Задача 2", priority=0, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "абракадабра"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Задача 1" in response.text
    assert "Задача 2" in response.text


# --- Overdue tasks ---


async def test_overdue_tasks_none() -> None:
    message = _make_message()
    mock_factory = _make_mock_client(tasks=[])
    response = await handle_overdue_tasks(message, ticktick_client_factory=mock_factory)
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
    response = await handle_overdue_tasks(message, ticktick_client_factory=mock_factory)
    assert "Просроченная" in response.text


async def test_overdue_tasks_api_error() -> None:
    message = _make_message()
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_overdue_tasks(message, ticktick_client_factory=mock_factory)
    assert "Произошла ошибка при обращении к TickTick" in response.text


# --- Complete task ---


async def test_complete_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_complete_task(message, intent_data, _make_state())
    assert response.text == txt.COMPLETE_NAME_REQUIRED


async def test_complete_task_success() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, _make_state(), mock_factory)
    assert "Купить молоко" in response.text
    assert "выполненной" in response.text


async def test_complete_task_not_found() -> None:
    tasks = [_make_task(title="Совсем другая задача")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "xxxxxx"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, _make_state(), mock_factory)
    assert "не найдена" in response.text


async def test_complete_task_no_active_tasks() -> None:
    tasks = [_make_task(title="Done", status=2)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Done"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, _make_state(), mock_factory)
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
    response = await handle_complete_task(message, intent_data, _make_state(), mock_factory)
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
        assert len(result) <= ALICE_RESPONSE_MAX_LENGTH
        assert result.endswith("…")

    def test_truncate_at_newline(self) -> None:
        """UX-9: _truncate_response breaks at last newline, not mid-word."""
        line1 = "a" * 600
        line2 = "b" * 600
        text = line1 + "\n" + line2
        result = _truncate_response(text)
        assert result == line1 + "\n…"
        assert len(result) <= ALICE_RESPONSE_MAX_LENGTH

    def test_truncate_no_good_newline_falls_back(self) -> None:
        """When newline is too early (< limit//2), truncate without newline."""
        text = "ab\n" + "c" * (ALICE_RESPONSE_MAX_LENGTH + 100)
        result = _truncate_response(text)
        assert len(result) <= ALICE_RESPONSE_MAX_LENGTH
        assert result.endswith("…")


# --- Gather all tasks (parallel) ---


async def test_list_tasks_parallel_fetch() -> None:
    """Verify tasks are fetched from all projects in parallel."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=tz).date(),
        datetime.time(),
        tzinfo=tz,
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
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=tz).date(),
        datetime.time(),
        tzinfo=tz,
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


async def test_list_tasks_timezone_filter() -> None:
    """Task due 2026-03-02 00:00 MSK (= 2026-03-01 21:00 UTC) should NOT appear for March 1."""
    # Due date stored as UTC: midnight March 2 MSK = 21:00 March 1 UTC
    due_utc = datetime.datetime(2026, 3, 1, 21, 0, tzinfo=datetime.UTC)
    task = _make_task(task_id="t1", title="Tomorrow Task", due_date=due_utc)

    factory = _make_mock_client(tasks=[task])

    message = _make_message()
    # Slot says "March 1" (today in MSK)
    intent_data: dict[str, Any] = {
        "slots": {
            "date": {
                "value": {
                    "day": 1,
                    "day_is_relative": False,
                    "month": 3,
                    "month_is_relative": False,
                    "year": 2026,
                    "year_is_relative": False,
                },
            },
        },
    }

    # Build a mock Update with Europe/Moscow timezone
    mock_update = MagicMock()
    mock_update.meta.timezone = "Europe/Moscow"

    response = await handle_list_tasks(
        message,
        intent_data,
        factory,
        event_update=mock_update,
    )
    # Task is March 2 in MSK — should NOT match March 1
    assert "Tomorrow Task" not in response.text


async def test_list_tasks_timezone_filter_matches() -> None:
    """Task due 2026-03-01 21:00 UTC (= March 2 MSK) should appear when querying March 2."""
    due_utc = datetime.datetime(2026, 3, 1, 21, 0, tzinfo=datetime.UTC)
    task = _make_task(task_id="t1", title="Tomorrow Task", due_date=due_utc)

    factory = _make_mock_client(tasks=[task])

    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "date": {
                "value": {
                    "day": 2,
                    "day_is_relative": False,
                    "month": 3,
                    "month_is_relative": False,
                    "year": 2026,
                    "year_is_relative": False,
                },
            },
        },
    }

    mock_update = MagicMock()
    mock_update.meta.timezone = "Europe/Moscow"

    response = await handle_list_tasks(
        message,
        intent_data,
        factory,
        event_update=mock_update,
    )
    assert "Tomorrow Task" in response.text


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
    assert "Произошла ошибка при обращении к TickTick" in response.text


# --- Edit task ---


async def test_edit_task_name_required() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    response = await handle_edit_task(message, intent_data, _make_state())
    assert response.text == txt.EDIT_NAME_REQUIRED


async def test_edit_task_no_changes() -> None:
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Купить молоко"}},
    }
    response = await handle_edit_task(message, intent_data, _make_state())
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
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text
    assert "Купить молоко" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.due_date is not None
    assert isinstance(call_args.due_date, datetime.datetime)
    # Single date: startDate must equal dueDate
    assert call_args.start_date is not None
    assert call_args.start_date == call_args.due_date


async def test_edit_task_reschedule_with_end_date() -> None:
    """When both new_date and new_end_date are given, startDate != dueDate."""
    tasks = [_make_task(title="Кино")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "кино"},
            "new_date": {"value": {"day": 5, "month": 3}},
            "new_end_date": {"value": {"day": 7, "month": 3}},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.start_date is not None
    assert call_args.due_date is not None
    assert call_args.start_date != call_args.due_date
    assert call_args.start_date.day == 5
    assert call_args.due_date.day == 7


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
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.priority == 5  # TaskPriority.HIGH


async def test_edit_task_rename() -> None:
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message(command="переименуй задачу купить молоко в купить кефир")
    message.nlu = MagicMock()
    message.nlu.tokens = ["переименуй", "задачу", "купить", "молоко", "в", "купить", "кефир"]
    message.nlu.entities = []
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_name": {"value": "Купить кефир"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.title == "Купить кефир"


async def test_edit_task_reschedule_with_v_in_name() -> None:
    """'Перенеси задачу сходить в озон на сегодня' must NOT rename."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    tasks = [_make_task(title="Сходить в Озон")]
    message = _make_message(command="перенеси задачу сходить в озон на сегодня")
    message.nlu = MagicMock()
    message.nlu.tokens = [
        "перенеси",
        "задачу",
        "сходить",
        "в",
        "озон",
        "на",
        "сегодня",
    ]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=5, end=7),
            value=DateTimeEntity(day=0, day_is_relative=True),
        ),
    ]
    # Grammar splits: task_name="сходить", new_name="озон на сегодня"
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "сходить"},
            "new_name": {"value": "озон на сегодня"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    state = _make_state()
    # NLU task_name = "сходить в озон" (clean, after removing date tokens) → high fuzzy score
    # → edit goes through without confirmation
    response = await handle_edit_task(message, intent_data, state, mock_factory)
    assert "Сходить в Озон" in response.text
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.title is None
    assert call_args.due_date is not None


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
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
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
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "Произошла ошибка при обращении к TickTick" in response.text


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
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert response.text == txt.EDIT_ERROR


async def test_edit_task_via_nlu_entities() -> None:
    """Edit task date via NLU entities when grammar .+ swallows date tokens."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    # "перенеси задачу купить молоко на сегодня"
    message.nlu = MagicMock()
    message.nlu.tokens = ["перенеси", "задачу", "купить", "молоко", "на", "сегодня"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=4, end=6),
            value=DateTimeEntity(day=0, day_is_relative=True),
        ),
    ]
    # Grammar swallowed date: task_name contains "на сегодня" but no new_date
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко на сегодня"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    # task_name "купить молоко на сегодня" vs "Купить молоко" → score ~70 < 85
    # Skip confirmation to test the edit logic itself
    response = await handle_edit_task(
        message, intent_data, _make_state(), mock_factory, _skip_confirm=True
    )
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.update_task.call_args[0][0]
    assert call_args.due_date is not None


async def test_edit_task_uses_nlu_task_name_when_grammar_swallowed_date() -> None:
    """When grammar .+ swallows date into task_name, NLU entity provides clean name for search."""
    from aliceio.types import DateTimeEntity

    tasks = [_make_task(title="Купить хлеб")]
    # Grammar зафиксировало task_name="купить хлеб на завтра" (дата поглощена)
    message = _make_message(command="перенеси задачу купить хлеб на завтра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перенеси", "задачу", "купить", "хлеб", "на", "завтра"]

    dt_value = MagicMock(spec=DateTimeEntity)
    dt_value.day = 1
    dt_value.day_is_relative = True
    dt_value.year = None
    dt_value.month = None
    dt_value.hour = None
    dt_value.minute = None
    dt_value.year_is_relative = False
    dt_value.month_is_relative = False
    dt_value.hour_is_relative = False
    dt_value.minute_is_relative = False

    entity = MagicMock()
    entity.type = "YANDEX.DATETIME"
    entity.tokens = MagicMock()
    entity.tokens.start = 5  # "завтра" at index 5
    entity.tokens.end = 6
    entity.value = dt_value
    message.nlu.entities = [entity]

    # Слот task_name содержит "на завтра" из-за greedy .+
    intent_data = {
        "slots": {
            "task_name": {"value": "купить хлеб на завтра"},
            # new_date slot отсутствует — грамматика съела дату в task_name
        }
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(
        message, intent_data, _make_state(), mock_factory, _skip_confirm=True
    )
    # Задача должна быть найдена и обновлена
    assert "обновлена" in response.text
    assert "Купить хлеб" in response.text


async def test_create_task_date_only_uses_user_timezone() -> None:
    """Date-only task uses midnight in user timezone, not UTC."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    message = _make_message()
    message.nlu = MagicMock()
    message.nlu.tokens = ["добавь", "задачу", "купить", "молоко", "на", "завтра"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=4, end=6),
            value=DateTimeEntity(day=1, day_is_relative=True),
        ),
    ]
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Купить молоко"}},
    }
    # Create event_update with Moscow timezone
    event_update = MagicMock()
    event_update.meta.timezone = "Europe/Moscow"

    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory, event_update)
    assert "купить молоко" in response.text.lower()

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    # Date-only: dueDate should be midnight in user timezone (+0300 for Moscow)
    assert call_args.due_date is not None
    assert "+0300" in call_args.due_date
    assert "T00:00:00" in call_args.due_date
    # isAllDay should be True for date-only tasks
    assert call_args.is_all_day is True


async def test_create_task_with_time_uses_user_timezone() -> None:
    """Task with specific time uses user timezone."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    message = _make_message()
    message.nlu = MagicMock()
    message.nlu.tokens = ["добавь", "задачу", "кино", "на", "завтра", "в", "19", "00"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=3, end=8),
            value=DateTimeEntity(day=1, day_is_relative=True, hour=19, minute=0),
        ),
    ]
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "Кино"}},
    }
    event_update = MagicMock()
    event_update.meta.timezone = "Europe/Moscow"

    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory, event_update)
    assert "кино" in response.text.lower()

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    # Time-specific: dueDate should contain 19:XX and Moscow offset
    assert call_args.due_date is not None
    assert "T19:00:" in call_args.due_date
    assert "+0300" in call_args.due_date
    # isAllDay should be False for time-specific tasks
    assert call_args.is_all_day is False


async def test_create_task_grammar_swallows_date_nlu_corrects_name() -> None:
    """Когда .+ поглощает дату в task_name, NLU entities исправляют название и дату."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    message = _make_message(command="создай задачу купить молоко на завтра")
    message.nlu = MagicMock()
    # создай(0) задачу(1) купить(2) молоко(3) на(4) завтра(5)
    message.nlu.tokens = ["создай", "задачу", "купить", "молоко", "на", "завтра"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=4, end=6),
            value=DateTimeEntity(day=1, day_is_relative=True),
        )
    ]
    # Баг грамматики: .+ поглотил "на завтра", слот date отсутствует
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "купить молоко на завтра"}}}

    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)

    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.title == "Купить молоко"
    assert payload.due_date is not None


async def test_create_task_nlu_task_name_is_capitalized() -> None:
    """Название задачи из NLU fallback должно быть с заглавной буквы."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    message = _make_message(command="добавь задачу позвонить маме на завтра")
    message.nlu = MagicMock()
    # добавь(0) задачу(1) позвонить(2) маме(3) на(4) завтра(5)
    message.nlu.tokens = ["добавь", "задачу", "позвонить", "маме", "на", "завтра"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=4, end=6),
            value=DateTimeEntity(day=1, day_is_relative=True),
        )
    ]
    # Баг грамматики: task_name поглотил дату
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "позвонить маме на завтра"}}}

    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)

    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.title == "Позвонить маме"


async def test_create_task_only_date_in_slot_returns_name_required() -> None:
    """Если после NLU-очистки название пустое — возвращать TASK_NAME_REQUIRED."""
    from aliceio.types import DateTimeEntity, Entity, TokensEntity

    message = _make_message(command="создай задачу на завтра")
    message.nlu = MagicMock()
    # создай(0) задачу(1) на(2) завтра(3)
    message.nlu.tokens = ["создай", "задачу", "на", "завтра"]
    message.nlu.entities = [
        Entity(
            type="YANDEX.DATETIME",
            tokens=TokensEntity(start=2, end=4),
            value=DateTimeEntity(day=1, day_is_relative=True),
        )
    ]
    # Баг грамматики: task_name = "на завтра" (только дата, без реального названия)
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "на завтра"}}}

    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert response.text == txt.TASK_NAME_REQUIRED


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
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING
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
    assert "Произошла ошибка при обращении к TickTick" in response.text


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


async def test_delete_other_handles_net_as_reject() -> None:
    """'нет' в состоянии confirm должен отменять удаление даже без YANDEX.REJECT."""
    state = _make_mock_state(
        data={"task_id": "t1", "task_name": "купить хлеб", "project_id": "p1"}
    )
    message = _make_message(command="нет")
    message.nlu = MagicMock()
    message.nlu.tokens = ["нет"]
    response = await on_delete_other(message, state)
    assert response.text == txt.DELETE_CANCELLED
    state.clear.assert_called_once()


async def test_delete_other_handles_da_as_confirm() -> None:
    """'да' в состоянии confirm должен вызвать handle_delete_confirm."""
    state = _make_mock_state(
        data={"task_id": "t1", "task_name": "купить хлеб", "project_id": "proj-1"}
    )
    message = _make_message(command="да")
    message.nlu = MagicMock()
    message.nlu.tokens = ["да"]
    await on_delete_other(message, state)
    # handle_delete_confirm deletes the task; with mocks it will either succeed
    # or raise error that gets caught. Key: state.clear was called (not re-prompted).
    state.clear.assert_called_once()


async def test_delete_other_handles_otmena_as_reject() -> None:
    """'отмена' в состоянии confirm должен отменять удаление."""
    state = _make_mock_state(
        data={"task_id": "t1", "task_name": "купить хлеб", "project_id": "p1"}
    )
    message = _make_message(command="отмена")
    message.nlu = MagicMock()
    message.nlu.tokens = ["отмена"]
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


async def test_search_task_best_match_with_description() -> None:
    """Best match shows description."""
    tasks = [
        Task(
            id="t1",
            title="Купить хлеб",
            projectId="p1",
            content="Зайти в Перекрёсток",
            priority=0,
            status=0,
        ),
        Task(id="t2", title="Купить молоко", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "купить"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Лучшее совпадение" in response.text
    assert "Купить хлеб" in response.text
    assert "Зайти в Перекрёсток" in response.text
    assert "Также найдено" in response.text
    assert "Купить молоко" in response.text


async def test_search_task_best_match_with_checklist() -> None:
    """Best match shows checklist with statuses."""
    tasks = [
        Task(
            id="t1",
            title="Список покупок",
            projectId="p1",
            content="",
            priority=0,
            status=0,
            items=[
                ChecklistItem(id="c1", title="Молоко", status=1),
                ChecklistItem(id="c2", title="Хлеб", status=0),
            ],
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "список покупок"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Список покупок" in response.text
    assert "[x] Молоко" in response.text
    assert "[ ] Хлеб" in response.text


async def test_search_task_single_result_no_also_found() -> None:
    """Single match — no 'Также найдено' section."""
    tasks = [
        Task(id="t1", title="Уникальная задача", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "уникальная задача"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Найдена задача" in response.text
    assert "Также найдено" not in response.text


async def test_search_task_no_description_no_checklist() -> None:
    """Best match without description/checklist skips those sections."""
    tasks = [
        Task(id="t1", title="Простая задача", projectId="p1", priority=0, status=0),
        Task(id="t2", title="Простая работа", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "простая"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Лучшее совпадение" in response.text
    assert "Описание" not in response.text
    assert "Чеклист" not in response.text


async def test_search_task_budget_truncates_checklist() -> None:
    """When checklist is too long, show partial + 'и ещё N'."""
    long_items = [
        ChecklistItem(
            id=f"c{i}",
            title=f"Пункт номер {i} с очень длинным названием для теста",
            status=0,
        )
        for i in range(30)
    ]
    tasks = [
        Task(
            id="t1",
            title="Задача",
            projectId="p1",
            content="Описание " * 20,
            priority=5,
            status=0,
            items=long_items,
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "задача"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert len(response.text) <= 1024
    assert "и ещё" in response.text


async def test_search_task_best_match_with_context() -> None:
    """Best match shows date and priority in context."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [
        Task(
            id="t1",
            title="Важное дело",
            projectId="p1",
            priority=5,
            status=0,
            dueDate=tomorrow,
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "важное дело"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "завтра" in response.text
    assert "высокий приоритет" in response.text


# --- Create task in project ---


async def test_create_task_in_project() -> None:
    """Create a task in a specific project."""
    projects = [
        _make_project(project_id="p-shop", name="Покупки"),
        _make_project(project_id="p-work", name="Работа"),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Купить молоко"},
            "project_name": {"value": "Покупки"},
        },
    }
    mock_factory = _make_mock_client(projects=projects)
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Покупки" in response.text
    assert "Купить молоко" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id == "p-shop"


async def test_create_task_in_project_with_date() -> None:
    """Create a task in a project with a date."""
    projects = [_make_project(project_id="p-shop", name="Покупки")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Купить молоко"},
            "project_name": {"value": "Покупки"},
            "date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(projects=projects)
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Покупки" in response.text
    assert "Купить молоко" in response.text
    assert "завтра" in response.text


async def test_create_task_project_not_found() -> None:
    """When project not found, return list of available projects."""
    projects = [
        _make_project(project_id="p1", name="Покупки"),
        _make_project(project_id="p2", name="Работа"),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Тест"},
            "project_name": {"value": "Несуществующий"},
        },
    }
    mock_factory = _make_mock_client(projects=projects)
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "не найден" in response.text
    assert "Покупки" in response.text
    assert "Работа" in response.text


async def test_create_task_project_fuzzy_match() -> None:
    """Fuzzy matching on project name (e.g., 'покупка' matches 'Покупки')."""
    projects = [_make_project(project_id="p-shop", name="Покупки")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Молоко"},
            "project_name": {"value": "покупка"},
        },
    }
    mock_factory = _make_mock_client(projects=projects)
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Покупки" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id == "p-shop"


# --- Edit task: move to project ---


async def test_edit_task_move_to_project() -> None:
    """Move a task to another project."""
    projects = [
        _make_project(project_id="p1", name="Inbox"),
        _make_project(project_id="p-work", name="Работа"),
    ]
    tasks = [_make_task(title="Подготовить отчёт", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "подготовить отчёт"},
            "new_project": {"value": "Работа"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "перемещена" in response.text
    assert "Работа" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    client.move_task.assert_called_once_with(tasks[0].id, "p1", "p-work")
    client.update_task.assert_not_called()


async def test_edit_task_move_project_not_found() -> None:
    """Moving to a non-existent project shows available projects."""
    projects = [
        _make_project(project_id="p1", name="Покупки"),
        _make_project(project_id="p2", name="Работа"),
    ]
    tasks = [_make_task(title="Тест")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "тест"},
            "new_project": {"value": "Несуществующий"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "не найден" in response.text
    assert "Покупки" in response.text
    assert "Работа" in response.text


async def test_edit_task_move_same_project() -> None:
    """Moving to the same project returns 'already in project' message."""
    projects = [_make_project(project_id="p1", name="Работа")]
    tasks = [_make_task(title="Отчёт", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "Работа"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "уже в проекте" in response.text
    assert "Работа" in response.text


async def test_edit_task_move_and_reschedule() -> None:
    """Move to another project and change date simultaneously."""
    projects = [
        _make_project(project_id="p1", name="Inbox"),
        _make_project(project_id="p-work", name="Работа"),
    ]
    tasks = [_make_task(title="Отчёт", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "Работа"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    # Multiple changes → EDIT_SUCCESS (not TASK_MOVED)
    assert "обновлена" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    # Both move_task and update_task must be called
    client.move_task.assert_called_once_with(tasks[0].id, "p1", "p-work")
    update_args = client.update_task.call_args[0][0]
    assert update_args.project_id == "p-work"
    assert update_args.due_date is not None


async def test_edit_task_move_api_error_returns_move_error() -> None:
    """move_task API failure → MOVE_ERROR, update_task never called."""
    projects = [
        _make_project(project_id="p1", name="Inbox"),
        _make_project(project_id="p-work", name="Работа"),
    ]
    tasks = [_make_task(title="Отчёт", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "Работа"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.move_task = AsyncMock(side_effect=Exception("API error"))

    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)

    assert response.text == txt.MOVE_ERROR
    client.update_task.assert_not_called()


async def test_edit_task_partial_failure_move_ok_update_fails() -> None:
    """move_task succeeds, update_task fails → EDIT_PARTIAL_ERROR with project name."""
    projects = [
        _make_project(project_id="p1", name="Inbox"),
        _make_project(project_id="p-work", name="Работа"),
    ]
    tasks = [_make_task(title="Отчёт", project_id="p1")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "Работа"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.update_task = AsyncMock(side_effect=Exception("timeout"))

    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)

    assert "перемещена" in response.text
    assert "Работа" in response.text
    assert "остальные изменения не применились" in response.text
    client.move_task.assert_called_once()


# --- Intent slot extraction ---


def test_extract_create_task_slots_with_project() -> None:
    """Verify project_name is extracted from create_task intent."""
    from alice_ticktick.dialogs.intents import extract_create_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Купить молоко"},
            "project_name": {"value": "Покупки"},
        },
    }
    slots = extract_create_task_slots(intent_data)
    assert slots.project_name == "Покупки"
    assert slots.task_name == "Купить молоко"


def test_extract_create_task_slots_fixed_rec_freq_fallback() -> None:
    """When rec_freq is None but fixed_rec_freq is set, use fixed_rec_freq."""
    from alice_ticktick.dialogs.intents import extract_create_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "fixed_rec_freq": {"value": "ежедневно"},
        },
    }
    slots = extract_create_task_slots(intent_data)
    assert slots.rec_freq == "ежедневно"


def test_extract_create_task_slots_rec_freq_preferred_over_fixed() -> None:
    """When both rec_freq and fixed_rec_freq are set, prefer rec_freq."""
    from alice_ticktick.dialogs.intents import extract_create_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "уборка"},
            "rec_freq": {"value": "понедельник"},
            "fixed_rec_freq": {"value": "еженедельно"},
        },
    }
    slots = extract_create_task_slots(intent_data)
    assert slots.rec_freq == "понедельник"


def test_extract_create_recurring_task_slots_fixed_rec_freq_fallback() -> None:
    """When rec_freq is None but fixed_rec_freq is set, use fixed_rec_freq."""
    from alice_ticktick.dialogs.intents import extract_create_recurring_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "fixed_rec_freq": {"value": "еженедельно"},
        },
    }
    slots = extract_create_recurring_task_slots(intent_data)
    assert slots.rec_freq == "еженедельно"


def test_extract_edit_task_slots_fixed_rec_freq_fallback() -> None:
    """When rec_freq is None but fixed_rec_freq is set, use fixed_rec_freq."""
    from alice_ticktick.dialogs.intents import extract_edit_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "fixed_rec_freq": {"value": "ежедневно"},
        },
    }
    slots = extract_edit_task_slots(intent_data)
    assert slots.rec_freq == "ежедневно"


def test_extract_edit_task_slots_rec_freq_preferred_over_fixed() -> None:
    """When both rec_freq and fixed_rec_freq are set, rec_freq wins."""
    from alice_ticktick.dialogs.intents import extract_edit_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "rec_freq": {"value": "понедельник"},
            "fixed_rec_freq": {"value": "ежедневно"},
        },
    }
    slots = extract_edit_task_slots(intent_data)
    assert slots.rec_freq == "понедельник"


def test_extract_edit_task_slots_with_project() -> None:
    """Verify new_project is extracted from edit_task intent."""
    from alice_ticktick.dialogs.intents import extract_edit_task_slots

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Отчёт"},
            "new_project": {"value": "Работа"},
        },
    }
    slots = extract_edit_task_slots(intent_data)
    assert slots.new_project == "Работа"
    assert slots.task_name == "Отчёт"


@pytest.mark.asyncio
async def test_router_disambiguate_add_subtask_vs_create_task_in_project() -> None:
    """When both add_subtask and create_task match, prefer create_task if no subtask keyword."""
    from alice_ticktick.dialogs.router import on_add_subtask

    projects = [_make_project(project_id="p-personal", name="Личное")]
    message = _make_message()
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "тест", "в", "проект", "личное"]
    message.nlu.entities = []
    # Both intents match
    message.nlu.intents = {
        "add_subtask": {
            "slots": {
                "subtask_name": {"value": "задачу тест"},
                "parent_name": {"value": "проект личное"},
            },
        },
        "create_task": {
            "slots": {
                "task_name": {"value": "тест"},
                "project_name": {"value": "личное"},
            },
        },
    }
    mock_factory = _make_mock_client(projects=projects)
    event_update = MagicMock()
    event_update.meta.timezone = "UTC"
    from unittest.mock import patch

    with patch("alice_ticktick.dialogs.handlers.tasks.TickTickClient", mock_factory):
        add_subtask_data = message.nlu.intents["add_subtask"]
        response = await on_add_subtask(message, add_subtask_data, event_update)

    # Should NOT say "not found" (add_subtask behavior)
    # Should create the task in project (create_task behavior)
    assert "не найдена" not in response.text


# --- Recurrence and reminder tests ---


async def test_create_daily_recurring() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "rec_freq": {"value": "день"},
        },
    }
    message = _make_message(command="создай задачу зарядка каждый день")
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Зарядка" in response.text
    assert "создана" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=DAILY"


async def test_create_weekly_monday() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "стендап"},
            "rec_freq": {"value": "понедельник"},
        },
    }
    message = _make_message(command="создай задачу стендап каждый понедельник")
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Стендап" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=WEEKLY;BYDAY=MO"


async def test_create_with_interval() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "полив цветов"},
            "rec_freq": {"value": "дня"},
            "rec_interval": {"value": 3},
        },
    }
    message = _make_message(command="создай задачу полив цветов каждые 3 дня")
    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=DAILY;INTERVAL=3"


async def test_create_with_reminder() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        },
    }
    message = _make_message(command="создай задачу встреча с напоминанием за 30 минут")
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Встреча" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.reminders == ["TRIGGER:-PT30M"]


async def test_create_with_recurrence_and_reminder() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "rec_freq": {"value": "день"},
            "reminder_value": {"value": 1},
            "reminder_unit": {"value": "час"},
        },
    }
    message = _make_message(command="создай задачу зарядка каждый день с напоминанием за час")
    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=DAILY"
    assert payload.reminders == ["TRIGGER:-PT1H"]


async def test_create_without_recurrence_no_repeat_flag() -> None:
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "обычная задача"},
        },
    }
    message = _make_message(command="создай задачу обычная задача")
    mock_factory = _make_mock_client()
    await handle_create_task(message, intent_data, mock_factory)
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag is None
    assert payload.reminders is None


# --- create_recurring_task tests ---


async def test_create_recurring_delegates() -> None:
    """create_recurring_task delegates to handle_create_task."""
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "проверить отчёт"},
            "rec_freq": {"value": "понедельник"},
        },
    }
    message = _make_message(command="напоминай каждый понедельник проверить отчёт")
    mock_factory = _make_mock_client()
    response = await handle_create_recurring_task(message, intent_data, mock_factory)
    assert "Проверить отчёт" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=WEEKLY;BYDAY=MO"


async def test_create_recurring_no_auth() -> None:
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "тест"}}}
    message = _make_message(access_token=None)
    response = await handle_create_recurring_task(message, intent_data)
    assert "привязать" in response.text.lower()


async def test_create_recurring_no_name() -> None:
    intent_data: dict[str, Any] = {"slots": {"rec_freq": {"value": "день"}}}
    message = _make_message()
    mock_factory = _make_mock_client()
    response = await handle_create_recurring_task(message, intent_data, mock_factory)
    assert "назвать" in response.text.lower() or "название" in response.text.lower()


async def test_create_task_ejednevno_creates_daily_rrule() -> None:
    """'создай задачу зарядка ежедневно' -> RRULE:FREQ=DAILY."""
    message = _make_message(command="создай задачу зарядка ежедневно")
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "зарядка", "ежедневно"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            # rec_freq НЕ заполнен NLU (баг)
        }
    }
    await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=DAILY"


async def test_create_task_ezhenedelno_creates_weekly_rrule() -> None:
    """'создай задачу уборка еженедельно' -> RRULE:FREQ=WEEKLY."""
    message = _make_message(command="создай задачу уборка еженедельно")
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "уборка", "еженедельно"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "уборка"}}}
    await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=WEEKLY"


async def test_create_recurring_task_ejednevno_creates_daily_rrule() -> None:
    """'напоминай ежедневно делать зарядку' -> RRULE:FREQ=DAILY."""
    message = _make_message(command="напоминай ежедневно делать зарядку")
    message.nlu = MagicMock()
    message.nlu.tokens = ["напоминай", "ежедневно", "делать", "зарядку"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "делать зарядку"},
            # rec_freq НЕ заполнен NLU (баг)
        }
    }
    await handle_create_recurring_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeat_flag == "RRULE:FREQ=DAILY"


# --- add_reminder tests ---


async def test_add_reminder_success() -> None:
    tasks = [_make_task(title="Встреча")]
    mock_factory = _make_mock_client(projects=[], tasks=tasks)
    # Override inbox to return the task (_gather_all_tasks fetches inbox)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=tasks)

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        },
    }
    message = _make_message(command="напомни о задаче встреча за 30 минут")
    response = await handle_add_reminder(message, intent_data, mock_factory)
    assert "напоминание" in response.text.lower()
    assert "30 минут" in response.text


async def test_add_reminder_no_auth() -> None:
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "тест"}}}
    message = _make_message(access_token=None)
    response = await handle_add_reminder(message, intent_data)
    assert "привязать" in response.text.lower()


async def test_add_reminder_no_task_name() -> None:
    intent_data: dict[str, Any] = {
        "slots": {"reminder_value": {"value": 30}, "reminder_unit": {"value": "минут"}},
    }
    message = _make_message()
    mock_factory = _make_mock_client()
    response = await handle_add_reminder(message, intent_data, mock_factory)
    assert response.text == txt.REMINDER_TASK_REQUIRED


async def test_add_reminder_no_value() -> None:
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "встреча"}}}
    message = _make_message()
    mock_factory = _make_mock_client()
    response = await handle_add_reminder(message, intent_data, mock_factory)
    assert response.text == txt.REMINDER_VALUE_REQUIRED


async def test_add_reminder_task_not_found() -> None:
    mock_factory = _make_mock_client(tasks=[])
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=[])

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "несуществующая"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        },
    }
    message = _make_message()
    response = await handle_add_reminder(message, intent_data, mock_factory)
    assert "не найдена" in response.text.lower()


# --- edit_task recurrence/reminder tests ---


async def test_edit_add_recurrence() -> None:
    tasks = [_make_task(title="Зарядка")]
    mock_factory = _make_mock_client(projects=[], tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=tasks)

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "rec_freq": {"value": "день"},
        },
    }
    message = _make_message(command="поменяй повторение задачи зарядка на каждый день")
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "повторение" in response.text.lower() or "обновлена" in response.text.lower()
    call_args = client.update_task.call_args[0][0]
    assert call_args.repeat_flag == "RRULE:FREQ=DAILY"


async def test_edit_recurrence_fallback_no_slots() -> None:
    """When NLU misses recurrence slots (greedy .+ conflict), handler parses from utterance."""
    tasks = [_make_task(title="Зарядка")]
    mock_factory = _make_mock_client(projects=[], tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=tasks)

    # NLU fills only task_name (dirty — line 4 matched instead of line 8)
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "повторение задачи зарядка на каждый день"},
        },
    }
    message = _make_message(command="поменяй повторение задачи зарядка на каждый день")
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "повторение" in response.text.lower() or "обновлена" in response.text.lower()
    call_args = client.update_task.call_args[0][0]
    assert call_args.repeat_flag == "RRULE:FREQ=DAILY"


async def test_edit_recurrence_fallback_weekly() -> None:
    """Fallback parses 'каждую неделю' from utterance when NLU misses slots."""
    tasks = [_make_task(title="Уборка")]
    mock_factory = _make_mock_client(projects=[], tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=tasks)

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "повтор задачи уборка на каждую неделю"},
        },
    }
    message = _make_message(command="измени повтор задачи уборка на каждую неделю")
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "повторение" in response.text.lower() or "обновлена" in response.text.lower()
    call_args = client.update_task.call_args[0][0]
    assert call_args.repeat_flag == "RRULE:FREQ=WEEKLY"


async def test_edit_remove_recurrence() -> None:
    task = _make_task(title="Зарядка")
    task.repeat_flag = "RRULE:FREQ=DAILY"
    mock_factory = _make_mock_client(projects=[], tasks=[task])
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=[task])

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            "remove_recurrence": {"value": "повторение"},
        },
    }
    message = _make_message(command="убери повторение задачи зарядка")
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "убрано" in response.text.lower() or "обновлена" in response.text.lower()
    call_args = client.update_task.call_args[0][0]
    assert call_args.repeat_flag == ""


async def test_edit_add_reminder() -> None:
    tasks = [_make_task(title="Встреча")]
    mock_factory = _make_mock_client(projects=[], tasks=tasks)
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=tasks)

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        },
    }
    message = _make_message(command="поставь напоминание задачи встреча за 30 минут")
    await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    call_args = client.update_task.call_args[0][0]
    assert call_args.reminders == ["TRIGGER:-PT30M"]


async def test_edit_remove_reminder() -> None:
    task = _make_task(title="Встреча")
    task.reminders = ["TRIGGER:-PT30M"]
    mock_factory = _make_mock_client(projects=[], tasks=[task])
    client = mock_factory.return_value.__aenter__.return_value
    client.get_inbox_tasks = AsyncMock(return_value=[task])

    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча"},
            "remove_reminder": {"value": "напоминание"},
        },
    }
    message = _make_message(command="убери напоминание задачи встреча")
    await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    call_args = client.update_task.call_args[0][0]
    assert call_args.reminders == []


# --- _format_priority_label ---


class TestFormatPriorityLabel:
    def test_high(self) -> None:
        assert _format_priority_label(5) == "высокий приоритет"

    def test_medium(self) -> None:
        assert _format_priority_label(3) == "средний приоритет"

    def test_low(self) -> None:
        assert _format_priority_label(1) == "низкий приоритет"

    def test_none(self) -> None:
        assert _format_priority_label(0) == ""


# --- _format_task_context ---


class TestFormatTaskContext:
    def test_with_date_and_priority(self) -> None:
        tz = ZoneInfo("UTC")
        now = datetime.datetime.now(tz=tz)
        tomorrow = now + datetime.timedelta(days=1)
        task = _make_task(title="X", due_date=tomorrow, priority=5)
        result = _format_task_context(task, tz)
        assert "завтра" in result
        assert "высокий приоритет" in result
        assert result.startswith(" (")
        assert result.endswith(")")

    def test_with_date_only(self) -> None:
        tz = ZoneInfo("UTC")
        now = datetime.datetime.now(tz=tz)
        tomorrow = now + datetime.timedelta(days=1)
        task = _make_task(title="X", due_date=tomorrow, priority=0)
        result = _format_task_context(task, tz)
        assert "завтра" in result
        assert "приоритет" not in result

    def test_with_priority_only(self) -> None:
        tz = ZoneInfo("UTC")
        task = _make_task(title="X", priority=3)
        result = _format_task_context(task, tz)
        assert "средний приоритет" in result

    def test_empty(self) -> None:
        tz = ZoneInfo("UTC")
        task = _make_task(title="X", priority=0)
        result = _format_task_context(task, tz)
        assert result == ""


# --- edit_task detailed confirmation tests ---


async def test_edit_task_reschedule_confirms_date() -> None:
    """Edit task with date change confirms the new date."""
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "Купить молоко" in response.text
    assert "дата" in response.text.lower()
    assert "завтра" in response.text


async def test_edit_task_change_priority_confirms() -> None:
    """Edit task with priority change confirms the new priority."""
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "Купить молоко" in response.text
    assert "приоритет" in response.text.lower()
    assert "высокий" in response.text.lower()


async def test_edit_task_multiple_changes_confirms_all() -> None:
    """Edit with date+priority confirms both changes."""
    tasks = [_make_task(title="Отчёт")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "дата" in response.text.lower()
    assert "приоритет" in response.text.lower()


# --- Complete task context ---


async def test_complete_task_confirms_with_context() -> None:
    """Complete task shows date and priority in confirmation."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [_make_task(title="Купить молоко", due_date=tomorrow, priority=1)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, _make_state(), mock_factory)
    assert "Купить молоко" in response.text
    assert "завтра" in response.text
    assert "низкий приоритет" in response.text
    assert "выполненной" in response.text


# --- Delete task context ---


async def test_delete_task_confirm_shows_context() -> None:
    """Delete confirmation shows task date."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [_make_task(title="Старый отчёт", due_date=tomorrow)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "старый отчёт"}},
    }
    state = AsyncMock()
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_delete_task(message, intent_data, state, mock_factory)
    assert "Старый отчёт" in response.text
    assert "завтра" in response.text
    assert "Удалить" in response.text


async def test_delete_confirm_success_shows_context() -> None:
    """Delete confirm success message shows task context."""
    message = _make_message()
    state = _make_mock_state(
        data={
            "task_id": "t1",
            "project_id": "p1",
            "task_name": "Купить молоко",
            "task_context": " (завтра, низкий приоритет)",
        }
    )
    mock_factory = _make_mock_client()
    response = await handle_delete_confirm(message, state, mock_factory)
    assert "удалена" in response.text
    assert "Купить молоко" in response.text
    assert "завтра" in response.text
    assert "низкий приоритет" in response.text


# --- edit_task: rename and priority removal ---


async def test_edit_task_rename_confirms_new_title() -> None:
    """Edit task with name change confirms the new title."""
    tasks = [_make_task(title="Старое название")]
    message = _make_message(command="переименуй задачу старое название в новое название")
    message.nlu = MagicMock()
    message.nlu.tokens = ["переименуй", "задачу", "старое", "название", "в", "новое", "название"]
    message.nlu.entities = []
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "старое название"},
            "new_name": {"value": "Новое название"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text
    assert "название" in response.text.lower()
    assert "Новое название" in response.text


async def test_edit_task_rename_capitalizes_first_letter() -> None:
    """Rename should capitalize the first letter of the new name."""
    tasks = [_make_task(title="Старое название")]
    message = _make_message(command="переименуй задачу старое название в новое название")
    message.nlu = MagicMock()
    message.nlu.tokens = ["переименуй", "задачу", "старое", "название", "в", "новое", "название"]
    message.nlu.entities = []
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "старое название"},
            "new_name": {"value": "новое название"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text
    assert "Новое название" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    payload = client.update_task.call_args[0][0]
    assert payload.title == "Новое название"


async def test_edit_task_remove_priority_confirms() -> None:
    """Edit task with priority set to none shows 'приоритет убран'."""
    tasks = [_make_task(title="Купить молоко", priority=5)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_priority": {"value": "без приоритета"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text
    assert "приоритет убран" in response.text


async def test_edit_task_weekday_strips_from_task_name() -> None:
    """When weekday date is parsed, the weekday suffix should be stripped from task_name."""
    tasks = [_make_task(title="Кктест редактирования")]
    message = _make_message(
        command="перенеси задачу кктест редактирования на понедельник",
    )
    intent_data: dict[str, Any] = {
        "slots": {
            # NLU greedy .+ swallows weekday into task_name
            "task_name": {"value": "кктест редактирования на понедельник"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "обновлена" in response.text


# --- _format_priority_short ---


class TestFormatPriorityShort:
    def test_high(self) -> None:
        assert _format_priority_short(5) == "высокий"

    def test_medium(self) -> None:
        assert _format_priority_short(3) == "средний"

    def test_low(self) -> None:
        assert _format_priority_short(1) == "низкий"

    def test_none(self) -> None:
        assert _format_priority_short(0) == ""


# --- Search: description truncation ---


async def test_search_task_description_truncated_when_too_long() -> None:
    """Very long description is truncated with ellipsis."""
    long_desc = "А" * 2000
    tasks = [
        Task(
            id="t1",
            title="Задача",
            projectId="p1",
            content=long_desc,
            priority=0,
            status=0,
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "задача"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert len(response.text) <= 1024
    assert "Описание:" in response.text
    assert response.text.rstrip().endswith("…")


# --- Cache isolation tests (L-10/C-6) ---


async def test_task_cache_isolated_between_tokens() -> None:
    """Tasks cached for one user must not leak to another user."""
    from alice_ticktick.dialogs.handlers import _reset_project_cache

    _reset_project_cache()

    today = datetime.datetime.now(tz=datetime.UTC)
    task_user_a = _make_task(task_id="a1", title="User A task", due_date=today)
    task_user_b = _make_task(task_id="b1", title="User B task", due_date=today)

    factory_a = _make_mock_client(tasks=[task_user_a])
    factory_b = _make_mock_client(tasks=[task_user_b])

    # User A lists tasks (populates cache for token "token-a")
    msg_a = _make_message(access_token="token-a")
    intent_data: dict[str, Any] = {"slots": {}}
    response_a = await handle_list_tasks(msg_a, intent_data, factory_a)
    assert "User A task" in response_a.text

    # User B lists tasks (should use its own cache for token "token-b")
    msg_b = _make_message(access_token="token-b")
    response_b = await handle_list_tasks(msg_b, intent_data, factory_b)
    assert "User B task" in response_b.text
    assert "User A task" not in response_b.text


async def test_timezone_warning_when_no_timezone(caplog: pytest.LogCaptureFixture) -> None:
    """Warning is logged when request has no timezone."""
    import logging

    from alice_ticktick.dialogs.handlers import _get_user_tz

    with caplog.at_level(logging.WARNING):
        tz = _get_user_tz(None)

    assert str(tz) == "Europe/Moscow"
    assert "No timezone in request, falling back to Europe/Moscow" in caplog.text


async def test_no_timezone_warning_when_timezone_present(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No warning when timezone is present in request."""
    import logging

    from alice_ticktick.dialogs.handlers import _get_user_tz

    mock_update = MagicMock()
    mock_update.meta.timezone = "Europe/Moscow"

    with caplog.at_level(logging.WARNING):
        tz = _get_user_tz(mock_update)

    assert str(tz) == "Europe/Moscow"
    assert "No timezone" not in caplog.text


async def test_list_tasks_passes_timezone_to_parse_yandex_datetime() -> None:
    """handle_list_tasks passes user timezone to parse_yandex_datetime for single-day path."""
    # Task due on March 2 UTC 00:30 — in Europe/Moscow it's still March 2
    due = datetime.datetime(2026, 3, 2, 0, 30, tzinfo=datetime.UTC)
    task = _make_task(task_id="t1", title="TZ Test Task", due_date=due)
    factory = _make_mock_client(tasks=[task])

    message = _make_message()
    # Ask for "tomorrow" (relative day +1) — with MSK timezone where "now" is
    # March 2 at 03:00, "tomorrow" should be March 3
    intent_data: dict[str, Any] = {
        "slots": {
            "date": {
                "value": {
                    "day": 2,
                    "day_is_relative": False,
                    "month": 3,
                    "month_is_relative": False,
                    "year": 2026,
                    "year_is_relative": False,
                },
            },
        },
    }

    mock_update = MagicMock()
    mock_update.meta.timezone = "Europe/Moscow"

    response = await handle_list_tasks(message, intent_data, factory, event_update=mock_update)
    # Task due 2026-03-02 00:30 UTC = 2026-03-02 03:30 MSK — should match March 2
    assert "TZ Test Task" in response.text


# --- format_priority_instrumental tests ---


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ("высокий приоритет", "высоким приоритетом"),
        ("средний приоритет", "средним приоритетом"),
        ("низкий приоритет", "низким приоритетом"),
        ("срочный приоритет", "срочным приоритетом"),
        ("unknown", "unknown"),
        ("", ""),
    ],
)
def test_format_priority_instrumental(input_val: str, expected: str) -> None:
    assert txt.format_priority_instrumental(input_val) == expected


# --- TickTickUnauthorizedError handling (C-5) ---


async def test_create_task_unauthorized_returns_auth_required() -> None:
    """TickTickUnauthorizedError in create_task returns AUTH_REQUIRED."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"type": "YANDEX.STRING", "value": "купить молоко"}}
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=TickTickUnauthorizedError(401, "Unauthorized"),
    )
    response = await handle_create_task(message, intent_data, mock_factory)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_list_tasks_unauthorized_returns_auth_required() -> None:
    """TickTickUnauthorizedError in list_tasks returns AUTH_REQUIRED."""
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=TickTickUnauthorizedError(401, "Unauthorized"),
    )
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_complete_task_unauthorized_returns_auth_required() -> None:
    """TickTickUnauthorizedError in complete_task returns AUTH_REQUIRED."""
    message = _make_message()
    state = _make_state()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"type": "YANDEX.STRING", "value": "купить молоко"}}
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=TickTickUnauthorizedError(401, "Unauthorized"),
    )
    response = await handle_complete_task(message, intent_data, state, mock_factory)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING


async def test_complete_task_generic_exception_returns_api_error() -> None:
    """Generic Exception in complete_task returns COMPLETE_ERROR."""
    message = _make_message()
    state = _make_state()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"type": "YANDEX.STRING", "value": "купить молоко"}}
    }
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=Exception("API error"),
    )
    response = await handle_complete_task(message, intent_data, state, mock_factory)
    assert response.text == txt.COMPLETE_ERROR


async def test_unauthorized_with_account_linking_returns_linking_response() -> None:
    """TickTickUnauthorizedError with account_linking returns AUTH_REQUIRED_LINKING."""
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {}}

    mock_update = MagicMock()
    mock_update.meta.interfaces.account_linking = {}
    mock_update.meta.timezone = "UTC"

    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=TickTickUnauthorizedError(401, "Unauthorized"),
    )
    response = await handle_list_tasks(
        message, intent_data, mock_factory, event_update=mock_update
    )
    assert response.text == txt.AUTH_REQUIRED_LINKING
    assert response.directives is not None


async def test_delete_confirm_unauthorized_clears_state() -> None:
    """TickTickUnauthorizedError in delete_confirm clears FSM state."""
    message = _make_message()
    state = _make_state(
        {"task_id": "t1", "project_id": "p1", "task_name": "test", "task_context": ""}
    )
    mock_factory = _make_mock_client()
    mock_factory.return_value.__aenter__ = AsyncMock(
        side_effect=TickTickUnauthorizedError(401, "Unauthorized"),
    )
    response = await handle_delete_confirm(message, state, ticktick_client_factory=mock_factory)
    assert response.text == txt.AUTH_REQUIRED_NO_LINKING
    state.clear.assert_awaited()


async def test_get_user_tz_fallback_is_moscow() -> None:
    """When no timezone in request, default must be Europe/Moscow, not UTC."""
    from zoneinfo import ZoneInfo

    from alice_ticktick.dialogs.handlers._helpers import _get_user_tz

    tz = _get_user_tz(None)
    assert tz == ZoneInfo("Europe/Moscow")


async def test_complete_task_redirects_to_check_item_on_checklist_command() -> None:
    """on_complete_task must redirect to handle_check_item for checklist command."""
    from unittest.mock import patch

    from aliceio.types import Response as AliceResponse

    from alice_ticktick.dialogs.router import on_complete_task

    message = _make_message(command="отметь пункт молоко в чеклисте задачи покупки")
    message.nlu = MagicMock()
    message.nlu.tokens = ["отметь", "пункт", "молоко", "в", "чеклисте", "задачи", "покупки"]
    message.nlu.intents = {}

    intent_data: dict[str, Any] = {"slots": {}}

    with patch(
        "alice_ticktick.dialogs.router.handle_check_item", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = AliceResponse(text="Пункт молоко отмечен в задаче Покупки")
        response = await on_complete_task(message, intent_data, _make_state(), MagicMock())

    mock_check.assert_called_once()
    assert "молоко" in response.text.lower() or "отмечен" in response.text.lower()


async def test_delete_task_redirects_to_delete_checklist_item_on_checklist_command() -> None:
    """on_delete_task must redirect to handle_delete_checklist_item.

    For command: 'удали пункт X из чеклиста задачи Y'.
    """
    from unittest.mock import patch

    from aliceio.types import Response as AliceResponse

    from alice_ticktick.dialogs.router import on_delete_task

    message = _make_message(command="удали пункт молоко из чеклиста задачи покупки")
    message.nlu = MagicMock()
    message.nlu.tokens = ["удали", "пункт", "молоко", "из", "чеклиста", "задачи", "покупки"]
    message.nlu.intents = {}

    intent_data: dict[str, Any] = {"slots": {}}

    with patch(
        "alice_ticktick.dialogs.router.handle_delete_checklist_item", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = AliceResponse(text="Пункт молоко удалён из задачи Покупки")
        response = await on_delete_task(message, intent_data, _make_state(), MagicMock())

    mock_delete.assert_called_once()
    assert "молоко" in response.text.lower() or "удалён" in response.text.lower()


def test_router_overdue_registered_before_list_tasks() -> None:
    """Verify router source code registers OVERDUE_TASKS before LIST_TASKS."""
    from pathlib import Path

    router_path = Path(__file__).parent.parent / "alice_ticktick" / "dialogs" / "router.py"
    source = router_path.read_text()
    overdue_pos = source.find("IntentFilter(OVERDUE_TASKS)")
    list_tasks_pos = source.find("IntentFilter(LIST_TASKS)")

    assert overdue_pos != -1, "OVERDUE_TASKS not found in router"
    assert list_tasks_pos != -1, "LIST_TASKS not found in router"
    assert overdue_pos < list_tasks_pos, "OVERDUE_TASKS must appear before LIST_TASKS in router.py"


# --- on_unknown fallback tests ---


async def test_unknown_handler_catches_goodbye_in_text_mode() -> None:
    """on_unknown should detect goodbye keywords and return goodbye response."""
    from alice_ticktick.dialogs.router import on_unknown

    for phrase in ["до свидания", "пока", "до встречи"]:
        message = _make_message(command=phrase)
        message.nlu = MagicMock()
        message.nlu.tokens = phrase.split()
        message.nlu.intents = {}
        response = await on_unknown(message)
        assert response.text == txt.GOODBYE, f"Failed for '{phrase}': {response.text}"
        assert response.end_session is True


async def test_unknown_handler_still_returns_unknown_for_normal_input() -> None:
    """on_unknown should still return UNKNOWN for non-goodbye phrases."""
    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="абракадабра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["абракадабра"]
    message.nlu.intents = {}
    response = await on_unknown(message)
    assert response.text == txt.UNKNOWN


# --- on_list_tasks redirect to show_checklist ---


async def test_list_tasks_redirects_to_show_checklist() -> None:
    """on_list_tasks should redirect to show_checklist when 'чеклист' in utterance."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_list_tasks

    message = _make_message(command="покажи чеклист задачи купить хлеб")
    message.nlu = MagicMock()
    message.nlu.tokens = ["покажи", "чеклист", "задачи", "купить", "хлеб"]
    message.nlu.intents = {"list_tasks": {"slots": {"priority": {"value": "чеклист"}}}}
    message.nlu.entities = []

    intent_data: dict[str, Any] = {"slots": {"priority": {"value": "чеклист"}}}
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    with patch(
        "alice_ticktick.dialogs.router.handle_show_checklist",
        new_callable=AsyncMock,
        return_value=MagicMock(text="Чеклист"),
    ) as mock_handler:
        await on_list_tasks(message, intent_data, event_update)
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        fake_intent = call_args[1]
        assert fake_intent["slots"]["task_name"]["value"] == "купить хлеб"


async def test_list_tasks_not_redirected_when_no_checklist_keyword() -> None:
    """on_list_tasks should NOT redirect for normal list queries."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_list_tasks

    message = _make_message(command="покажи задачи на сегодня")
    message.nlu = MagicMock()
    message.nlu.tokens = ["покажи", "задачи", "на", "сегодня"]
    message.nlu.intents = {"list_tasks": {"slots": {}}}
    message.nlu.entities = []

    intent_data: dict[str, Any] = {"slots": {}}
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    with patch(
        "alice_ticktick.dialogs.router.handle_list_tasks",
        new_callable=AsyncMock,
        return_value=MagicMock(text="На сегодня"),
    ) as mock_handler:
        await on_list_tasks(message, intent_data, event_update)
        mock_handler.assert_called_once()


# --- _infer_rec_freq_from_tokens tests ---

from alice_ticktick.dialogs.handlers._helpers import (  # noqa: E402
    _infer_rec_freq_from_tokens,
    _try_parse_weekday,
)


def test_infer_rec_freq_detects_kazhdy_den() -> None:
    """_infer_rec_freq should detect 'каждый день' in tokens."""
    tokens = ["напоминай", "каждый", "день", "пить", "воду"]
    result = _infer_rec_freq_from_tokens(None, tokens)
    assert result == "день"


def test_infer_rec_freq_detects_kazhduyu_nedelyu() -> None:
    """_infer_rec_freq should detect 'каждую неделю' in tokens."""
    tokens = ["напоминай", "каждую", "неделю", "проверить"]
    result = _infer_rec_freq_from_tokens(None, tokens)
    assert result == "неделю"


def test_infer_rec_freq_preserves_existing() -> None:
    """Should not override existing rec_freq."""
    tokens = ["каждый", "день"]
    result = _infer_rec_freq_from_tokens("понедельник", tokens)
    assert result == "понедельник"


# --- create_task project extraction from utterance ---


async def test_create_task_extracts_project_from_utterance() -> None:
    """When NLU .+ consumes 'в проекте X', handler should extract it from utterance."""
    task = _make_task(task_id="t1", title="Ревью кода", project_id="proj-inbox")
    project = Project(id="proj-inbox", name="Inbox")
    client = _make_mock_client(tasks=[task], projects=[project])

    message = _make_message(command="создай задачу кктест ревью кода в проекте Inbox")
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "кктест", "ревью", "кода", "в", "проекте", "inbox"]
    message.nlu.intents = {}
    message.nlu.entities = []

    # NLU didn't extract project_name — .+ consumed it into task_name
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "кктест ревью кода в проекте Inbox"},
        }
    }
    event_update = MagicMock()
    event_update.meta.timezone = "Europe/Moscow"
    event_update.meta.interfaces.account_linking = None

    response = await handle_create_task(message, intent_data, client, event_update=event_update)
    assert "Готово" in response.text
    # Verify project was extracted: task name in guillemets should not include "в проекте X"
    assert "«кктест ревью кода»" in response.text.lower()


# --- on_unknown search fallback ---


async def test_unknown_handler_catches_search_keywords() -> None:
    """on_unknown should detect 'поиск' and redirect to search."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поиск задачи молоко")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поиск", "задачи", "молоко"]
    message.nlu.intents = {}

    with patch(
        "alice_ticktick.dialogs.router.handle_search_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="Найдено"),
    ) as mock_handler:
        await on_unknown(message)
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        fake_intent = call_args[1]
        assert fake_intent["slots"]["query"]["value"] == "молоко"


# --- on_unknown edit_task fallback ---


async def test_unknown_catches_edit_date() -> None:
    """on_unknown detects 'перенеси задачу X на завтра' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="перенеси задачу тестовую на завтра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перенеси", "задачу", "тестовую", "на", "завтра"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()


async def test_unknown_catches_edit_priority() -> None:
    """on_unknown detects 'поменяй приоритет задачи X на высокий' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поменяй приоритет задачи тестовой на высокий")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поменяй", "приоритет", "задачи", "тестовой", "на", "высокий"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()
        intent_data = mock_handler.call_args[0][1]
        assert intent_data["slots"]["task_name"]["value"] == "тестовой"
        assert intent_data["slots"]["new_priority"]["value"] == "высокий"


async def test_unknown_catches_rename() -> None:
    """on_unknown detects 'переименуй задачу X в Y' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="переименуй задачу старое имя в новое имя")
    message.nlu = MagicMock()
    message.nlu.tokens = ["переименуй", "задачу", "старое", "имя", "в", "новое", "имя"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["new_name"]["value"] == "новое имя"


async def test_unknown_catches_move_project() -> None:
    """on_unknown detects 'перемести задачу X в проект Y' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="перемести задачу тестовую в проект Inbox")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перемести", "задачу", "тестовую", "в", "проект", "inbox"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="перемещена"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["new_project"]["value"] == "Inbox"


async def test_unknown_catches_remove_recurrence() -> None:
    """on_unknown detects 'убери повторение задачи X' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="убери повторение задачи тестовой")
    message.nlu = MagicMock()
    message.nlu.tokens = ["убери", "повторение", "задачи", "тестовой"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="убрано"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["remove_recurrence"]["value"] is True


async def test_unknown_catches_change_reminder() -> None:
    """on_unknown detects 'поменяй напоминание задачи X за 30 минут' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поменяй напоминание задачи тестовой за 30 минут")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поменяй", "напоминание", "задачи", "тестовой", "за", "30", "минут"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="изменено"),
    ) as mock_handler:
        state = MagicMock()
        event_update = MagicMock()
        await on_unknown(message, state=state, event_update=event_update)
        mock_handler.assert_called_once()


def test_try_parse_edit_command_returns_none_for_unrelated() -> None:
    """_try_parse_edit_command returns None for text that has no edit pattern."""
    from alice_ticktick.dialogs.router import _try_parse_edit_command

    assert _try_parse_edit_command("привет как дела") is None
    assert _try_parse_edit_command("") is None
    assert _try_parse_edit_command("добавь задачу купить молоко") is None


# --- Inbox shortcut in create_task ---


async def test_create_task_inbox_shortcut_skips_project_resolution() -> None:
    """project_name='inbox' should skip project resolution and create with project_id=None."""
    message = _make_message()
    message.nlu = None
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Тест инбокса"},
            "project_name": {"value": "inbox"},
        },
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Готово" in response.text
    assert "Тест инбокса" in response.text
    # Inbox shortcut: project_id must be None (=Inbox in TickTick)
    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id is None
    # get_projects should NOT be called for Inbox shortcut
    client.get_projects.assert_not_called()


async def test_create_task_inbox_shortcut_russian_vhodyaschie() -> None:
    """project_name='входящие' should also use Inbox shortcut."""
    message = _make_message()
    message.nlu = None
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Тест"},
            "project_name": {"value": "входящие"},
        },
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Готово" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id is None
    client.get_projects.assert_not_called()


async def test_create_task_inbox_shortcut_russian_inboks() -> None:
    """project_name='инбокс' should also use Inbox shortcut."""
    message = _make_message()
    message.nlu = None
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Тест"},
            "project_name": {"value": "инбокс"},
        },
    }
    mock_factory = _make_mock_client()
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Готово" in response.text
    client = mock_factory.return_value.__aenter__.return_value
    call_args = client.create_task.call_args[0][0]
    assert call_args.project_id is None
    client.get_projects.assert_not_called()


# --- Inbox shortcut in edit_task (move to Inbox) ---


async def test_edit_task_move_to_inbox() -> None:
    """Moving a task from a project to Inbox should call move_task with Inbox project ID."""
    projects = [_make_project(project_id="p-work", name="Работа")]
    tasks = [_make_task(title="Отчёт", project_id="p-work")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "inbox"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "перемещена" in response.text
    assert "Inbox" in response.text

    client = mock_factory.return_value.__aenter__.return_value
    client.move_task.assert_called_once_with(tasks[0].id, "p-work", "inbox")


async def test_edit_task_move_to_inbox_already_in_inbox() -> None:
    """Moving a task already in Inbox to Inbox should say 'already there'."""
    projects = [_make_project(project_id="p1", name="Работа")]
    tasks = [_make_task(title="Отчёт", project_id="inbox")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_project": {"value": "входящие"},
        },
    }
    mock_factory = _make_mock_client(projects=projects, tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    assert "уже в проекте" in response.text
    assert "Inbox" in response.text


# --- First-word extraction in _infer_rec_freq_from_tokens ---


def test_infer_rec_freq_multiword_extracts_first_word() -> None:
    """Multi-word NLU value 'день пить воду' → returns 'день'."""
    result = _infer_rec_freq_from_tokens("день пить воду", None)
    assert result == "день"


def test_infer_rec_freq_recognized_full_value() -> None:
    """Recognized full value 'ежедневно' → returns as-is."""
    result = _infer_rec_freq_from_tokens("ежедневно", None)
    assert result == "ежедневно"


def test_infer_rec_freq_unrecognized_value_passthrough() -> None:
    """Unrecognized value → returns original for build_rrule to handle."""
    result = _infer_rec_freq_from_tokens("кварталу", None)
    assert result == "кварталу"


# --- _try_parse_weekday ---


class TestTryParseWeekday:
    """Tests for _try_parse_weekday helper."""

    TZ = ZoneInfo("Europe/Moscow")

    def test_monday(self) -> None:
        result = _try_parse_weekday("перенеси на понедельник", self.TZ)
        assert result is not None
        assert result.weekday() == 0  # Monday

    def test_friday(self) -> None:
        result = _try_parse_weekday("что на пятницу", self.TZ)
        assert result is not None
        assert result.weekday() == 4  # Friday

    def test_wednesday_accusative(self) -> None:
        result = _try_parse_weekday("перенеси на среду", self.TZ)
        assert result is not None
        assert result.weekday() == 2  # Wednesday

    def test_no_weekday(self) -> None:
        result = _try_parse_weekday("перенеси на завтра", self.TZ)
        assert result is None

    def test_empty_string(self) -> None:
        result = _try_parse_weekday("", self.TZ)
        assert result is None

    def test_result_is_in_future(self) -> None:
        today = datetime.datetime.now(tz=self.TZ).date()
        result = _try_parse_weekday("на понедельник", self.TZ)
        assert result is not None
        assert result > today
