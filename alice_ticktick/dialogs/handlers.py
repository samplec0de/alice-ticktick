"""Intent handlers for Alice skill."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from aliceio.types import Message, Response

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import (
    extract_complete_task_slots,
    extract_create_task_slots,
    extract_list_tasks_slots,
)
from alice_ticktick.dialogs.nlp import find_best_match, parse_priority, parse_yandex_datetime
from alice_ticktick.ticktick.client import TickTickClient
from alice_ticktick.ticktick.models import Task, TaskCreate, TaskPriority

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
            best_match = find_best_match(slots.task_name, titles)

            if best_match is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            matched_task = next((t for t in active_tasks if t.title == best_match), None)
            if matched_task is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            await client.complete_task(matched_task.id, matched_task.project_id)

    except Exception:
        logger.exception("Failed to complete task")
        return Response(text=txt.COMPLETE_ERROR)

    return Response(text=txt.TASK_COMPLETED.format(name=best_match))


async def handle_unknown(message: Message) -> Response:
    """Handle unrecognized commands."""
    return Response(text=txt.UNKNOWN)
