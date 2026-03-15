"""Project-related intent handlers."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.nlp import parse_date_range, parse_priority, parse_yandex_datetime
from alice_ticktick.ticktick.client import TickTickClient, TickTickUnauthorizedError

from ._helpers import (
    _apply_task_filters,
    _auth_required_response,
    _find_project_by_name,
    _format_date,
    _format_priority_label,
    _format_priority_short,
    _get_access_token,
    _get_user_tz,
    _invalidate_task_cache,
    _truncate_response,
)

if TYPE_CHECKING:
    from aliceio.types import Message

    from alice_ticktick.dialogs.nlp import DateRange

logger = logging.getLogger(__name__)


async def handle_list_projects(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_projects intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            projects = await client.get_projects()
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception as exc:
        logger.exception("Failed to list projects")
        return Response(text=txt.api_error_detail(exc))

    projects = [p for p in projects if not p.closed]

    if not projects:
        return Response(text=txt.NO_PROJECTS)

    lines = [f"{i + 1}. {p.name}" for i, p in enumerate(projects)]
    n = len(projects)
    if n % 10 == 1 and n % 100 != 11:
        count_str = f"{n} проект"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        count_str = f"{n} проекта"
    else:
        count_str = f"{n} проектов"
    full_text = txt.PROJECTS_LIST.format(count=count_str, projects="\n".join(lines))
    return Response(text=_truncate_response(full_text))


async def handle_project_tasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle project_tasks intent -- show tasks from a specific project."""
    from alice_ticktick.dialogs.intents import extract_project_tasks_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_project_tasks_slots(intent_data)
    if not slots.project_name:
        return Response(text=txt.PROJECT_TASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            projects = await client.get_projects()
            project = _find_project_by_name(projects, slots.project_name)
            if project is None:
                names = ", ".join(p.name for p in projects) if projects else "\u2014"
                return Response(
                    text=txt.PROJECT_NOT_FOUND.format(name=slots.project_name, projects=names)
                )
            tasks = await client.get_tasks(project.id)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception as exc:
        logger.exception("Failed to get project tasks")
        return Response(text=txt.api_error_detail(exc))

    user_tz = _get_user_tz(event_update)

    # Build date filter
    date_filter: datetime.date | DateRange | None = None
    if slots.date_range:
        date_filter = parse_date_range(
            slots.date_range,
            now=datetime.datetime.now(tz=user_tz).date(),
            tz=user_tz,
        )
    elif slots.date:
        now_local = datetime.datetime.now(tz=user_tz)
        try:
            parsed = parse_yandex_datetime(slots.date, now=now_local)
            date_filter = parsed.date() if isinstance(parsed, datetime.datetime) else parsed
        except ValueError:
            pass

    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = (
        txt.format_priority_instrumental(_format_priority_label(priority_filter))
        if priority_filter is not None
        else None
    )

    active = _apply_task_filters(
        tasks,
        date_filter=date_filter,
        priority_filter=priority_filter,
        user_tz=user_tz,
    )
    if not active:
        if priority_label:
            return Response(
                text=txt.PROJECT_NO_TASKS_WITH_PRIORITY.format(
                    project=project.name, priority=priority_label
                )
            )
        return Response(text=txt.PROJECT_NO_TASKS.format(project=project.name))

    count = txt.pluralize_tasks(len(active))
    lines: list[str] = []
    for i, task in enumerate(active[:10]):
        line = f"{i + 1}. {task.title}"
        parts: list[str] = []
        if task.due_date:
            parts.append(_format_date(task.due_date, user_tz))
        prio = _format_priority_short(task.priority)
        if prio:
            parts.append(prio)
        if parts:
            line += f" — {', '.join(parts)}"
        lines.append(line)

    if priority_label:
        text = txt.PROJECT_TASKS_WITH_PRIORITY.format(
            project=project.name, priority=priority_label, count=count, tasks="\n".join(lines)
        )
    else:
        text = txt.PROJECT_TASKS_HEADER.format(
            project=project.name, count=count, tasks="\n".join(lines)
        )
    return Response(text=_truncate_response(text))


async def handle_create_project(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_project intent."""
    from alice_ticktick.dialogs.intents import extract_create_project_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_create_project_slots(intent_data)
    if not slots.project_name:
        return Response(text=txt.PROJECT_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            await client.create_project(slots.project_name)
            _invalidate_task_cache(access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to create project")
        return Response(text=txt.PROJECT_CREATE_ERROR)

    return Response(text=txt.PROJECT_CREATED.format(name=slots.project_name))
