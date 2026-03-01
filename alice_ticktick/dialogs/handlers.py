"""Intent handlers for Alice skill."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any

from aliceio.types import Message, Response

if TYPE_CHECKING:
    from aliceio.fsm.context import FSMContext

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import (
    extract_add_checklist_item_slots,
    extract_add_subtask_slots,
    extract_check_item_slots,
    extract_complete_task_slots,
    extract_create_task_slots,
    extract_delete_checklist_item_slots,
    extract_delete_task_slots,
    extract_edit_task_slots,
    extract_list_subtasks_slots,
    extract_list_tasks_slots,
    extract_search_task_slots,
    extract_show_checklist_slots,
)
from alice_ticktick.dialogs.nlp import (
    find_best_match,
    find_matches,
    parse_priority,
    parse_yandex_datetime,
)
from alice_ticktick.dialogs.states import DeleteTaskStates
from alice_ticktick.ticktick.client import TickTickClient
from alice_ticktick.ticktick.models import Task, TaskCreate, TaskPriority, TaskUpdate

logger = logging.getLogger(__name__)

ALICE_RESPONSE_MAX_LENGTH = 1024


def _format_date(d: datetime.date | datetime.datetime) -> str:
    """Format a date for display in Russian."""
    today = datetime.datetime.now(tz=datetime.UTC).date()
    day = d.date() if isinstance(d, datetime.datetime) else d

    if day == today:
        return "сегодня"
    if day == today + datetime.timedelta(days=1):
        return "завтра"
    if day == today - datetime.timedelta(days=1):
        return "вчера"
    return day.strftime("%d.%m.%Y")


def _format_task_line(idx: int, task: Task) -> str:
    """Format a single task for listing."""
    priority_label = {5: " [!]", 3: " [~]", 1: " [.]"}.get(task.priority, "")
    return f"{idx}. {task.title}{priority_label}"


def _truncate_response(text: str) -> str:
    """Truncate response to Alice's 1024-char limit."""
    if len(text) <= ALICE_RESPONSE_MAX_LENGTH:
        return text
    return text[: ALICE_RESPONSE_MAX_LENGTH - 1] + "…"


async def _gather_all_tasks(client: TickTickClient) -> list[Task]:
    """Fetch tasks from all projects in parallel."""
    projects = await client.get_projects()
    if not projects:
        return []
    task_lists = await asyncio.gather(
        *(client.get_tasks(p.id) for p in projects),
    )
    return [t for tasks in task_lists for t in tasks]


def _get_access_token(message: Message) -> str | None:
    """Extract TickTick access token from user session."""
    if message.user is None:
        return None
    return message.user.access_token


async def handle_welcome(message: Message) -> Response:
    """Handle new session greeting."""
    return Response(text=txt.WELCOME)


async def handle_help(message: Message) -> Response:
    """Handle help request."""
    return Response(text=txt.HELP)


async def handle_create_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle create_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_create_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.TASK_NAME_REQUIRED)

    # Parse optional date
    due_date_str: str | None = None
    date_display: str | None = None
    if slots.date:
        try:
            parsed_date = parse_yandex_datetime(slots.date)
            if isinstance(parsed_date, datetime.datetime):
                due_date_str = parsed_date.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            else:
                dt = datetime.datetime.combine(parsed_date, datetime.time(), tzinfo=datetime.UTC)
                due_date_str = dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            date_display = _format_date(parsed_date)
        except ValueError:
            pass

    # Parse optional priority
    priority_raw = parse_priority(slots.priority) or 0
    priority_value = TaskPriority(priority_raw)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            payload = TaskCreate(
                title=slots.task_name,
                priority=priority_value,
                dueDate=due_date_str,
            )
            await client.create_task(payload)
    except Exception:
        logger.exception("Failed to create task")
        return Response(text=txt.CREATE_ERROR)

    if date_display:
        return Response(
            text=txt.TASK_CREATED_WITH_DATE.format(
                name=slots.task_name,
                date=date_display,
            )
        )
    return Response(text=txt.TASK_CREATED.format(name=slots.task_name))


