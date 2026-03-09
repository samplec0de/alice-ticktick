"""E2E tests: Section 3.13 — Checklists (add item, show, check, delete)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_add_checklist_item(yandex_client: YandexDialogsClient) -> None:
    """Add an item to a task's checklist."""
    response = await yandex_client.send(
        "добавь пункт кктест проверить тесты в чеклист задачи кктест купить хлеб"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "добавлен" in response or "не найдена" in response


@pytest.mark.xfail(
    reason="NLU: add_subtask sometimes intercepts add_checklist_item phrases",
    strict=False,
)
async def test_add_checklist_item_alt(
    yandex_client: YandexDialogsClient,
) -> None:
    """Add a different item to a task's checklist."""
    response = await yandex_client.send(
        "добавь пункт кктест написать отчёт в чеклист задачи кктест подготовить презентацию"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "добавлен" in response or "не найдена" in response


@pytest.mark.xfail(
    reason="NLU: list_tasks $Priority (.+) intercepts 'чеклист' as priority value",
    strict=False,
)
async def test_show_checklist(yandex_client: YandexDialogsClient) -> None:
    """Show the checklist of a task."""
    response = await yandex_client.send("покажи чеклист задачи кктест купить хлеб")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "Чеклист" in response or "пуст" in response or "не найдена" in response


@pytest.mark.xfail(
    reason="NLU: list_tasks $Priority (.+) intercepts 'чеклист' as priority value",
    strict=False,
)
async def test_show_checklist_alt(
    yandex_client: YandexDialogsClient,
) -> None:
    """Show the checklist using alternative phrasing."""
    response = await yandex_client.send("что в чеклисте задачи кктест подготовить презентацию")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "Чеклист" in response or "пуст" in response or "не найдена" in response


async def test_check_item(yandex_client: YandexDialogsClient) -> None:
    """Mark a checklist item as done."""
    response = await yandex_client.send(
        "отметь пункт кктест проверить тесты в чеклисте задачи кктест купить хлеб"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "отмечен" in response or "не найден" in response or "не найдена" in response


async def test_delete_checklist_item(
    yandex_client: YandexDialogsClient,
) -> None:
    """Delete a checklist item."""
    response = await yandex_client.send(
        "удали пункт кктест проверить тесты из чеклиста задачи кктест купить хлеб"
    )
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    assert "удалён" in response or "не найден" in response or "не найдена" in response
