"""Tests for fuzzy match confirmation, _find_active_task helper, and stopword checks."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aliceio.types import Response

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _find_active_task,
    _is_only_stopwords,
    _reset_project_cache,
    _TaskMatch,
    handle_complete_confirm,
    handle_complete_reject,
    handle_complete_task,
    handle_delete_task,
    handle_edit_reject,
    handle_edit_task,
)
from alice_ticktick.ticktick.models import Project, Task


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _reset_project_cache()


def _make_message(
    *,
    access_token: str | None = "test-token",
    command: str = "",
) -> MagicMock:
    message = MagicMock()
    message.command = command
    message.original_utterance = command
    message.session.new = False
    message.session.session_id = "test-session-id"
    message.session.skill_id = "test-skill-id"
    if access_token is not None:
        message.user = MagicMock()
        message.user.access_token = access_token
    else:
        message.user = None
    message.nlu = None
    return message


def _make_task(
    *,
    task_id: str = "task-1",
    title: str = "Test task",
    project_id: str = "proj-1",
    priority: int = 0,
    status: int = 0,
) -> Task:
    return Task(
        id=task_id,
        title=title,
        projectId=project_id,
        priority=priority,
        status=status,
    )


def _make_mock_client(
    projects: list[Project] | None = None,
    tasks: list[Task] | None = None,
) -> type:
    if projects is None:
        projects = [Project(id="proj-1", name="Inbox")]
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


def _make_state(data: dict[str, Any] | None = None) -> AsyncMock:
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


# --- _is_only_stopwords ---


class TestIsOnlyStopwords:
    def test_empty_string(self) -> None:
        assert _is_only_stopwords("") is True

    def test_single_stopword(self) -> None:
        assert _is_only_stopwords("задачу") is True

    def test_multiple_stopwords(self) -> None:
        assert _is_only_stopwords("задачу напоминание") is True

    def test_normal_name(self) -> None:
        assert _is_only_stopwords("купить молоко") is False

    def test_mixed(self) -> None:
        assert _is_only_stopwords("задачу купить") is False


# --- _find_active_task ---


class TestFindActiveTask:
    async def test_task_found(self) -> None:
        tasks = [_make_task(title="Купить молоко")]
        mock_factory = _make_mock_client(tasks=tasks)
        client = await mock_factory().__aenter__()
        result = await _find_active_task(client, "купить молоко")
        assert isinstance(result, _TaskMatch)
        assert result.task.title == "Купить молоко"
        assert result.score > 85

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Купить молоко")]
        mock_factory = _make_mock_client(tasks=tasks)
        client = await mock_factory().__aenter__()
        result = await _find_active_task(client, "совершенно другое")
        assert isinstance(result, Response)
        assert "не найдена" in result.text

    async def test_no_active_tasks(self) -> None:
        mock_factory = _make_mock_client(tasks=[])
        client = await mock_factory().__aenter__()
        result = await _find_active_task(client, "что угодно")
        assert isinstance(result, Response)
        assert "не найдена" in result.text

    async def test_returns_score(self) -> None:
        tasks = [_make_task(title="Купить молоко")]
        mock_factory = _make_mock_client(tasks=tasks)
        client = await mock_factory().__aenter__()
        result = await _find_active_task(client, "купить молоко")
        assert isinstance(result, _TaskMatch)
        assert result.score >= 60


# --- complete_task confirmation ---


class TestCompleteTaskConfirmation:
    async def test_high_score_no_confirmation(self) -> None:
        """Exact match (score >= 85) — complete immediately."""
        tasks = [_make_task(title="Купить молоко")]
        mock_factory = _make_mock_client(tasks=tasks)
        state = _make_state()
        message = _make_message()
        intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "купить молоко"}}}
        response = await handle_complete_task(message, intent_data, state, mock_factory)
        assert "выполненной" in response.text
        state.set_state.assert_not_called()

    async def test_low_score_asks_confirmation(self) -> None:
        """Partial match (score 60-85) — ask for confirmation."""
        tasks = [_make_task(title="Купить молоко и хлеб")]
        mock_factory = _make_mock_client(tasks=tasks)
        state = _make_state()
        message = _make_message()
        # "купить молоко" vs "Купить молоко и хлеб" → score ~79 < 85
        intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "купить молоко"}}}
        response = await handle_complete_task(message, intent_data, state, mock_factory)
        assert "Завершить задачу" in response.text
        state.set_state.assert_called_once()

    async def test_confirm_completes_task(self) -> None:
        """After confirmation, task is completed."""
        state = _make_state(
            {
                "task_id": "task-1",
                "project_id": "proj-1",
                "task_name": "Купить молоко",
                "task_context": "",
            }
        )
        mock_factory = _make_mock_client()
        message = _make_message()
        response = await handle_complete_confirm(message, state, mock_factory)
        assert "выполненной" in response.text

    async def test_reject_cancels(self) -> None:
        """Rejection cancels the flow."""
        state = _make_state(
            {
                "task_id": "task-1",
                "project_id": "proj-1",
                "task_name": "Купить молоко",
            }
        )
        message = _make_message()
        response = await handle_complete_reject(message, state)
        assert response.text == txt.COMPLETE_CANCELLED

    async def test_stopword_returns_required(self) -> None:
        """Task name that is only stopwords returns REQUIRED."""
        message = _make_message()
        intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задачу"}}}
        state = _make_state()
        response = await handle_complete_task(message, intent_data, state)
        assert response.text == txt.COMPLETE_NAME_REQUIRED


# --- edit_task confirmation ---


class TestEditTaskConfirmation:
    async def test_high_score_no_confirmation(self) -> None:
        """Exact match → edit immediately."""
        tasks = [_make_task(title="Купить молоко")]
        mock_factory = _make_mock_client(tasks=tasks)
        state = _make_state()
        message = _make_message()
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "купить молоко"},
                "new_priority": {"value": "высокий"},
            },
        }
        response = await handle_edit_task(message, intent_data, state, mock_factory)
        assert "обновлена" in response.text
        state.set_state.assert_not_called()

    async def test_low_score_asks_confirmation(self) -> None:
        """Partial match (score 60-85) → ask for confirmation."""
        tasks = [_make_task(title="Купить молоко и хлеб")]
        mock_factory = _make_mock_client(tasks=tasks)
        state = _make_state()
        message = _make_message()
        # "купить молоко" vs "Купить молоко и хлеб" → score ~79 < 85
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "купить молоко"},
                "new_priority": {"value": "высокий"},
            },
        }
        response = await handle_edit_task(message, intent_data, state, mock_factory)
        assert "Изменить задачу" in response.text
        state.set_state.assert_called_once()

    async def test_reject_cancels(self) -> None:
        """Rejection cancels the edit flow."""
        state = _make_state()
        message = _make_message()
        response = await handle_edit_reject(message, state)
        assert response.text == txt.EDIT_CANCELLED

    async def test_stopword_returns_required(self) -> None:
        """Task name that is only stopwords returns REQUIRED."""
        message = _make_message()
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "задачу"},
                "new_priority": {"value": "высокий"},
            },
        }
        state = _make_state()
        response = await handle_edit_task(message, intent_data, state)
        assert response.text == txt.EDIT_NAME_REQUIRED


# --- delete/complete/edit stopword checks ---


class TestStopwordChecks:
    async def test_complete_empty_name(self) -> None:
        message = _make_message()
        intent_data: dict[str, Any] = {"slots": {"task_name": {"value": ""}}}
        state = _make_state()
        response = await handle_complete_task(message, intent_data, state)
        assert response.text == txt.COMPLETE_NAME_REQUIRED

    async def test_delete_stopword_name(self) -> None:
        message = _make_message()
        intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задачу"}}}
        state = _make_state()
        response = await handle_delete_task(message, intent_data, state)
        assert response.text == txt.DELETE_NAME_REQUIRED

    async def test_edit_multiple_stopwords(self) -> None:
        message = _make_message()
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "задачу напоминание"},
                "new_priority": {"value": "высокий"},
            },
        }
        state = _make_state()
        response = await handle_edit_task(message, intent_data, state)
        assert response.text == txt.EDIT_NAME_REQUIRED
