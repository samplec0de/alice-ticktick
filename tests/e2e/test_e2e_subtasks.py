"""E2E tests: Section 3.12 — Subtasks (add, list)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_add_subtask(yandex_client: YandexDialogsClient) -> None:
    """Add a subtask to a task."""
    response = await yandex_client.send(
        "добавь подзадачу кктест проверить документы к задаче кктест купить хлеб"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "Подзадача" in response or "не найдена" in response or "не удалось" in response.lower()


async def test_add_subtask_alt(yandex_client: YandexDialogsClient) -> None:
    """Add a subtask using alternative phrasing."""
    response = await yandex_client.send(
        "добавь подзадачу кктест собрать отзывы к задаче кктест подготовить презентацию"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "Подзадача" in response or "не найдена" in response or "не удалось" in response.lower()


async def test_list_subtasks(yandex_client: YandexDialogsClient) -> None:
    """List subtasks of a task."""
    response = await yandex_client.send("покажи подзадачи задачи кктест купить хлеб")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert (
        "Подзадачи" in response
        or "нет подзадач" in response
        or "не найдена" in response
        or "ошибка" in response.lower()
    )


async def test_list_subtasks_alt(yandex_client: YandexDialogsClient) -> None:
    """List subtasks using alternative phrasing."""
    response = await yandex_client.send("какие подзадачи у задачи кктест подготовить презентацию")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "Подзадачи" in response or "нет подзадач" in response or "не найдена" in response
