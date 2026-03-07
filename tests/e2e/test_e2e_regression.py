"""E2E tests: Section 5 — Regression tests for known bugs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_edit_task_date_consumed(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: edit_task should fire, not lose the date.

    Fixed in commit 201ab72.
    """
    response = await yandex_client.send("перенеси задачу сменить полотенца на завтра")
    assert response != UNKNOWN, f"Intent not recognized: {response}"
    # Should be an edit response, not a create or fallback
    assert (
        "обновлена" in response.lower()
        or "не найдена" in response.lower()
        or "перемещена" in response.lower()
        or "изменить" in response.lower()
    ), f"Expected edit_task response: {response}"


async def test_subtask_not_intercepted(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: add_subtask should not be intercepted by create_task."""
    response = await yandex_client.send(
        "добавь подзадачу кктест купить средство к задаче сменить полотенца"
    )
    assert "Подзадача" in response or "не найдена" in response, (
        f"Expected subtask response, got: {response}"
    )


@pytest.mark.xfail(
    reason="create_task intercepts checklist intent",
    strict=False,
)
async def test_checklist_not_intercepted(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: add checklist item should not be intercepted."""
    response = await yandex_client.send(
        "добавь пункт кктест купить мыло в чеклист задачи сменить полотенца"
    )
    assert "добавлен" in response or "не найдена" in response, (
        f"Expected checklist response, got: {response}"
    )


async def test_check_item_not_intercepted(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: check_item should not be intercepted."""
    response = await yandex_client.send(
        "отметь пункт кктест поменять полотенца в чеклисте задачи сменить полотенца"
    )
    assert "отмечен" in response or "не найден" in response, (
        f"Expected check_item response, got: {response}"
    )


async def test_delete_checklist_not_intercepted(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: delete checklist item should not be intercepted."""
    response = await yandex_client.send(
        "удали пункт кктест купить мыло из чеклиста задачи сменить полотенца"
    )
    assert "удалён" in response or "не найден" in response, (
        f"Expected delete_checklist_item response, got: {response}"
    )


@pytest.mark.xfail(
    reason="YANDEX.GOODBYE doesn't work in text mode",
    strict=False,
)
async def test_goodbye_text_mode(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: goodbye should work in text testing mode."""
    response = await yandex_client.send("до свидания")
    assert "До встречи" in response or "Удачного дня" in response, (
        f"Expected goodbye response, got: {response}"
    )


async def test_search_transliteration(
    yandex_client: YandexDialogsClient,
) -> None:
    """Regression: 'макбук' should find a task named 'MacBook'."""
    response = await yandex_client.send("найди задачу про макбук")
    assert "MacBook" in response or "макбук" in response.lower(), (
        f"Expected transliteration match, got: {response}"
    )
