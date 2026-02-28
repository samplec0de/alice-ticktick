"""Alice skill router configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aliceio import Router

from alice_ticktick.dialogs.filters import IntentFilter, NewSessionFilter
from alice_ticktick.dialogs.handlers import (
    handle_complete_task,
    handle_create_task,
    handle_list_tasks,
    handle_overdue_tasks,
    handle_unknown,
    handle_welcome,
)
from alice_ticktick.dialogs.intents import COMPLETE_TASK, CREATE_TASK, LIST_TASKS, OVERDUE_TASKS

if TYPE_CHECKING:
    from aliceio.types import Message, Response

router = Router(name="main")


@router.message(NewSessionFilter())
async def on_new_session(message: Message) -> Response:
    """Greet user on new session."""
    return await handle_welcome(message)


@router.message(IntentFilter(CREATE_TASK))
async def on_create_task(message: Message, intent_data: dict[str, Any]) -> Response:
    """Handle create_task intent."""
    return await handle_create_task(message, intent_data)


@router.message(IntentFilter(LIST_TASKS))
async def on_list_tasks(message: Message, intent_data: dict[str, Any]) -> Response:
    """Handle list_tasks intent."""
    return await handle_list_tasks(message, intent_data)


@router.message(IntentFilter(OVERDUE_TASKS))
async def on_overdue_tasks(message: Message) -> Response:
    """Handle overdue_tasks intent."""
    return await handle_overdue_tasks(message)


@router.message(IntentFilter(COMPLETE_TASK))
async def on_complete_task(message: Message, intent_data: dict[str, Any]) -> Response:
    """Handle complete_task intent."""
    return await handle_complete_task(message, intent_data)


@router.message()
async def on_unknown(message: Message) -> Response:
    """Fallback for unrecognized commands."""
    return await handle_unknown(message)
