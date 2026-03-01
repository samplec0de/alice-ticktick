"""Intent IDs and slot extraction for Yandex Dialogs NLU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from alice_ticktick.dialogs.nlp.date_parser import YandexDateTime

# Intent IDs configured in Yandex Dialogs console
CREATE_TASK = "create_task"
LIST_TASKS = "list_tasks"
OVERDUE_TASKS = "overdue_tasks"
COMPLETE_TASK = "complete_task"
SEARCH_TASK = "search_task"
EDIT_TASK = "edit_task"
DELETE_TASK = "delete_task"
ADD_SUBTASK = "add_subtask"
LIST_SUBTASKS = "list_subtasks"
ADD_CHECKLIST_ITEM = "add_checklist_item"
SHOW_CHECKLIST = "show_checklist"
CHECK_ITEM = "check_item"
DELETE_CHECKLIST_ITEM = "delete_checklist_item"

ALL_INTENTS = frozenset(
    {
        CREATE_TASK,
        LIST_TASKS,
        OVERDUE_TASKS,
        COMPLETE_TASK,
        SEARCH_TASK,
        EDIT_TASK,
        DELETE_TASK,
        ADD_SUBTASK,
        LIST_SUBTASKS,
        ADD_CHECKLIST_ITEM,
        SHOW_CHECKLIST,
        CHECK_ITEM,
        DELETE_CHECKLIST_ITEM,
    }
)


@dataclass(frozen=True, slots=True)
class CreateTaskSlots:
    """Extracted slots for create_task intent."""

    task_name: str | None = None
    date: YandexDateTime | None = None
    priority: str | None = None


@dataclass(frozen=True, slots=True)
class ListTasksSlots:
    """Extracted slots for list_tasks intent."""

    date: YandexDateTime | None = None


@dataclass(frozen=True, slots=True)
class CompleteTaskSlots:
    """Extracted slots for complete_task intent."""

    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class SearchTaskSlots:
    """Extracted slots for search_task intent."""

    query: str | None = None


@dataclass(frozen=True, slots=True)
class EditTaskSlots:
    """Extracted slots for edit_task intent."""

    task_name: str | None = None
    new_date: YandexDateTime | None = None
    new_priority: str | None = None
    new_name: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteTaskSlots:
    """Extracted slots for delete_task intent."""

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


def extract_search_task_slots(intent_data: dict[str, Any]) -> SearchTaskSlots:
    """Extract slots from search_task intent."""
    return SearchTaskSlots(
        query=_get_slot_value(intent_data, "query"),
    )


def extract_edit_task_slots(intent_data: dict[str, Any]) -> EditTaskSlots:
    """Extract slots from edit_task intent."""
    return EditTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        new_date=_get_slot_value(intent_data, "new_date"),
        new_priority=_get_slot_value(intent_data, "new_priority"),
        new_name=_get_slot_value(intent_data, "new_name"),
    )


def extract_delete_task_slots(intent_data: dict[str, Any]) -> DeleteTaskSlots:
    """Extract slots from delete_task intent."""
    return DeleteTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
    )


@dataclass(frozen=True, slots=True)
class AddSubtaskSlots:
    """Extracted slots for add_subtask intent."""

    subtask_name: str | None = None
    parent_name: str | None = None


@dataclass(frozen=True, slots=True)
class ListSubtasksSlots:
    """Extracted slots for list_subtasks intent."""

    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class AddChecklistItemSlots:
    """Extracted slots for add_checklist_item intent."""

    item_name: str | None = None
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class ShowChecklistSlots:
    """Extracted slots for show_checklist intent."""

    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class CheckItemSlots:
    """Extracted slots for check_item intent."""

    item_name: str | None = None
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteChecklistItemSlots:
    """Extracted slots for delete_checklist_item intent."""

    item_name: str | None = None
    task_name: str | None = None


def extract_add_subtask_slots(intent_data: dict[str, Any]) -> AddSubtaskSlots:
    """Extract slots from add_subtask intent."""
    return AddSubtaskSlots(
        subtask_name=_get_slot_value(intent_data, "subtask_name"),
        parent_name=_get_slot_value(intent_data, "parent_name"),
    )


def extract_list_subtasks_slots(intent_data: dict[str, Any]) -> ListSubtasksSlots:
    """Extract slots from list_subtasks intent."""
    return ListSubtasksSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_add_checklist_item_slots(
    intent_data: dict[str, Any],
) -> AddChecklistItemSlots:
    """Extract slots from add_checklist_item intent."""
    return AddChecklistItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_show_checklist_slots(intent_data: dict[str, Any]) -> ShowChecklistSlots:
    """Extract slots from show_checklist intent."""
    return ShowChecklistSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_check_item_slots(intent_data: dict[str, Any]) -> CheckItemSlots:
    """Extract slots from check_item intent."""
    return CheckItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_delete_checklist_item_slots(
    intent_data: dict[str, Any],
) -> DeleteChecklistItemSlots:
    """Extract slots from delete_checklist_item intent."""
    return DeleteChecklistItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )
