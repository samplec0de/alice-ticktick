"""Tests for project management handlers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _reset_project_cache,
    handle_list_projects,
    handle_project_tasks,
)
from alice_ticktick.ticktick.models import Project, Task


@pytest.fixture(autouse=True)
def _clear_project_cache() -> None:
    _reset_project_cache()


def _make_message(*, access_token: str | None = "test-token") -> MagicMock:
    message = MagicMock()
    message.command = ""
    message.session.new = False
    if access_token is not None:
        message.user = MagicMock()
        message.user.access_token = access_token
    else:
        message.user = None
    message.nlu = None
    return message


def _make_project(*, project_id: str = "proj-1", name: str = "Inbox") -> Project:
    return Project(id=project_id, name=name)


def _make_mock_client(projects: list[Project] | None = None, tasks: list[Any] | None = None) -> type:
    if projects is None:
        projects = [_make_project()]
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(return_value=tasks or [])
    client.get_inbox_tasks = AsyncMock(return_value=[])
    client.create_project = AsyncMock(return_value=_make_project())
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


# --- handle_list_projects ---


async def test_list_projects_no_auth() -> None:
    message = _make_message(access_token=None)
    response = await handle_list_projects(message, ticktick_client_factory=_make_mock_client())
    assert txt.AUTH_REQUIRED_NO_LINKING in response.text


async def test_list_projects_success() -> None:
    projects = [
        _make_project(project_id="p1", name="Работа"),
        _make_project(project_id="p2", name="Дом"),
        _make_project(project_id="p3", name="Покупки"),
    ]
    message = _make_message()
    response = await handle_list_projects(
        message, ticktick_client_factory=_make_mock_client(projects=projects)
    )
    assert "Работа" in response.text
    assert "Дом" in response.text
    assert "Покупки" in response.text


async def test_list_projects_empty() -> None:
    message = _make_message()
    response = await handle_list_projects(
        message, ticktick_client_factory=_make_mock_client(projects=[])
    )
    assert response.text == txt.NO_PROJECTS


async def test_list_projects_api_error() -> None:
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.get_projects = AsyncMock(
        side_effect=Exception("API error")
    )
    message = _make_message()
    response = await handle_list_projects(message, ticktick_client_factory=factory)
    assert response.text == txt.API_ERROR


def _make_task(
    *, task_id: str = "t1", title: str = "Test", project_id: str = "p1",
    priority: int = 0, status: int = 0, due_date: Any = None,
) -> Task:
    return Task(
        id=task_id, title=title, projectId=project_id,
        priority=priority, status=status, dueDate=due_date,
    )


def _make_intent_data(project_name: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"slots": {}}
    if project_name:
        data["slots"]["project_name"] = {"value": project_name}
    return data


# --- handle_project_tasks ---


async def test_project_tasks_no_auth() -> None:
    message = _make_message(access_token=None)
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=_make_mock_client(),
    )
    assert txt.AUTH_REQUIRED_NO_LINKING in response.text


async def test_project_tasks_no_name() -> None:
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data(),
        ticktick_client_factory=_make_mock_client(),
    )
    assert response.text == txt.PROJECT_TASKS_NAME_REQUIRED


async def test_project_tasks_not_found() -> None:
    projects = [_make_project(project_id="p1", name="Дом")]
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Несуществующий"),
        ticktick_client_factory=_make_mock_client(projects=projects),
    )
    assert "не найден" in response.text


async def test_project_tasks_success() -> None:
    projects = [_make_project(project_id="p1", name="Работа")]
    tasks = [
        _make_task(task_id="t1", title="Отчёт", project_id="p1"),
        _make_task(task_id="t2", title="Звонок", project_id="p1"),
    ]
    factory = _make_mock_client(projects=projects, tasks=tasks)
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=factory,
    )
    assert "Отчёт" in response.text
    assert "Звонок" in response.text
    assert "Работа" in response.text


async def test_project_tasks_empty() -> None:
    projects = [_make_project(project_id="p1", name="Работа")]
    factory = _make_mock_client(projects=projects, tasks=[])
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.PROJECT_NO_TASKS.format(project="Работа")


async def test_project_tasks_api_error() -> None:
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.get_projects = AsyncMock(
        side_effect=Exception("fail")
    )
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("X"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.API_ERROR
