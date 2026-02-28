"""Tests for custom aliceio filters."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from alice_ticktick.dialogs.filters import IntentFilter, NewSessionFilter


def _make_message(
    *,
    new: bool = False,
    intents: dict[str, Any] | None = None,
    has_nlu: bool = True,
) -> MagicMock:
    """Create a mock Message."""
    message = MagicMock()
    message.session.new = new
    if has_nlu and intents is not None:
        message.nlu = MagicMock()
        message.nlu.intents = intents
    elif has_nlu:
        message.nlu = MagicMock()
        message.nlu.intents = {}
    else:
        message.nlu = None
    return message


class TestIntentFilter:
    async def test_match(self) -> None:
        f = IntentFilter("create_task")
        message = _make_message(intents={"create_task": {"slots": {}}})
        result = await f(message)
        assert isinstance(result, dict)
        assert "intent_data" in result

    async def test_no_match(self) -> None:
        f = IntentFilter("create_task")
        message = _make_message(intents={"list_tasks": {"slots": {}}})
        result = await f(message)
        assert result is False

    async def test_no_nlu(self) -> None:
        f = IntentFilter("create_task")
        message = _make_message(has_nlu=False)
        result = await f(message)
        assert result is False

    async def test_empty_intents(self) -> None:
        f = IntentFilter("create_task")
        message = _make_message(intents={})
        result = await f(message)
        assert result is False

    def test_repr(self) -> None:
        f = IntentFilter("create_task")
        assert "create_task" in repr(f)


class TestNewSessionFilter:
    async def test_new_session(self) -> None:
        f = NewSessionFilter()
        message = _make_message(new=True)
        result = await f(message)
        assert result is True

    async def test_existing_session(self) -> None:
        f = NewSessionFilter()
        message = _make_message(new=False)
        result = await f(message)
        assert result is False
