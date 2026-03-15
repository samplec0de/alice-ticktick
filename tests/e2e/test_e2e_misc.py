"""E2E tests: Sections 3.16 + 3.17 — Help, Goodbye, Fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# 3.16  Help (3 tests)
# ---------------------------------------------------------------------------


async def test_help(yandex_client: YandexDialogsClient) -> None:
    """'помощь' should return help text."""
    response = await yandex_client.send("помощь")
    assert "Я умею" in response, f"Expected 'Я умею' in response: {response}"


async def test_help_what_can_you_do(
    yandex_client: YandexDialogsClient,
) -> None:
    """'что ты умеешь' should return help text."""
    response = await yandex_client.send("что ты умеешь")
    assert "Я умею" in response, f"Expected 'Я умею' in response: {response}"


async def test_help_alt(yandex_client: YandexDialogsClient) -> None:
    """'помоги' should return help text."""
    response = await yandex_client.send("помоги")
    assert "Я умею" in response, f"Expected 'Я умею' in response: {response}"


# ---------------------------------------------------------------------------
# 3.16a Help — topic help (3 tests)
# ---------------------------------------------------------------------------


async def test_help_topic_create(yandex_client: YandexDialogsClient) -> None:
    """'помощь с созданием' should return topic-specific help."""
    response = await yandex_client.send("помощь с созданием")
    r = response.lower()
    assert "создан" in r or "создай" in r, f"Expected creation topic in: {response}"


async def test_help_topic_via_question(
    yandex_client: YandexDialogsClient,
) -> None:
    """'как удалить задачу' should return topic help, not fallback."""
    response = await yandex_client.send("как удалить задачу")
    assert "не распознана" not in response.lower(), f"Got fallback: {response}"


async def test_help_general_has_topic_hint(
    yandex_client: YandexDialogsClient,
) -> None:
    """'помощь' should mention topic help availability."""
    response = await yandex_client.send("помощь")
    assert "помощь с" in response.lower(), f"Expected topic hint in: {response}"


# ---------------------------------------------------------------------------
# 3.16b Goodbye (2 tests)
# ---------------------------------------------------------------------------


async def test_goodbye(yandex_client: YandexDialogsClient) -> None:
    """'до свидания' should end the session."""
    response = await yandex_client.send("до свидания")
    assert response  # any response is acceptable


async def test_goodbye_bye(yandex_client: YandexDialogsClient) -> None:
    """'пока' should end the session."""
    response = await yandex_client.send("пока")
    assert response  # any response is acceptable


# ---------------------------------------------------------------------------
# 3.17  Fallback / unknown commands (3 tests)
# ---------------------------------------------------------------------------


async def test_fallback_joke(yandex_client: YandexDialogsClient) -> None:
    """Unrecognized command 'расскажи анекдот' should trigger fallback."""
    response = await yandex_client.send("расскажи анекдот")
    assert "не распознана" in response.lower(), f"Expected fallback: {response}"


async def test_fallback_weather(
    yandex_client: YandexDialogsClient,
) -> None:
    """Unrecognized command 'какая погода' should trigger fallback."""
    response = await yandex_client.send("какая погода")
    assert "не распознана" in response.lower(), f"Expected fallback: {response}"


async def test_fallback_alice(yandex_client: YandexDialogsClient) -> None:
    """'алиса' — may trigger fallback or another handler."""
    response = await yandex_client.send("алиса")
    assert response, "Expected a non-empty response"
