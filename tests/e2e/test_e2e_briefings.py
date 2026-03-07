"""E2E tests: Section 3.15 — Briefings (morning, evening)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_morning_briefing(yandex_client: YandexDialogsClient) -> None:
    """Morning briefing should start with 'Доброе утро'."""
    response = await yandex_client.send("доброе утро")
    assert "доброе утро" in response.lower(), f"Expected 'Доброе утро' in response: {response}"


async def test_evening_briefing(yandex_client: YandexDialogsClient) -> None:
    """Evening briefing should start with 'Итоги дня'."""
    response = await yandex_client.send("вечерний брифинг")
    assert "итоги дня" in response.lower(), f"Expected 'Итоги дня' in response: {response}"
