"""Tests for project management handlers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _reset_project_cache,
    handle_list_projects,
)
from alice_ticktick.ticktick.models import Project


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
