"""Tests for intent slot extraction."""

from __future__ import annotations

from typing import Any

from alice_ticktick.dialogs.intents import (
    ALL_INTENTS,
    COMPLETE_TASK,
    CREATE_TASK,
    LIST_TASKS,
    OVERDUE_TASKS,
    extract_complete_task_slots,
    extract_create_task_slots,
    extract_list_tasks_slots,
)


class TestIntentConstants:
    def test_all_intents_contains_all(self) -> None:
        assert CREATE_TASK in ALL_INTENTS
        assert LIST_TASKS in ALL_INTENTS
        assert OVERDUE_TASKS in ALL_INTENTS
        assert COMPLETE_TASK in ALL_INTENTS

    def test_all_intents_count(self) -> None:
        assert len(ALL_INTENTS) == 4


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
