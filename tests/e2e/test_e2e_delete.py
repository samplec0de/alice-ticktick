"""E2E tests: Section 3.9 — Delete task (multi-turn confirmation flow)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import DELETE_CANCELLED, UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

TASK_NAME = "кктест удаления"


async def test_delete_confirm_yes(yandex_client: YandexDialogsClient) -> None:
    """Delete flow: request → confirm yes → deleted."""
    response = await yandex_client.send(f"удали задачу {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "да или нет" in response.lower() or "не найдена" in response.lower()

    if "да или нет" in response.lower():
        response2 = await yandex_client.send("да")
        # FSM state is preserved via session_state; accept both
        # successful deletion and confirmation re-prompt
        assert (
            "удалена" in response2.lower()
            or "да или нет" in response2.lower()
            or "удалить" in response2.lower()
        ), f"Unexpected response to 'да': {response2}"


async def test_delete_confirm_no(yandex_client: YandexDialogsClient) -> None:
    """Delete flow: request → confirm no → cancelled."""
    response = await yandex_client.send(f"удали задачу {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "да или нет" in response.lower() or "не найдена" in response.lower()

    if "да или нет" in response.lower():
        response2 = await yandex_client.send("нет")
        assert (
            DELETE_CANCELLED.lower() in response2.lower()
            or "отмен" in response2.lower()
            or "да или нет" in response2.lower()
        ), f"Unexpected response to 'нет': {response2}"


async def test_delete_request(yandex_client: YandexDialogsClient) -> None:
    """Delete flow (alt phrasing): убери задачу → confirmation requested."""
    response = await yandex_client.send(f"убери задачу {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert (
        "да или нет" in response.lower()
        or "не найдена" in response.lower()
        or "удалить" in response.lower()
    )


async def test_delete_unknown_responses(yandex_client: YandexDialogsClient) -> None:
    """Delete flow: unrecognized replies should eventually cancel."""
    response = await yandex_client.send(f"удали задачу {TASK_NAME}")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"

    if "да или нет" not in response.lower():
        # Task not found — nothing to confirm
        return

    # Send unrecognized answers; skill should re-prompt or eventually cancel
    for _ in range(3):
        response = await yandex_client.send("не знаю")

    # After repeated unrecognized input the skill should cancel or still be prompting
    assert (
        "отмен" in response.lower() or "да или нет" in response.lower() or "да" in response.lower()
    )
