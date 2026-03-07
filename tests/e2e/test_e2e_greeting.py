"""E2E tests: Section 3.1 — Greeting / new session."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_greeting_new_session(yandex_client: YandexDialogsClient) -> None:
    """Starting a new session should return a welcome message."""
    response = await yandex_client.send_new_session()
    r = response.lower()
    assert any(
        word in r
        for word in ("привет", "с возвращением", "слушаю", "добро пожаловать", "тиктик", "помощь")
    ), f"Unexpected greeting: {response}"
