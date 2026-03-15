"""Briefing intent handlers (morning/evening)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.ticktick.client import TickTickClient, TickTickUnauthorizedError

from ._helpers import (
    MAX_BRIEFING_TASKS,
    _apply_task_filters,
    _auth_required_response,
    _format_task_line,
    _gather_all_tasks,
    _get_access_token,
    _get_user_tz,
    _to_user_date,
    _truncate_response,
)

if TYPE_CHECKING:
    from aliceio.types import Message

    from alice_ticktick.ticktick.models import Task

logger = logging.getLogger(__name__)


def _build_morning_briefing_text(
    today_tasks: list[Task],
    overdue_tasks: list[Task],
) -> str:
    """Build morning briefing text from today's and overdue tasks."""
    overdue_count = len(overdue_tasks)

    if not today_tasks:
        if overdue_count:
            return txt.MORNING_BRIEFING_NO_TASKS_OVERDUE.format(
                overdue_count=txt.pluralize_tasks(overdue_count)
            )
        return txt.MORNING_BRIEFING_NO_TASKS

    count_str = txt.pluralize_tasks(len(today_tasks))
    shown = today_tasks[:MAX_BRIEFING_TASKS]
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(shown)]
    task_list = "\n".join(lines)
    if len(today_tasks) > MAX_BRIEFING_TASKS:
        remaining = len(today_tasks) - MAX_BRIEFING_TASKS
        task_list += "\n" + txt.BRIEFING_MORE_TASKS.format(count=remaining)

    if overdue_count:
        return txt.MORNING_BRIEFING_TASKS_OVERDUE.format(
            count=count_str,
            tasks=task_list,
            overdue_count=txt.pluralize_tasks(overdue_count),
        )
    return txt.MORNING_BRIEFING_TASKS.format(count=count_str, tasks=task_list)


def _build_evening_briefing_text(
    tomorrow_tasks: list[Task],
    overdue_tasks: list[Task],
) -> str:
    """Build evening briefing text from tomorrow's tasks and overdue count."""
    overdue_count = len(overdue_tasks)

    if not tomorrow_tasks:
        if overdue_count:
            return txt.EVENING_BRIEFING_NO_TASKS_OVERDUE.format(
                overdue_count=txt.pluralize_tasks(overdue_count)
            )
        return txt.EVENING_BRIEFING_NO_TASKS

    count_str = txt.pluralize_tasks(len(tomorrow_tasks))
    shown = tomorrow_tasks[:MAX_BRIEFING_TASKS]
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(shown)]
    task_list = "\n".join(lines)
    if len(tomorrow_tasks) > MAX_BRIEFING_TASKS:
        remaining = len(tomorrow_tasks) - MAX_BRIEFING_TASKS
        task_list += "\n" + txt.BRIEFING_MORE_TASKS.format(count=remaining)

    if overdue_count:
        return txt.EVENING_BRIEFING_TASKS_OVERDUE.format(
            count=count_str,
            tasks=task_list,
            overdue_count=txt.pluralize_tasks(overdue_count),
        )
    return txt.EVENING_BRIEFING_TASKS.format(count=count_str, tasks=task_list)


async def handle_morning_briefing(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle morning briefing intent -- show today's tasks and overdue count."""
    access_token = _get_access_token(message)
    if not access_token:
        return _auth_required_response(event_update)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception as exc:
        logger.exception("Failed to fetch tasks for morning briefing")
        return Response(text=txt.api_error_detail(exc))

    user_tz = _get_user_tz(event_update)
    today = datetime.datetime.now(tz=user_tz).date()

    today_tasks = _apply_task_filters(all_tasks, date_filter=today, user_tz=user_tz)
    overdue_tasks = [
        t
        for t in all_tasks
        if t.status == 0 and t.due_date is not None and _to_user_date(t.due_date, user_tz) < today
    ]

    text = _build_morning_briefing_text(today_tasks=today_tasks, overdue_tasks=overdue_tasks)
    return Response(text=_truncate_response(text))


async def handle_evening_briefing(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle evening briefing intent -- show tomorrow's tasks."""
    access_token = _get_access_token(message)
    if not access_token:
        return _auth_required_response(event_update)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception as exc:
        logger.exception("Failed to fetch tasks for evening briefing")
        return Response(text=txt.api_error_detail(exc))

    user_tz = _get_user_tz(event_update)
    now_date = datetime.datetime.now(tz=user_tz).date()
    tomorrow = now_date + datetime.timedelta(days=1)

    tomorrow_tasks = _apply_task_filters(all_tasks, date_filter=tomorrow, user_tz=user_tz)
    overdue_tasks = [
        t
        for t in all_tasks
        if t.status == 0
        and t.due_date is not None
        and _to_user_date(t.due_date, user_tz) < now_date
    ]

    text = _build_evening_briefing_text(tomorrow_tasks=tomorrow_tasks, overdue_tasks=overdue_tasks)
    return Response(text=_truncate_response(text))
