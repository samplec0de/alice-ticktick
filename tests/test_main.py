"""Tests for Cloud Function entry point."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from alice_ticktick.main import handler


def _make_event(
    *,
    command: str = "",
    new: bool = True,
    intents: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Build a minimal Alice webhook event dict."""
    nlu: dict[str, Any] = {"tokens": [], "entities": [], "intents": intents or {}}
    user: dict[str, Any] | None = None
    if access_token is not None:
        user = {"user_id": "test-user", "access_token": access_token}

    return {
        "meta": {
            "locale": "ru-RU",
            "timezone": "Europe/Moscow",
            "client_id": "test",
            "interfaces": {},
        },
        "request": {
            "type": "SimpleUtterance",
            "command": command,
            "original_utterance": command,
            "nlu": nlu,
        },
        "session": {
            "message_id": 0,
            "session_id": "test-session",
            "skill_id": "test-skill",
            "new": new,
            "application": {"application_id": "test-app"},
            "user": user,
        },
        "version": "1.0",
    }


async def test_handler_new_session() -> None:
    event = _make_event(new=True)
    result = await handler(event, None)
    assert "response" in result
    assert "Привет" in result["response"]["text"]


async def test_handler_unknown_command() -> None:
    event = _make_event(new=False, command="абракадабра")
    result = await handler(event, None)
    assert "response" in result
    assert "Не поняла" in result["response"]["text"]


async def test_handler_returns_version() -> None:
    event = _make_event(new=True)
    result = await handler(event, None)
    assert result.get("version") == "1.0"


async def test_handler_error_returns_fallback() -> None:
    event = _make_event(new=True)
    with patch(
        "alice_ticktick.main._process_event",
        new_callable=AsyncMock,
        side_effect=Exception("boom"),
    ):
        result = await handler(event, None)
    assert "response" in result
    assert "ошибка" in result["response"]["text"].lower()
