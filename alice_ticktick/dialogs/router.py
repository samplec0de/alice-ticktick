"""Alice skill router configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aliceio import Router
from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.filters import IntentFilter, NewSessionFilter
from alice_ticktick.dialogs.handlers import (
    handle_add_checklist_item,
    handle_add_reminder,
    handle_add_subtask,
    handle_check_item,
    handle_complete_task,
    handle_create_recurring_task,
    handle_create_task,
    handle_delete_checklist_item,
    handle_delete_confirm,
    handle_delete_reject,
    handle_delete_task,
    handle_edit_task,
    handle_goodbye,
    handle_help,
    handle_list_subtasks,
    handle_list_tasks,
    handle_overdue_tasks,
    handle_search_task,
    handle_show_checklist,
    handle_unknown,
    handle_welcome,
)
from alice_ticktick.dialogs.intents import (
    ADD_CHECKLIST_ITEM,
    ADD_REMINDER,
    ADD_SUBTASK,
    CHECK_ITEM,
    COMPLETE_TASK,
    CREATE_RECURRING_TASK,
    CREATE_TASK,
    DELETE_CHECKLIST_ITEM,
    DELETE_TASK,
    EDIT_TASK,
    LIST_SUBTASKS,
    LIST_TASKS,
    OVERDUE_TASKS,
    SEARCH_TASK,
    SHOW_CHECKLIST,
)
from alice_ticktick.dialogs.states import DeleteTaskStates

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext
    from aliceio.types import Message

logger = logging.getLogger(__name__)

_MAX_CONFIRM_RETRIES = 3

router = Router(name="main")


@router.message(NewSessionFilter())
async def on_new_session(message: Message) -> Response:
    """Greet user on new session."""
    return await handle_welcome(message)


@router.message(IntentFilter("YANDEX.HELP"))
@router.message(IntentFilter("YANDEX.WHAT_CAN_YOU_DO"))
async def on_help(message: Message) -> Response:
    """Handle help and 'what can you do' requests."""
    return await handle_help(message)


# --- Specific "добавь..." intents BEFORE generic create_task ---
_SUBTASK_KEYWORDS = frozenset({"подзадачу", "подзадача", "подзадачи"})


@router.message(IntentFilter(ADD_SUBTASK))
async def on_add_subtask(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle add_subtask intent.

    Disambiguate with create_task: "создай задачу X в проект Y" matches both
    intents because "в" looks like a subtask separator.  Prefer create_task
    unless the utterance explicitly contains a subtask keyword.
    """
    if message.nlu and message.nlu.intents and CREATE_TASK in message.nlu.intents:
        tokens = set(message.nlu.tokens or [])
        if not tokens & _SUBTASK_KEYWORDS:
            create_data = message.nlu.intents[CREATE_TASK]
            return await handle_create_task(message, create_data, event_update=event_update)
    return await handle_add_subtask(message, intent_data, event_update=event_update)


@router.message(IntentFilter(ADD_CHECKLIST_ITEM))
async def on_add_checklist_item(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle add_checklist_item intent."""
    return await handle_add_checklist_item(message, intent_data, event_update=event_update)


@router.message(IntentFilter(CREATE_RECURRING_TASK))
async def on_create_recurring_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_recurring_task intent."""
    return await handle_create_recurring_task(message, intent_data, event_update=event_update)


@router.message(IntentFilter(ADD_REMINDER))
async def on_add_reminder(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle add_reminder intent."""
    return await handle_add_reminder(message, intent_data, event_update=event_update)


@router.message(IntentFilter(CREATE_TASK))
async def on_create_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_task intent."""
    return await handle_create_task(message, intent_data, event_update=event_update)


# --- Specific "покажи..." intents BEFORE generic list_tasks ---
@router.message(IntentFilter(LIST_SUBTASKS))
async def on_list_subtasks(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle list_subtasks intent."""
    return await handle_list_subtasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(LIST_TASKS))
async def on_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    event_update: Update,
) -> Response:
    """Handle list_tasks intent."""
    return await handle_list_tasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(OVERDUE_TASKS))
async def on_overdue_tasks(message: Message, event_update: Update) -> Response:
    """Handle overdue_tasks intent."""
    return await handle_overdue_tasks(message, event_update=event_update)


# --- Specific "отметь..." intent BEFORE generic complete_task ---
@router.message(IntentFilter(CHECK_ITEM))
async def on_check_item(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle check_item intent."""
    return await handle_check_item(message, intent_data, event_update=event_update)


@router.message(IntentFilter(COMPLETE_TASK))
async def on_complete_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle complete_task intent."""
    return await handle_complete_task(message, intent_data, event_update=event_update)


@router.message(IntentFilter(SEARCH_TASK))
async def on_search_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle search_task intent."""
    return await handle_search_task(message, intent_data, event_update=event_update)


# --- show_checklist BEFORE edit_task for safety ---
@router.message(IntentFilter(SHOW_CHECKLIST))
async def on_show_checklist(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle show_checklist intent."""
    return await handle_show_checklist(message, intent_data, event_update=event_update)


@router.message(IntentFilter(EDIT_TASK))
async def on_edit_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle edit_task intent."""
    return await handle_edit_task(message, intent_data, event_update=event_update)


# --- Specific "удали..." intent BEFORE generic delete_task ---
@router.message(IntentFilter(DELETE_CHECKLIST_ITEM))
async def on_delete_checklist_item(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle delete_checklist_item intent."""
    return await handle_delete_checklist_item(message, intent_data, event_update=event_update)


@router.message(IntentFilter(DELETE_TASK))
async def on_delete_task(
    message: Message, intent_data: dict[str, Any], state: FSMContext, event_update: Update
) -> Response:
    """Handle delete_task intent."""
    return await handle_delete_task(message, intent_data, state, event_update=event_update)


# FSM handlers for delete confirmation — must be BEFORE the unknown handler
@router.message(DeleteTaskStates.confirm, IntentFilter("YANDEX.CONFIRM"))
async def on_delete_confirm(message: Message, state: FSMContext, event_update: Update) -> Response:
    """Handle delete confirmation."""
    return await handle_delete_confirm(message, state, event_update=event_update)


@router.message(DeleteTaskStates.confirm, IntentFilter("YANDEX.REJECT"))
async def on_delete_reject(message: Message, state: FSMContext) -> Response:
    """Handle delete rejection."""
    return await handle_delete_reject(message, state)


@router.message(DeleteTaskStates.confirm)
async def on_delete_other(message: Message, state: FSMContext) -> Response:
    """Handle unexpected input during delete confirmation."""
    data = await state.get_data()
    retries = data.get("_confirm_retries", 0) + 1
    logger.debug("Unexpected input during delete confirm: %r (retry %d)", message.command, retries)

    if retries >= _MAX_CONFIRM_RETRIES:
        await state.clear()
        return Response(text=txt.DELETE_CANCELLED)

    await state.set_data({**data, "_confirm_retries": retries})
    return Response(text=txt.DELETE_CONFIRM_PROMPT)


@router.message(IntentFilter("YANDEX.GOODBYE"))
async def on_goodbye(message: Message) -> Response:
    """Handle goodbye."""
    return await handle_goodbye(message)


# Fallback — must be LAST
@router.message()
async def on_unknown(message: Message) -> Response:
    """Fallback for unrecognized commands."""
    return await handle_unknown(message)
