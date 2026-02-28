"""Tests for intent slot extraction."""

from __future__ import annotations

from typing import Any

from alice_ticktick.dialogs.intents import (
    ALL_INTENTS,
    COMPLETE_TASK,
    CREATE_TASK,
    DELETE_TASK,
    EDIT_TASK,
    LIST_TASKS,
    OVERDUE_TASKS,
    SEARCH_TASK,
    extract_complete_task_slots,
    extract_create_task_slots,
    extract_delete_task_slots,
    extract_edit_task_slots,
    extract_list_tasks_slots,
    extract_search_task_slots,
)


class TestIntentConstants:
    def test_all_intents_contains_all(self) -> None:
        assert CREATE_TASK in ALL_INTENTS
        assert LIST_TASKS in ALL_INTENTS
        assert OVERDUE_TASKS in ALL_INTENTS
        assert COMPLETE_TASK in ALL_INTENTS
        assert SEARCH_TASK in ALL_INTENTS
        assert EDIT_TASK in ALL_INTENTS
        assert DELETE_TASK in ALL_INTENTS

    def test_all_intents_count(self) -> None:
        assert len(ALL_INTENTS) == 7


class TestCreateTaskSlots:
    def test_full_slots(self) -> None:
        data: dict[str, Any] = {
            "slots": {
                "task_name": {"type": "YANDEX.STRING", "value": "Купить молоко"},
                "date": {"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}},
                "priority": {"type": "YANDEX.STRING", "value": "высокий"},
            },
        }
        slots = extract_create_task_slots(data)
        assert slots.task_name == "Купить молоко"
        assert slots.date == {"day": 1, "day_is_relative": True}
        assert slots.priority == "высокий"

    def test_name_only(self) -> None:
        data: dict[str, Any] = {
            "slots": {"task_name": {"type": "YANDEX.STRING", "value": "Тест"}},
        }
        slots = extract_create_task_slots(data)
        assert slots.task_name == "Тест"
        assert slots.date is None
        assert slots.priority is None

    def test_empty_slots(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_create_task_slots(data)
        assert slots.task_name is None


class TestListTasksSlots:
    def test_with_date(self) -> None:
        data: dict[str, Any] = {
            "slots": {
                "date": {"type": "YANDEX.DATETIME", "value": {"day": 5, "month": 3}},
            },
        }
        slots = extract_list_tasks_slots(data)
        assert slots.date == {"day": 5, "month": 3}

    def test_no_date(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_list_tasks_slots(data)
        assert slots.date is None


class TestCompleteTaskSlots:
    def test_with_name(self) -> None:
        data: dict[str, Any] = {
            "slots": {"task_name": {"type": "YANDEX.STRING", "value": "купить молоко"}},
        }
        slots = extract_complete_task_slots(data)
        assert slots.task_name == "купить молоко"

    def test_no_name(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_complete_task_slots(data)
        assert slots.task_name is None


class TestSearchTaskSlots:
    def test_with_query(self) -> None:
        data: dict[str, Any] = {
            "slots": {"query": {"type": "YANDEX.STRING", "value": "купить"}},
        }
        slots = extract_search_task_slots(data)
        assert slots.query == "купить"

    def test_no_query(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_search_task_slots(data)
        assert slots.query is None


class TestEditTaskSlots:
    def test_full_slots(self) -> None:
        data: dict[str, Any] = {
            "slots": {
                "task_name": {"type": "YANDEX.STRING", "value": "купить молоко"},
                "new_date": {
                    "type": "YANDEX.DATETIME",
                    "value": {"day": 1, "day_is_relative": True},
                },
                "new_priority": {"type": "YANDEX.STRING", "value": "высокий"},
                "new_name": {"type": "YANDEX.STRING", "value": "купить кефир"},
            },
        }
        slots = extract_edit_task_slots(data)
        assert slots.task_name == "купить молоко"
        assert slots.new_date == {"day": 1, "day_is_relative": True}
        assert slots.new_priority == "высокий"
        assert slots.new_name == "купить кефир"

    def test_empty_slots(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_edit_task_slots(data)
        assert slots.task_name is None
        assert slots.new_date is None
        assert slots.new_priority is None
        assert slots.new_name is None


class TestDeleteTaskSlots:
    def test_with_name(self) -> None:
        data: dict[str, Any] = {
            "slots": {"task_name": {"type": "YANDEX.STRING", "value": "купить молоко"}},
        }
        slots = extract_delete_task_slots(data)
        assert slots.task_name == "купить молоко"

    def test_no_name(self) -> None:
        data: dict[str, Any] = {"slots": {}}
        slots = extract_delete_task_slots(data)
        assert slots.task_name is None
