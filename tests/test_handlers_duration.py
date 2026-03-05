"""Tests for task duration/range handling in create_task."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import _reset_project_cache, handle_create_task
from alice_ticktick.ticktick.models import Task


@pytest.fixture(autouse=True)
def _clear_project_cache() -> None:
    """Reset the project cache before each test."""
    _reset_project_cache()


def _make_message(
    *,
    tokens: list[str] | None = None,
    entities: list[Any] | None = None,
    access_token: str = "test-token",
) -> MagicMock:
    msg = MagicMock()
    msg.user = MagicMock()
    msg.user.access_token = access_token
    nlu = MagicMock()
    nlu.tokens = tokens or []
    nlu.entities = entities or []
    msg.nlu = nlu
    return msg


def _make_update(tz: str = "Europe/Moscow") -> MagicMock:
    update = MagicMock()
    update.meta.interfaces.account_linking = None
    update.meta.timezone = tz
    return update


def _make_mock_client() -> type:
    """Create a mock TickTickClient factory that captures create_task payload."""
    created_payloads: list[Any] = []

    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=[])
    client.get_tasks = AsyncMock(return_value=[])
    client.get_inbox_tasks = AsyncMock(return_value=[])

    async def _capture_create(payload: Any) -> Task:
        created_payloads.append(payload)
        return Task(id="t1", projectId="inbox", title=payload.title)

    client.create_task = AsyncMock(side_effect=_capture_create)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    factory._created_payloads = created_payloads  # type: ignore[attr-defined]
    return factory


class TestDurationCreateTask:
    """Duration pattern: 'создай встречу совещание завтра в 10 на 2 часа'."""

    @pytest.mark.asyncio
    async def test_duration_with_date(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
            }
        }
        msg = _make_message(
            tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "2", "часа"]
        )
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        assert "совещание" in resp.text.lower()
        # Verify payload has startDate and dueDate
        payloads = factory._created_payloads  # type: ignore[attr-defined]
        assert len(payloads) == 1
        p = payloads[0]
        assert p.start_date is not None
        assert p.due_date is not None
        assert p.is_all_day is False

    @pytest.mark.asyncio
    async def test_duration_without_value(self) -> None:
        """'на час' → duration_value=None, duration_unit='час' → 1 hour."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "ланч"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 12,
                    }
                },
                "duration_unit": {"value": "час"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "ланч", "завтра", "в", "12", "на", "час"])
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        payloads = factory._created_payloads  # type: ignore[attr-defined]
        assert len(payloads) == 1
        p = payloads[0]
        assert p.start_date is not None
        assert p.due_date is not None

    @pytest.mark.asyncio
    async def test_duration_without_date_asks_clarification(self) -> None:
        """Duration without start time → ask for time."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "duration_unit": {"value": "час"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "совещание", "на", "час"])

        resp = await handle_create_task(msg, intent_data, None, _make_update())

        assert resp.text == txt.DURATION_MISSING_START_TIME

    @pytest.mark.asyncio
    async def test_duration_half_hour(self) -> None:
        """'на полчаса' → 30 minutes."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "стендап"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_unit": {"value": "полчаса"},
            }
        }
        msg = _make_message(
            tokens=["создай", "встречу", "стендап", "завтра", "в", "10", "на", "полчаса"]
        )
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        assert "стендап" in resp.text.lower()


class TestRangeCreateTask:
    """Range pattern: 'создай задачу митинг с 14 до 16'."""

    @pytest.mark.asyncio
    async def test_range_basic(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "митинг"},
                "range_start": {"value": {"hour": 14}},
                "range_end": {"value": {"hour": 16}},
            }
        }
        msg = _make_message(tokens=["создай", "задачу", "митинг", "с", "14", "до", "16"])
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        assert "митинг" in resp.text.lower()
        payloads = factory._created_payloads  # type: ignore[attr-defined]
        assert len(payloads) == 1
        p = payloads[0]
        assert p.start_date is not None
        assert p.due_date is not None
        assert p.is_all_day is False


class TestDurationCombinations:
    """Duration + priority/recurrence/reminder."""

    @pytest.mark.asyncio
    async def test_duration_with_priority(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
                "priority": {"value": "высокий"},
            }
        }
        msg = _make_message(
            tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "2", "часа"]
        )
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        assert "приоритет" in resp.text

    @pytest.mark.asyncio
    async def test_duration_with_reminder(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 1},
                "duration_unit": {"value": "час"},
                "reminder_value": {"value": 15},
                "reminder_unit": {"value": "минут"},
            }
        }
        msg = _make_message(
            tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "час"]
        )
        factory = _make_mock_client()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Готово" in resp.text
        assert "напоминание" in resp.text
