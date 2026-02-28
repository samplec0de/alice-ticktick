"""Intent IDs and slot extraction for Yandex Dialogs NLU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Intent IDs configured in Yandex Dialogs console
CREATE_TASK = "create_task"
LIST_TASKS = "list_tasks"
OVERDUE_TASKS = "overdue_tasks"
COMPLETE_TASK = "complete_task"

ALL_INTENTS = frozenset({CREATE_TASK, LIST_TASKS, OVERDUE_TASKS, COMPLETE_TASK})


@dataclass(frozen=True, slots=True)
class CreateTaskSlots:
    """Extracted slots for create_task intent."""

    task_name: str | None = None
    date: dict[str, Any] | None = None
    priority: str | None = None


@dataclass(frozen=True, slots=True)
class ListTasksSlots:
    """Extracted slots for list_tasks intent."""

    date: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CompleteTaskSlots:
    """Extracted slots for complete_task intent."""

    task_name: str | None = None


def _get_slot_value(intent_data: dict[str, Any], slot_name: str) -> Any:
    """Extract a slot value from intent data."""
    slots = intent_data.get("slots", {})
    slot = slots.get(slot_name, {})
    return slot.get("value")


def extract_create_task_slots(intent_data: dict[str, Any]) -> CreateTaskSlots:
    """Extract slots from create_task intent."""
    return CreateTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        date=_get_slot_value(intent_data, "date"),
        priority=_get_slot_value(intent_data, "priority"),
    )


def extract_list_tasks_slots(intent_data: dict[str, Any]) -> ListTasksSlots:
    """Extract slots from list_tasks intent."""
    return ListTasksSlots(
        date=_get_slot_value(intent_data, "date"),
    )


def extract_complete_task_slots(intent_data: dict[str, Any]) -> CompleteTaskSlots:
    """Extract slots from complete_task intent."""
    return CompleteTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
    )
