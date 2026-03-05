"""Checklist-related intent handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aliceio.types import Response, Update

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.intents import (
    extract_add_checklist_item_slots,
    extract_check_item_slots,
    extract_delete_checklist_item_slots,
    extract_show_checklist_slots,
)
from alice_ticktick.dialogs.nlp import find_best_match
from alice_ticktick.ticktick.client import TickTickClient, TickTickUnauthorizedError
from alice_ticktick.ticktick.models import TaskUpdate

from ._helpers import (
    _auth_required_response,
    _find_active_task,
    _get_access_token,
    _invalidate_task_cache,
    _truncate_response,
)

if TYPE_CHECKING:
    from aliceio.types import Message

logger = logging.getLogger(__name__)


async def handle_add_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
            if isinstance(result, Response):
                return result

            matched_task = result.task

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
            _invalidate_task_cache(access_token)

    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to add checklist item")
        return Response(text=txt.CHECKLIST_ITEM_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_ADDED.format(
            item=slots.item_name, task=result.name, count=len(updated_items)
        )
    )


async def handle_show_checklist(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle show_checklist intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_show_checklist_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.SHOW_CHECKLIST_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to fetch tasks for checklist")
        return Response(text=txt.API_ERROR)

    if isinstance(result, Response):
        return result

    if not result.task.items:
        return Response(text=txt.CHECKLIST_EMPTY.format(name=result.name))

    lines: list[str] = []
    for i, item in enumerate(result.task.items, 1):
        mark = "[x]" if item.status == 1 else "[ ]"
        lines.append(f"{i}. {mark} {item.title}")
    items_text = "\n".join(lines)

    return Response(
        text=_truncate_response(txt.CHECKLIST_HEADER.format(name=result.name, items=items_text))
    )


async def handle_check_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle check_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_check_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
            if isinstance(result, Response):
                return result

            matched_task = result.task

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(
                        item=slots.item_name, task=result.name
                    )
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(
                        item=slots.item_name, task=result.name
                    )
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
            _invalidate_task_cache(access_token)

    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to check item")
        return Response(text=txt.CHECKLIST_CHECK_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_CHECKED.format(item=matched_item_title, task=result.name)
    )


async def handle_delete_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle delete_checklist_item intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_delete_checklist_item_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)

    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            result = await _find_active_task(client, slots.task_name, access_token)
            if isinstance(result, Response):
                return result

            matched_task = result.task

            if not matched_task.items:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(
                        item=slots.item_name, task=result.name
                    )
                )

            item_titles = [item.title for item in matched_task.items]
            item_match = find_best_match(slots.item_name, item_titles)

            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(
                        item=slots.item_name, task=result.name
                    )
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
            _invalidate_task_cache(access_token)

    except TickTickUnauthorizedError:
        return _auth_required_response(event_update)
    except Exception:
        logger.exception("Failed to delete checklist item")
        return Response(text=txt.CHECKLIST_ITEM_DELETE_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_DELETED.format(item=matched_item_title, task=result.name)
    )
