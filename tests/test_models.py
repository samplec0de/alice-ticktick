"""Tests for TickTick Pydantic models."""

from __future__ import annotations

from typing import Any

from alice_ticktick.ticktick.models import (
    ChecklistItem,
    Task,
    TaskCreate,
    TaskPriority,
    TaskUpdate,
)


class TestChecklistItem:
    def test_basic_item(self) -> None:
        item = ChecklistItem(title="Buy milk")
        assert item.title == "Buy milk"
        assert item.status == 0
        assert item.sort_order == 0
        assert item.id == ""

    def test_completed_item(self) -> None:
        item = ChecklistItem(id="abc123", title="Done item", status=1, sortOrder=3)
        assert item.id == "abc123"
        assert item.title == "Done item"
        assert item.status == 1
        assert item.sort_order == 3

    def test_from_api_response(self) -> None:
        data: dict[str, Any] = {
            "id": "item1",
            "title": "Check email",
            "status": 0,
            "sortOrder": 5,
        }
        item = ChecklistItem.model_validate(data)
        assert item.id == "item1"
        assert item.title == "Check email"
        assert item.sort_order == 5

    def test_populate_by_name(self) -> None:
        item = ChecklistItem(title="Test", sort_order=10)
        assert item.sort_order == 10


class TestTaskWithItems:
    def test_task_with_items(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Shopping",
            "items": [
                {"id": "i1", "title": "Milk", "status": 0, "sortOrder": 0},
                {"id": "i2", "title": "Bread", "status": 1, "sortOrder": 1},
            ],
        }
        task = Task.model_validate(data)
        assert len(task.items) == 2
        assert task.items[0].title == "Milk"
        assert task.items[0].status == 0
        assert task.items[1].title == "Bread"
        assert task.items[1].status == 1

    def test_task_without_items_defaults_empty(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Simple task",
        }
        task = Task.model_validate(data)
        assert task.items == []

    def test_task_with_parent_id(self) -> None:
        data: dict[str, Any] = {
            "id": "t2",
            "projectId": "p1",
            "title": "Subtask",
            "parentId": "t1",
        }
        task = Task.model_validate(data)
        assert task.parent_id == "t1"

    def test_task_without_parent_id_defaults_none(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Top-level task",
        }
        task = Task.model_validate(data)
        assert task.parent_id is None

    def test_task_with_items_and_parent_id(self) -> None:
        data: dict[str, Any] = {
            "id": "t3",
            "projectId": "p1",
            "title": "Sub with checklist",
            "parentId": "t1",
            "items": [{"id": "i1", "title": "Step 1", "status": 0, "sortOrder": 0}],
        }
        task = Task.model_validate(data)
        assert task.parent_id == "t1"
        assert len(task.items) == 1
        assert task.items[0].title == "Step 1"


class TestTaskCreateWithItems:
    def test_create_with_items(self) -> None:
        tc = TaskCreate(
            title="Shopping",
            items=[{"title": "Milk", "status": 0}],
        )
        assert tc.items is not None
        assert len(tc.items) == 1
        assert tc.items[0]["title"] == "Milk"

    def test_create_without_items(self) -> None:
        tc = TaskCreate(title="Simple")
        assert tc.items is None

    def test_create_with_parent_id(self) -> None:
        tc = TaskCreate(title="Subtask", parent_id="parent1")
        assert tc.parent_id == "parent1"

    def test_create_without_parent_id(self) -> None:
        tc = TaskCreate(title="Top-level")
        assert tc.parent_id is None

    def test_create_serialization_with_alias(self) -> None:
        tc = TaskCreate(title="Sub", parent_id="p1")
        data = tc.model_dump(by_alias=True, exclude_none=True)
        assert data["parentId"] == "p1"
        assert "parent_id" not in data


