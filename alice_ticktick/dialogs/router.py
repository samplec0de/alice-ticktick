"""Alice skill router configuration."""

from __future__ import annotations

import logging
import re
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
    handle_complete_confirm,
    handle_complete_reject,
    handle_complete_task,
    handle_create_project,
    handle_create_recurring_task,
    handle_create_task,
    handle_delete_checklist_item,
    handle_delete_confirm,
    handle_delete_reject,
    handle_delete_task,
    handle_edit_confirm,
    handle_edit_reject,
    handle_edit_task,
    handle_evening_briefing,
    handle_goodbye,
    handle_help,
    handle_list_projects,
    handle_list_subtasks,
    handle_list_tasks,
    handle_morning_briefing,
    handle_overdue_tasks,
    handle_project_tasks,
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
    CREATE_PROJECT,
    CREATE_RECURRING_TASK,
    CREATE_TASK,
    DELETE_CHECKLIST_ITEM,
    DELETE_TASK,
    EDIT_TASK,
    EVENING_BRIEFING,
    LIST_PROJECTS,
    LIST_SUBTASKS,
    LIST_TASKS,
    MORNING_BRIEFING,
    OVERDUE_TASKS,
    PROJECT_TASKS,
    SEARCH_TASK,
    SHOW_CHECKLIST,
)
from alice_ticktick.dialogs.states import CompleteTaskStates, DeleteTaskStates, EditTaskStates

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext
    from aliceio.types import Message

logger = logging.getLogger(__name__)

_MAX_CONFIRM_RETRIES = 3

_CONFIRM_TOKENS = frozenset({"да", "конечно", "подтверждаю", "ладно", "давай", "удали"})
_REJECT_TOKENS = frozenset({"нет", "отмена", "отменить", "не", "отменяй"})

_GOODBYE_KEYWORDS = frozenset({"до свидания", "пока", "до встречи", "до скорого"})

# Checklist dispatch: keywords that indicate add_checklist_item intent.
# Substring matching is used, so "чеклист" covers all inflected forms.
_CHECKLIST_KEYWORDS = frozenset({"чеклист"})
_ITEM_KEYWORDS = frozenset({"пункт", "элемент", "пункте", "пункта"})

