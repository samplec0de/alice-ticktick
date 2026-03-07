"""E2E tests: Section 3.11 — Add reminder to existing task."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

TASK_NAME = "кктест напоминаний"


async def test_reminder_30min(yandex_client: YandexDialogsClient) -> None:
    """напомни о задаче за 30 минут."""
    response = await yandex_client.send(f"напомни о задаче {TASK_NAME} за 30 минут")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "апоминание" in response.lower() or "не найдена" in response.lower()


async def test_reminder_hour(yandex_client: YandexDialogsClient) -> None:
    """напомни про задачу за час."""
    response = await yandex_client.send(f"напомни про задачу {TASK_NAME} за час")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "апоминание" in response.lower() or "не найдена" in response.lower()


async def test_reminder_1day(yandex_client: YandexDialogsClient) -> None:
    """напомни о задаче за 1 день."""
    response = await yandex_client.send(f"напомни о задаче {TASK_NAME} за 1 день")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "апоминание" in response.lower() or "не найдена" in response.lower()


async def test_reminder_2hours(yandex_client: YandexDialogsClient) -> None:
    """поставь напоминание о задаче за 2 часа."""
    response = await yandex_client.send(f"поставь напоминание о задаче {TASK_NAME} за 2 часа")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "апоминание" in response.lower() or "не найдена" in response.lower()


async def test_reminder_day(yandex_client: YandexDialogsClient) -> None:
    """напомни о задаче за день."""
    response = await yandex_client.send(f"напомни о задаче {TASK_NAME} за день")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "апоминание" in response.lower() or "не найдена" in response.lower()