class TestTaskUpdateWithItems:
    def test_update_with_items(self) -> None:
        tu = TaskUpdate(
            id="t1",
            project_id="p1",
            items=[{"title": "Updated item", "status": 1}],
        )
        assert tu.items is not None
        assert len(tu.items) == 1
        assert tu.items[0]["title"] == "Updated item"

    def test_update_without_items(self) -> None:
        tu = TaskUpdate(id="t1", project_id="p1")
        assert tu.items is None

    def test_update_existing_fields_still_work(self) -> None:
        tu = TaskUpdate(
            id="t1",
            project_id="p1",
            title="New title",
            priority=TaskPriority.HIGH,
        )
        assert tu.title == "New title"
        assert tu.priority == TaskPriority.HIGH
        assert tu.items is None


class TestTaskRepeatAndReminders:
    def test_task_with_repeat_flag(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Daily standup",
            "repeatFlag": "RRULE:FREQ=DAILY",
        }
        task = Task.model_validate(data)
        assert task.repeat_flag == "RRULE:FREQ=DAILY"

    def test_task_without_repeat_flag(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Simple task",
        }
        task = Task.model_validate(data)
        assert task.repeat_flag is None

    def test_task_with_reminders(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Meeting",
            "reminders": ["TRIGGER:-PT30M", "TRIGGER:-PT1H"],
        }
        task = Task.model_validate(data)
        assert task.reminders == ["TRIGGER:-PT30M", "TRIGGER:-PT1H"]

    def test_task_without_reminders(self) -> None:
        data: dict[str, Any] = {
            "id": "t1",
            "projectId": "p1",
            "title": "Simple",
        }
        task = Task.model_validate(data)
        assert task.reminders == []


class TestTaskCreateRepeatAndReminders:
    def test_create_with_repeat_flag(self) -> None:
        tc = TaskCreate(title="Daily", repeat_flag="RRULE:FREQ=DAILY")
        data = tc.model_dump(by_alias=True, exclude_none=True)
        assert data["repeatFlag"] == "RRULE:FREQ=DAILY"
        assert "reminders" not in data

    def test_create_with_reminders(self) -> None:
        tc = TaskCreate(title="Meeting", reminders=["TRIGGER:-PT30M"])
        data = tc.model_dump(by_alias=True, exclude_none=True)
        assert data["reminders"] == ["TRIGGER:-PT30M"]

    def test_create_without_repeat_excludes_field(self) -> None:
        tc = TaskCreate(title="Simple")
        data = tc.model_dump(by_alias=True, exclude_none=True)
        assert "repeatFlag" not in data
        assert "reminders" not in data


class TestTaskUpdateRepeatAndReminders:
    def test_update_with_repeat_flag(self) -> None:
        tu = TaskUpdate(id="t1", project_id="p1", repeat_flag="RRULE:FREQ=WEEKLY")
        data = tu.model_dump(by_alias=True, exclude_none=True)
        assert data["repeatFlag"] == "RRULE:FREQ=WEEKLY"

    def test_update_remove_repeat_flag(self) -> None:
        """Empty string removes recurrence (exclude_none=True keeps it)."""
        tu = TaskUpdate(id="t1", project_id="p1", repeat_flag="")
        data = tu.model_dump(by_alias=True, exclude_none=True)
        assert data["repeatFlag"] == ""

    def test_update_with_reminders(self) -> None:
        tu = TaskUpdate(id="t1", project_id="p1", reminders=["TRIGGER:-PT1H"])
        data = tu.model_dump(by_alias=True, exclude_none=True)
        assert data["reminders"] == ["TRIGGER:-PT1H"]

    def test_update_remove_reminders(self) -> None:
        """Empty list removes reminders (exclude_none=True keeps it)."""
        tu = TaskUpdate(id="t1", project_id="p1", reminders=[])
        data = tu.model_dump(by_alias=True, exclude_none=True)
        assert data["reminders"] == []

    def test_update_none_repeat_excludes_field(self) -> None:
        tu = TaskUpdate(id="t1", project_id="p1")
        data = tu.model_dump(by_alias=True, exclude_none=True)
        assert "repeatFlag" not in data
        assert "reminders" not in data