async def handle_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle list_tasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_list_tasks_slots(intent_data)

    # Determine target date
    if slots.date:
        try:
            target_date = parse_yandex_datetime(slots.date)
            if isinstance(target_date, datetime.datetime):
                target_day = target_date.date()
            else:
                target_day = target_date
        except ValueError:
            target_day = datetime.datetime.now(tz=datetime.UTC).date()
    else:
        target_day = datetime.datetime.now(tz=datetime.UTC).date()

    date_display = _format_date(target_day)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to list tasks")
        return Response(text=txt.API_ERROR)

    # Filter tasks for the target date
    day_tasks = [
        t
        for t in all_tasks
        if t.due_date is not None and t.due_date.date() == target_day and t.status == 0
    ]

    if not day_tasks:
        if target_day == datetime.datetime.now(tz=datetime.UTC).date():
            return Response(text=txt.NO_TASKS_TODAY)
        return Response(text=txt.NO_TASKS_FOR_DATE.format(date=date_display))

    count_str = txt.pluralize_tasks(len(day_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(day_tasks[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.TASKS_FOR_DATE.format(
                date=date_display,
                count=count_str,
                tasks=task_list,
            )
        )
    )


async def handle_overdue_tasks(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle overdue_tasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    today = datetime.datetime.now(tz=datetime.UTC).date()

    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to get overdue tasks")
        return Response(text=txt.API_ERROR)

    overdue = [
        t
        for t in all_tasks
        if t.due_date is not None and t.due_date.date() < today and t.status == 0
    ]

    if not overdue:
        return Response(text=txt.NO_OVERDUE)

    count_str = txt.pluralize_tasks(len(overdue))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(overdue[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.OVERDUE_TASKS_HEADER.format(
                count=count_str,
                tasks=task_list,
            )
        )
    )


async def handle_complete_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle complete_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_complete_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.COMPLETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            # Find task by fuzzy match
            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            await client.complete_task(matched_task.id, matched_task.project_id)

    except Exception:
        logger.exception("Failed to complete task")
        return Response(text=txt.COMPLETE_ERROR)

    return Response(text=txt.TASK_COMPLETED.format(name=best_match))


async def handle_search_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle search_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_search_task_slots(intent_data)

    if not slots.query:
        return Response(text=txt.SEARCH_QUERY_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to search tasks")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    titles = [t.title for t in active_tasks]
    matches = find_matches(slots.query, titles, limit=5)

    if not matches:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    matched_tasks = [active_tasks[idx] for _title, _score, idx in matches]

    count_str = txt.pluralize_tasks(len(matched_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(matched_tasks)]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(txt.SEARCH_RESULTS.format(count=count_str, tasks=task_list))
    )


async def handle_edit_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle edit_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_edit_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.EDIT_NAME_REQUIRED)

    # Check that at least one change is specified
    has_date = slots.new_date is not None
    has_priority = slots.new_priority is not None
    has_name = slots.new_name is not None

    if not has_date and not has_priority and not has_name:
        return Response(text=txt.EDIT_NO_CHANGES)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for edit")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    # Build update payload
    new_title: str | None = slots.new_name if has_name else None

    new_due_date: datetime.datetime | None = None
    if has_date and slots.new_date:
        try:
            parsed_date = parse_yandex_datetime(slots.new_date)
            if isinstance(parsed_date, datetime.datetime):
                new_due_date = parsed_date
            else:
                new_due_date = datetime.datetime.combine(
                    parsed_date, datetime.time(), tzinfo=datetime.UTC
                )
        except ValueError:
            logger.warning("Failed to parse date for edit: %s", slots.new_date)

    new_priority_value: TaskPriority | None = None
    if has_priority:
        raw = parse_priority(slots.new_priority)
        if raw is not None:
            new_priority_value = TaskPriority(raw)
        else:
            logger.warning("Unrecognized priority value: %s", slots.new_priority)

    # Check that at least one field was successfully parsed
    if new_title is None and new_due_date is None and new_priority_value is None:
        return Response(text=txt.EDIT_NO_CHANGES)

    payload = TaskUpdate(
        id=matched_task.id,
        projectId=matched_task.project_id,
        title=new_title,
        priority=new_priority_value,
        dueDate=new_due_date,
    )
    try:
        async with factory(access_token) as client:
            await client.update_task(payload)
    except Exception:
        logger.exception("Failed to edit task")
        return Response(text=txt.EDIT_ERROR)

    return Response(text=txt.EDIT_SUCCESS.format(name=best_match))


async def handle_delete_task(
    message: Message,
    intent_data: dict[str, Any],
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle delete_task intent — start confirmation flow."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_delete_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.DELETE_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for deletion")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    await state.set_state(DeleteTaskStates.confirm)
    await state.set_data(
        {
            "task_id": matched_task.id,
            "project_id": matched_task.project_id,
            "task_name": best_match,
        }
    )

    return Response(text=txt.DELETE_CONFIRM.format(name=best_match))


async def handle_delete_confirm(
    message: Message,
    state: FSMContext,
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle delete confirmation (user said 'yes')."""
    access_token = _get_access_token(message)
    if access_token is None:
        await state.clear()
        return Response(text=txt.AUTH_REQUIRED)

    data = await state.get_data()
    task_id = data.get("task_id", "")
    project_id = data.get("project_id", "")
    task_name = data.get("task_name", "")

    if not task_id or not project_id or not task_name:
        logger.error(
            "Invalid FSM state data in delete confirm: task_id=%r, project_id=%r, task_name=%r",
            task_id,
            project_id,
            task_name,
        )
        await state.clear()
        return Response(text=txt.DELETE_ERROR)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            await client.delete_task(task_id, project_id)
    except Exception:
        logger.exception("Failed to delete task")
        await state.clear()
        return Response(text=txt.DELETE_ERROR)

    await state.clear()
    return Response(text=txt.DELETE_SUCCESS.format(name=task_name))


async def handle_delete_reject(message: Message, state: FSMContext) -> Response:
    """Handle delete rejection (user said 'no')."""
    await state.clear()
    return Response(text=txt.DELETE_CANCELLED)


async def handle_add_subtask(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle add_subtask intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_add_subtask_slots(intent_data)

    if not slots.parent_name:
        return Response(text=txt.SUBTASK_PARENT_REQUIRED)

    if not slots.subtask_name:
        return Response(text=txt.SUBTASK_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.parent_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.parent_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.parent_name))

            best_match, match_idx = match_result
            parent_task = active_tasks[match_idx]

            payload = TaskCreate(
                title=slots.subtask_name,
                projectId=parent_task.project_id,
                parentId=parent_task.id,
            )
            await client.create_task(payload)

    except Exception:
        logger.exception("Failed to create subtask")
        return Response(text=txt.SUBTASK_ERROR)

    return Response(text=txt.SUBTASK_CREATED.format(name=slots.subtask_name, parent=best_match))


async def handle_list_subtasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle list_subtasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_list_subtasks_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.LIST_SUBTASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for subtask listing")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    parent_task = active_tasks[match_idx]

    subtasks = [t for t in all_tasks if t.parent_id == parent_task.id and t.status == 0]

    if not subtasks:
        return Response(text=txt.NO_SUBTASKS.format(name=best_match))

    count_str = txt.pluralize_tasks(len(subtasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(subtasks[:5])]
    task_list = "\n".join(lines)

    return Response(
        text=_truncate_response(
            txt.SUBTASKS_HEADER.format(name=best_match, count=count_str, tasks=task_list)
        )
    )


async def handle_add_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle add_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_add_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            # Build updated items list
            existing_items: list[dict[str, Any]] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "sortOrder": item.sort_order,
                }
                for item in matched_task.items
            ]
            new_item: dict[str, Any] = {"title": slots.item_name, "status": 0}
            updated_items = [*existing_items, new_item]

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)

    except Exception:
        logger.exception("Failed to add checklist item")
        return Response(text=txt.CHECKLIST_ITEM_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_ADDED.format(
            item=slots.item_name, task=best_match, count=len(updated_items)
        )
    )


async def handle_show_checklist(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle show_checklist intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_show_checklist_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.SHOW_CHECKLIST_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to fetch tasks for checklist")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    titles = [t.title for t in active_tasks]
    match_result = find_best_match(slots.task_name, titles)

    if match_result is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    best_match, match_idx = match_result
    matched_task = active_tasks[match_idx]

    if not matched_task.items:
        return Response(text=txt.CHECKLIST_EMPTY.format(name=best_match))

    lines: list[str] = []
    for i, item in enumerate(matched_task.items, 1):
        mark = "[x]" if item.status == 1 else "[ ]"
        lines.append(f"{i}. {mark} {item.title}")
    items_text = "\n".join(lines)

    return Response(
        text=_truncate_response(txt.CHECKLIST_HEADER.format(name=best_match, items=items_text))
    )


async def handle_check_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle check_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_check_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            matched_item_title, item_idx = item_match

            # Build updated items list with matched item checked
            updated_items: list[dict[str, Any]] = []
            for i, item in enumerate(matched_task.items):
                item_dict: dict[str, Any] = {
                    "id": item.id,
                    "title": item.title,
                    "status": 1 if i == item_idx else item.status,
                    "sortOrder": item.sort_order,
                }
                updated_items.append(item_dict)

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)

    except Exception:
        logger.exception("Failed to check item")
        return Response(text=txt.CHECKLIST_CHECK_ERROR)

    return Response(text=txt.CHECKLIST_ITEM_CHECKED.format(item=matched_item_title))


async def handle_delete_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    """Handle delete_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_delete_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)

            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=best_match)
                )

            matched_item_title, item_idx = item_match

            # Build updated items list without the matched item
            updated_items: list[dict[str, Any]] = [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status,
                    "sortOrder": item.sort_order,
                }
                for i, item in enumerate(matched_task.items)
                if i != item_idx
            ]

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                items=updated_items,
            )
            await client.update_task(payload)

    except Exception:
        logger.exception("Failed to delete checklist item")
        return Response(text=txt.CHECKLIST_ITEM_DELETE_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_DELETED.format(item=matched_item_title, task=best_match)
    )


async def handle_unknown(message: Message) -> Response:
    """Handle unrecognized commands."""
    return Response(text=txt.UNKNOWN)
