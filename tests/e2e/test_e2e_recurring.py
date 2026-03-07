"""E2E tests: Section 3.10 — Create recurring tasks via 'напоминай' / 'повторяй'."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_recurring_every_monday(yandex_client: YandexDialogsClient) -> None:
    """напоминай каждый понедельник проверить кктест."""
    response = await yandex_client.send("напоминай каждый понедельник проверить кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()
    assert "понедельник" in response.lower()


@pytest.mark.xfail(
    reason="NLU may consume 'каждый день' as YANDEX.DATETIME instead of recurrence",
    strict=False,
)
async def test_recurring_every_day(yandex_client: YandexDialogsClient) -> None:
    """напоминай каждый день пить воду кктест."""
    response = await yandex_client.send("напоминай каждый день пить воду кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()
    assert "каждый день" in response.lower() or "ежедневно" in response.lower()


async def test_recurring_daily(yandex_client: YandexDialogsClient) -> None:
    """напоминай ежедневно делать кктест."""
    response = await yandex_client.send("напоминай ежедневно делать кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()


async def test_recurring_weekly(yandex_client: YandexDialogsClient) -> None:
    """напоминай еженедельно проверить кктест."""
    response = await yandex_client.send("напоминай еженедельно проверить кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()


async def test_recurring_monthly(yandex_client: YandexDialogsClient) -> None:
    """напоминай ежемесячно оплатить кктест."""
    response = await yandex_client.send("напоминай ежемесячно оплатить кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()


async def test_recurring_every_2_days(yandex_client: YandexDialogsClient) -> None:
    """напоминай каждые 2 дня поливать кктест."""
    response = await yandex_client.send("напоминай каждые 2 дня поливать кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()


async def test_recurring_every_15th(yandex_client: YandexDialogsClient) -> None:
    """напоминай каждое 15 число оплатить кктест."""
    response = await yandex_client.send("напоминай каждое 15 число оплатить кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()


async def test_recurring_repeat_wednesday(yandex_client: YandexDialogsClient) -> None:
    """повторяй каждую среду уборка кктест."""
    response = await yandex_client.send("повторяй каждую среду уборка кктест")
    assert UNKNOWN not in response, f"Intent not recognized: {response}"
    assert "готово" in response.lower()