_CHECKLIST_ITEM_RE = re.compile(
    r"(?:добавь|добавить)\s+(?:пункт|элемент)\s+(.+?)\s+(?:в|к)\s+(?:чеклист|список)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)

_SHOW_CHECKLIST_RE = re.compile(
    r"(?:покажи|какой|что)\s+(?:чеклист|список|пункты)\s+(?:у|для|в)?\s*(?:задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_SHOW_CHECKLIST_ALT_RE = re.compile(
    r"что\s+(?:в|из)\s+(?:чеклисте|списке)\s+(?:задачи?)?\s*(.+)",
    re.IGNORECASE,
)

_SEARCH_FALLBACK_RE = re.compile(
    r"(?:поиск|ищи)\s+(?:задачи?|задач)?\s*(.+)",
    re.IGNORECASE,
)

# --- Edit fallback regexes ---
_EDIT_RENAME_RE = re.compile(
    r"переименуй\s+(?:задачу\s+)?(.+?)\s+в\s+(.+)",
    re.IGNORECASE,
)
_EDIT_MOVE_RE = re.compile(
    r"(?:перемести|переложи|перекинь|отправь)\s+(?:задачу?\s+)?(.+?)\s+в\s+(?:проект|список|папку)\s+(.+)",
    re.IGNORECASE,
)
_EDIT_REMOVE_RECURRENCE_RE = re.compile(
    r"(?:убери|отмени|удали)\s+(?:повторение|повтор)\s+(?:у|для|задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_EDIT_REMOVE_REMINDER_RE = re.compile(
    r"(?:убери|отмени|удали)\s+напоминание\s+(?:у|для|задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_EDIT_CHANGE_RECURRENCE_RE = re.compile(
    r"(?:поменяй|измени)\s+(?:повторение|повтор)\s+(?:у|для|задачи?)?\s*(.+?)\s+на\s+(.+)",
    re.IGNORECASE,
)
_EDIT_CHANGE_REMINDER_RE = re.compile(
    r"(?:поменяй|измени|поставь)\s+напоминание\s+(?:у|для|задачи?)?\s*(.+?)\s+за\s+(.+)",
    re.IGNORECASE,
)
_EDIT_PRIORITY_RE = re.compile(
    r"(?:поменяй|измени)\s+приоритет\s+(?:задачи?)?\s*(.+?)\s+(?:на|в)\s+(низкий|средний|высокий)",
    re.IGNORECASE,
)
# Must be last — "поменяй" overlaps with priority/recurrence/reminder patterns
_EDIT_GENERIC_RE = re.compile(
    r"(?:перенеси|поменяй|измени|сдвинь|обнови)\s+(?:задачу?\s+)?(.+)",
    re.IGNORECASE,
)


def _try_parse_edit_command(raw: str) -> dict[str, Any] | None:
    """Try to parse an edit command from raw utterance. Returns fake intent_data or None."""
    slots: dict[str, Any] = {}

    # Rename: "переименуй задачу X в Y"
    m = _EDIT_RENAME_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["new_name"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Move: "перемести задачу X в проект Y"
    m = _EDIT_MOVE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["new_project"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Remove recurrence: "убери повторение задачи X"
    m = _EDIT_REMOVE_RECURRENCE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["remove_recurrence"] = {"value": True}
        return {"slots": slots}

    # Remove reminder: "убери напоминание задачи X"
    m = _EDIT_REMOVE_REMINDER_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["remove_reminder"] = {"value": True}
        return {"slots": slots}

    # Change recurrence: "поменяй повторение задачи X на Y"
    m = _EDIT_CHANGE_RECURRENCE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["rec_freq"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Change reminder: "поменяй напоминание задачи X за Y"
    m = _EDIT_CHANGE_REMINDER_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["reminder_unit"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Edit priority: "поменяй приоритет задачи X на высокий"
    m = _EDIT_PRIORITY_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["new_priority"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Generic edit: "перенеси задачу X на завтра"
    m = _EDIT_GENERIC_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        return {"slots": slots}

    return None


_ADD_SUBTASK_FALLBACK_RE = re.compile(
    r"(?:добавь|создай)\s+подзадачу\s+(.+?)\s+(?:к|в)\s+задач[еуи]?\s+(.+)",
    re.IGNORECASE,
)

_CHECK_ITEM_RE = re.compile(
    r"(?:отметь|выполни)\s+(?:пункт|элемент)\s+(.+?)\s+(?:в|из)\s+(?:чеклиста?|списка?|чеклисте?)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)

_DELETE_CHECKLIST_ITEM_RE = re.compile(
    r"(?:удали|убери)\s+(?:пункт|элемент)\s+(.+?)\s+(?:из|от)\s+(?:чеклиста?|списка?)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)


def _try_parse_checklist_command(command: str) -> tuple[str, str] | None:
    """Попытаться извлечь item_name и task_name из команды чеклиста."""
    m = _CHECKLIST_ITEM_RE.search(command)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


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


@router.message(IntentFilter(MORNING_BRIEFING))
async def on_morning_briefing(message: Message, event_update: Update) -> Response:
    """Handle morning_briefing intent."""
    return await handle_morning_briefing(message, event_update=event_update)


@router.message(IntentFilter(EVENING_BRIEFING))
async def on_evening_briefing(message: Message, event_update: Update) -> Response:
    """Handle evening_briefing intent."""
    return await handle_evening_briefing(message, event_update=event_update)


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
    """Handle create_task intent.

    Also detects when NLU fired create_task but the utterance is actually
    an add_checklist_item command (e.g. 'добавь пункт X в чеклист задачи Y').
    """
    # Проверка: не является ли это командой add_checklist_item
    # Используем original_utterance (полная оригинальная фраза без нормализации),
    # с fallback на command (может быть пустой после нормализации Яндексом).
    utterance = (message.original_utterance or message.command or "").lower()
    if any(kw in utterance for kw in _CHECKLIST_KEYWORDS) and any(
        kw in utterance for kw in _ITEM_KEYWORDS
    ):
        parsed = _try_parse_checklist_command(message.original_utterance or message.command or "")
        if parsed:
            item_name, task_name = parsed
            fake_intent_data: dict[str, Any] = {
                "slots": {
                    "item_name": {"value": item_name},
                    "task_name": {"value": task_name},
                }
            }
            return await handle_add_checklist_item(
                message, fake_intent_data, event_update=event_update
            )
    return await handle_create_task(message, intent_data, event_update=event_update)


# --- Project intents BEFORE generic list_tasks ---
@router.message(IntentFilter(LIST_PROJECTS))
async def on_list_projects(message: Message, event_update: Update) -> Response:
    """Handle list_projects intent."""
    return await handle_list_projects(message, event_update=event_update)


@router.message(IntentFilter(PROJECT_TASKS))
async def on_project_tasks(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle project_tasks intent."""
    return await handle_project_tasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(CREATE_PROJECT))
async def on_create_project(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_project intent."""
    return await handle_create_project(message, intent_data, event_update=event_update)


# --- Specific "покажи..." intents BEFORE generic list_tasks ---
@router.message(IntentFilter(LIST_SUBTASKS))
async def on_list_subtasks(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle list_subtasks intent."""
    return await handle_list_subtasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(OVERDUE_TASKS))
async def on_overdue_tasks(
    message: Message,
    intent_data: dict[str, Any],
    event_update: Update,
) -> Response:
    """Handle overdue_tasks intent."""
    return await handle_overdue_tasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(LIST_TASKS))
async def on_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    event_update: Update,
) -> Response:
    """Handle list_tasks intent."""
    utterance = (message.original_utterance or message.command or "").lower()
    if "чеклист" in utterance or "пункты" in utterance:
        raw = message.original_utterance or message.command or ""
        m = _SHOW_CHECKLIST_RE.search(raw) or _SHOW_CHECKLIST_ALT_RE.search(raw)
        if m:
            task_name = m.group(1).strip()
            fake_intent_data: dict[str, Any] = {"slots": {"task_name": {"value": task_name}}}
            return await handle_show_checklist(
                message, fake_intent_data, event_update=event_update
            )
        # Regex didn't match but NLU routed to list_tasks — fall through to list_tasks below
    return await handle_list_tasks(message, intent_data, event_update=event_update)


# --- Specific "отметь..." intent BEFORE generic complete_task ---
@router.message(IntentFilter(CHECK_ITEM))
async def on_check_item(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle check_item intent."""
    return await handle_check_item(message, intent_data, event_update=event_update)


@router.message(IntentFilter(COMPLETE_TASK))
async def on_complete_task(
    message: Message, intent_data: dict[str, Any], state: FSMContext, event_update: Update
) -> Response:
    """Handle complete_task intent.

    Also detects when NLU fired complete_task but the utterance is actually
    a check_item command (e.g. 'отметь пункт X в чеклисте задачи Y').
    """
    utterance_ct = (message.original_utterance or message.command or "").lower()
    if any(kw in utterance_ct for kw in _CHECKLIST_KEYWORDS) and any(
        kw in utterance_ct for kw in _ITEM_KEYWORDS
    ):
        m = _CHECK_ITEM_RE.search(message.original_utterance or message.command or "")
        if m:
            item_name, task_name = m.group(1).strip(), m.group(2).strip()
            fake_intent_data: dict[str, Any] = {
                "slots": {
                    "item_name": {"value": item_name},
                    "task_name": {"value": task_name},
                }
            }
            return await handle_check_item(message, fake_intent_data, event_update=event_update)
    return await handle_complete_task(message, intent_data, state, event_update=event_update)


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
    message: Message, intent_data: dict[str, Any], state: FSMContext, event_update: Update
) -> Response:
    """Handle edit_task intent."""
    return await handle_edit_task(message, intent_data, state, event_update=event_update)


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
    """Handle delete_task intent.

    Also detects when NLU fired delete_task but the utterance is actually
    a delete_checklist_item command (e.g. 'удали пункт X из чеклиста задачи Y').
    """
    utterance_dt = (message.original_utterance or message.command or "").lower()
    if any(kw in utterance_dt for kw in _CHECKLIST_KEYWORDS) and any(
        kw in utterance_dt for kw in _ITEM_KEYWORDS
    ):
        m = _DELETE_CHECKLIST_ITEM_RE.search(message.original_utterance or message.command or "")
        if m:
            item_name, task_name = m.group(1).strip(), m.group(2).strip()
            fake_intent_data: dict[str, Any] = {
                "slots": {
                    "item_name": {"value": item_name},
                    "task_name": {"value": task_name},
                }
            }
            return await handle_delete_checklist_item(
                message, fake_intent_data, event_update=event_update
            )
    return await handle_delete_task(message, intent_data, state, event_update=event_update)


# FSM handlers for complete confirmation — must be BEFORE the unknown handler
@router.message(CompleteTaskStates.confirm, IntentFilter("YANDEX.CONFIRM"))
async def on_complete_confirm(
    message: Message, state: FSMContext, event_update: Update
) -> Response:
    """Handle complete confirmation."""
    return await handle_complete_confirm(message, state, event_update=event_update)


@router.message(CompleteTaskStates.confirm, IntentFilter("YANDEX.REJECT"))
async def on_complete_reject(message: Message, state: FSMContext) -> Response:
    """Handle complete rejection."""
    return await handle_complete_reject(message, state)


@router.message(CompleteTaskStates.confirm)
async def on_complete_other(message: Message, state: FSMContext) -> Response:
    """Handle unexpected input during complete confirmation."""
    tokens = set(message.nlu.tokens or []) if message.nlu else set()
    command_lower = (message.command or "").lower().strip()

    if tokens & _REJECT_TOKENS or command_lower in _REJECT_TOKENS:
        return await handle_complete_reject(message, state)
    if tokens & _CONFIRM_TOKENS or command_lower in _CONFIRM_TOKENS:
        return await handle_complete_confirm(message, state)

    data = await state.get_data()
    retries = data.get("_confirm_retries", 0) + 1

    if retries >= _MAX_CONFIRM_RETRIES:
        await state.clear()
        return Response(text=txt.COMPLETE_CANCELLED)

    await state.set_data({**data, "_confirm_retries": retries})
    return Response(text=txt.COMPLETE_CONFIRM.format(name=data.get("task_name", "")))


# FSM handlers for edit confirmation — must be BEFORE the unknown handler
@router.message(EditTaskStates.confirm, IntentFilter("YANDEX.CONFIRM"))
async def on_edit_confirm(message: Message, state: FSMContext, event_update: Update) -> Response:
    """Handle edit confirmation."""
    return await handle_edit_confirm(message, state, event_update=event_update)


@router.message(EditTaskStates.confirm, IntentFilter("YANDEX.REJECT"))
async def on_edit_reject(message: Message, state: FSMContext) -> Response:
    """Handle edit rejection."""
    return await handle_edit_reject(message, state)


@router.message(EditTaskStates.confirm)
async def on_edit_other(message: Message, state: FSMContext) -> Response:
    """Handle unexpected input during edit confirmation."""
    tokens = set(message.nlu.tokens or []) if message.nlu else set()
    command_lower = (message.command or "").lower().strip()

    if tokens & _REJECT_TOKENS or command_lower in _REJECT_TOKENS:
        return await handle_edit_reject(message, state)
    if tokens & _CONFIRM_TOKENS or command_lower in _CONFIRM_TOKENS:
        return await handle_edit_confirm(message, state)

    data = await state.get_data()
    retries = data.get("_confirm_retries", 0) + 1

    if retries >= _MAX_CONFIRM_RETRIES:
        await state.clear()
        return Response(text=txt.EDIT_CANCELLED)

    await state.set_data({**data, "_confirm_retries": retries})
    return Response(text=txt.EDIT_CONFIRM.format(name=data.get("task_name", "")))


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
    """Handle unexpected input during delete confirmation.

    Also handles 'нет'/'да' as reject/confirm when NLU does not fire
    YANDEX.CONFIRM / YANDEX.REJECT intents (e.g. after Lambda cold start).
    """
    # Token-based matching: catch reject/confirm words
    tokens = set(message.nlu.tokens or []) if message.nlu else set()
    command_lower = (message.command or "").lower().strip()

    if tokens & _REJECT_TOKENS or command_lower in _REJECT_TOKENS:
        return await handle_delete_reject(message, state)
    if tokens & _CONFIRM_TOKENS or command_lower in _CONFIRM_TOKENS:
        return await handle_delete_confirm(message, state)

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
async def on_unknown(
    message: Message, state: FSMContext | None = None, event_update: Update | None = None
) -> Response:
    """Fallback for unrecognized commands."""
    command_lower = (message.command or "").lower().strip()
    if command_lower in _GOODBYE_KEYWORDS:
        return await handle_goodbye(message)

    raw = message.original_utterance or message.command or ""

    # Search fallback: "поиск задачи X"
    m = _SEARCH_FALLBACK_RE.search(raw)
    if m:
        query = m.group(1).strip()
        if query:
            fake_intent_data: dict[str, Any] = {"slots": {"query": {"value": query}}}
            return await handle_search_task(message, fake_intent_data, event_update=event_update)

    # Subtask fallback: "добавь подзадачу X к задаче Y"
    m = _ADD_SUBTASK_FALLBACK_RE.search(raw)
    if m:
        subtask_name = m.group(1).strip()
        parent_name = m.group(2).strip()
        fake_subtask_data: dict[str, Any] = {
            "slots": {
                "subtask_name": {"value": subtask_name},
                "parent_name": {"value": parent_name},
            }
        }
        return await handle_add_subtask(message, fake_subtask_data, event_update=event_update)

    # Edit fallback (state is None when FSM is not configured — skip silently)
    edit_intent = _try_parse_edit_command(raw)
    if edit_intent is not None and state is not None:
        return await handle_edit_task(message, edit_intent, state, event_update=event_update)

    return await handle_unknown(message)
