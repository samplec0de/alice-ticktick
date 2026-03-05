"""Subtask-related intent handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import extract_add_subtask_slots, extract_list_subtasks_slots
from alice_ticktick.dialogs.nlp import find_best_match
from alice_ticktick.ticktick.client import TickTickClient, TickTickUnauthorizedError
from alice_ticktick.ticktick.models import TaskCreate

from ._helpers import (
    _auth_required_response,
    _find_active_task,
    _format_task_line,
    _gather_all_tasks,
    _get_access_token,
    _invalidate_task_cache,
    _truncate_response,
)

if TYPE_CHECKING:
    from aliceio.types import Message

logger = logging.getLogger(__name__)


async def handle_add_subtask(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_subtask intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_subtask_slots(intent_data)

    if not slots.parent_name:
        return Response(text=txt.SUBTASK_PARENT_REQUIRED)

    if not slots.subtask_name:
        return Response(text=txt.SUBTASK_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.parent_name, access_token)
            if isinstance(result, Response):
                return result

            payload = TaskCreate(
                title=slots.subtask_name,
                projectId=result.task.project_id,
                parentId=result.task.id,
            )
            await client.create_task(payload)
            _invalidate_task_cache(access_token)

    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to create subtask")
        return Response(text=txt.SUBTASK_ERROR)

    return Response(text=txt.SUBTASK_CREATED.format(name=slots.subtask_name, parent=result.name))


async def handle_list_subtasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_subtasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_list_subtasks_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.LIST_SUBTASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
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
