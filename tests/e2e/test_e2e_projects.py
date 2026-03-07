"""E2E tests: Section 3.14 — Projects (list, tasks, create)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


@pytest.mark.xfail(
    reason="NLU: list_tasks intercepts 'покажи мои проекты'",
    strict=False,
)
async def test_list_projects(yandex_client: YandexDialogsClient) -> None:
    """List all user projects."""
    response = await yandex_client.send("покажи мои проекты")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "проект" in response.lower(), f"Expected 'проект' in response: {response}"


@pytest.mark.xfail(
    reason="NLU does not recognize 'задачи в проекте X' intent",
    strict=False,
)
async def test_project_tasks(yandex_client: YandexDialogsClient) -> None:
    """Show tasks in a specific project."""
    response = await yandex_client.send("задачи в проекте работа")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "задач" in response.lower() or "не найден" in response.lower(), (
        f"Unexpected response: {response}"
    )


async def test_create_project(yandex_client: YandexDialogsClient) -> None:
    """Create a new project."""
    response = await yandex_client.send("создай проект кктест учёба")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "создан" in response.lower(), f"Expected 'создан' in response: {response}"
