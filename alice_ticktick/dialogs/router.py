"""Alice skill router configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aliceio import Router
from aliceio.types import Response

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.filters import IntentFilter, NewSessionFilter
from alice_ticktick.dialogs.handlers import (
    handle_complete_task,
    handle_create_task,
    handle_delete_confirm,
    handle_delete_reject,
    handle_delete_task,
    handle_edit_task,
    handle_list_tasks,
    handle_overdue_tasks,
    handle_search_task,
    handle_unknown,
    handle_welcome,
)
from alice_ticktick.dialogs.intents import (
    COMPLETE_TASK,
    CREATE_TASK,
    DELETE_TASK,
    EDIT_TASK,
    LIST_TASKS,
    OVERDUE_TASKS,
    SEARCH_TASK,
)
from alice_ticktick.dialogs.states import DeleteTaskStates

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext
    from aliceio.types import Message

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


@router.message(IntentFilter(SEARCH_TASK))
async def on_search_task(message: Message, intent_data: dict[str, Any]) -> Response:
    """Handle search_task intent."""
    return await handle_search_task(message, intent_data)


@router.message(IntentFilter(EDIT_TASK))
async def on_edit_task(message: Message, intent_data: dict[str, Any]) -> Response:
    """Handle edit_task intent."""
    return await handle_edit_task(message, intent_data)


@router.message(IntentFilter(DELETE_TASK))
async def on_delete_task(
    message: Message, intent_data: dict[str, Any], state: FSMContext
) -> Response:
    """Handle delete_task intent."""
    return await handle_delete_task(message, intent_data, state)


# FSM handlers for delete confirmation — must be BEFORE the unknown handler
@router.message(DeleteTaskStates.confirm, IntentFilter("YANDEX.CONFIRM"))
async def on_delete_confirm(message: Message, state: FSMContext) -> Response:
    """Handle delete confirmation."""
    return await handle_delete_confirm(message, state)


@router.message(DeleteTaskStates.confirm, IntentFilter("YANDEX.REJECT"))
async def on_delete_reject(message: Message, state: FSMContext) -> Response:
    """Handle delete rejection."""
    return await handle_delete_reject(message, state)


@router.message(DeleteTaskStates.confirm)
async def on_delete_other(message: Message) -> Response:
    """Handle unexpected input during delete confirmation."""
    return Response(text=txt.DELETE_CONFIRM_PROMPT)


# Fallback — must be LAST
@router.message()
async def on_unknown(message: Message) -> Response:
    """Fallback for unrecognized commands."""
    return await handle_unknown(message)
