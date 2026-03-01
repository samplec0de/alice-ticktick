"""Tests for Phase 3 handlers: subtasks and checklists."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    handle_add_checklist_item,
    handle_add_subtask,
    handle_check_item,
    handle_delete_checklist_item,
    handle_list_subtasks,
    handle_show_checklist,
)
from alice_ticktick.ticktick.models import ChecklistItem, Project, Task

# --- Helpers ---


def _make_message(
    *,
    access_token: str | None = "test-token",
) -> MagicMock:
    """Create a mock Message object."""
    message = MagicMock()
    message.command = ""
    message.original_utterance = ""
    message.session.new = False
    message.session.session_id = "test-session-id"
    message.session.skill_id = "test-skill-id"

    if access_token is not None:
        message.user = MagicMock()
        message.user.access_token = access_token
    else:
        message.user = None

    return message


def _make_task(
    *,
    task_id: str = "task-1",
    title: str = "Test task",
    project_id: str = "proj-1",
    priority: int = 0,
    status: int = 0,
    items: list[ChecklistItem] | None = None,
    parent_id: str | None = None,
) -> Task:
    """Create a Task instance."""
    return Task(
        id=task_id,
        title=title,
        projectId=project_id,
        priority=priority,
        status=status,
        items=items or [],
        parentId=parent_id,
    )


def _make_project(*, project_id: str = "proj-1", name: str = "Inbox") -> Project:
    """Create a Project instance."""
    return Project(id=project_id, name=name)


def _make_mock_client(
    projects: list[Project] | None = None,
    tasks: list[Task] | None = None,
) -> type:
    """Create a mock TickTickClient factory class."""
    if projects is None:
        projects = [_make_project()]
    if tasks is None:
        tasks = []

    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(return_value=tasks)
    client.get_inbox_tasks = AsyncMock(return_value=[])
    client.create_task = AsyncMock(return_value=tasks[0] if tasks else _make_task())
    client.complete_task = AsyncMock(return_value=None)
    client.update_task = AsyncMock(return_value=tasks[0] if tasks else _make_task())
    client.delete_task = AsyncMock(return_value=None)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)

    return factory


def _intent_data(**slots: Any) -> dict[str, Any]:
    """Build intent_data dict from keyword args."""
    return {"slots": {k: {"value": v} for k, v in slots.items()}}


# =============================================================================
# handle_add_subtask
# =============================================================================


class TestAddSubtask:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_add_subtask(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_parent_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(subtask_name="Подзадача")
        response = await handle_add_subtask(message, data, None)
        assert response.text == txt.SUBTASK_PARENT_REQUIRED

    async def test_subtask_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(parent_name="Родитель")
        response = await handle_add_subtask(message, data, None)
        assert response.text == txt.SUBTASK_NAME_REQUIRED

    async def test_parent_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая задача")]
        message = _make_message()
        data = _intent_data(subtask_name="Подзадача", parent_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_subtask(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_no_active_tasks(self) -> None:
        tasks = [_make_task(title="Done", status=2)]
        message = _make_message()
        data = _intent_data(subtask_name="Подзадача", parent_name="Done")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_subtask(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_success(self) -> None:
        parent = _make_task(task_id="p1", title="Купить продукты", project_id="proj-1")
        tasks = [parent]
        message = _make_message()
        data = _intent_data(subtask_name="Купить молоко", parent_name="купить продукты")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_subtask(message, data, mock_factory)
        assert "Купить молоко" in response.text
        assert "Купить продукты" in response.text

        client = mock_factory.return_value.__aenter__.return_value
        call_args = client.create_task.call_args[0][0]
        assert call_args.title == "Купить молоко"
        assert call_args.parent_id == "p1"
        assert call_args.project_id == "proj-1"

    async def test_api_error_on_fetch(self) -> None:
        message = _make_message()
        data = _intent_data(subtask_name="Подзадача", parent_name="Родитель")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_add_subtask(message, data, mock_factory)
        assert response.text == txt.SUBTASK_ERROR

    async def test_api_error_on_create(self) -> None:
        tasks = [_make_task(title="Родитель")]
        message = _make_message()
        data = _intent_data(subtask_name="Подзадача", parent_name="родитель")
        mock_factory = _make_mock_client(tasks=tasks)
        client = mock_factory.return_value.__aenter__.return_value
        client.create_task = AsyncMock(side_effect=Exception("API error"))
        response = await handle_add_subtask(message, data, mock_factory)
        assert response.text == txt.SUBTASK_ERROR


# =============================================================================
# handle_list_subtasks
# =============================================================================


class TestListSubtasks:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_list_subtasks(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_task_name_required(self) -> None:
        message = _make_message()
        response = await handle_list_subtasks(message, _intent_data(), None)
        assert response.text == txt.LIST_SUBTASKS_NAME_REQUIRED

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая")]
        message = _make_message()
        data = _intent_data(task_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_list_subtasks(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_no_subtasks(self) -> None:
        parent = _make_task(task_id="p1", title="Купить продукты")
        tasks = [parent]
        message = _make_message()
        data = _intent_data(task_name="купить продукты")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_list_subtasks(message, data, mock_factory)
        assert "нет подзадач" in response.text

    async def test_success(self) -> None:
        parent = _make_task(task_id="p1", title="Купить продукты", project_id="proj-1")
        sub1 = _make_task(task_id="s1", title="Молоко", project_id="proj-1", parent_id="p1")
        sub2 = _make_task(task_id="s2", title="Хлеб", project_id="proj-1", parent_id="p1")
        tasks = [parent, sub1, sub2]
        message = _make_message()
        data = _intent_data(task_name="купить продукты")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_list_subtasks(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "Хлеб" in response.text
        assert "Купить продукты" in response.text

    async def test_only_active_subtasks(self) -> None:
        """Completed subtasks should be excluded."""
        parent = _make_task(task_id="p1", title="Купить продукты")
        sub_done = _make_task(task_id="s1", title="Молоко", parent_id="p1", status=2)
        sub_active = _make_task(task_id="s2", title="Хлеб", parent_id="p1", status=0)
        tasks = [parent, sub_done, sub_active]
        message = _make_message()
        data = _intent_data(task_name="купить продукты")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_list_subtasks(message, data, mock_factory)
        assert "Хлеб" in response.text
        assert "Молоко" not in response.text

    async def test_api_error(self) -> None:
        message = _make_message()
        data = _intent_data(task_name="тест")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_list_subtasks(message, data, mock_factory)
        assert response.text == txt.API_ERROR


# =============================================================================
# handle_add_checklist_item
# =============================================================================


class TestAddChecklistItem:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_add_checklist_item(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_task_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко")
        response = await handle_add_checklist_item(message, data, None)
        assert response.text == txt.CHECKLIST_TASK_REQUIRED

    async def test_item_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(task_name="Список покупок")
        response = await handle_add_checklist_item(message, data, None)
        assert response.text == txt.CHECKLIST_ITEM_REQUIRED

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая")]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_checklist_item(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_success_empty_checklist(self) -> None:
        task = _make_task(task_id="t1", title="Список покупок", items=[])
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_checklist_item(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "Список покупок" in response.text
        assert "1" in response.text  # count

        client = mock_factory.return_value.__aenter__.return_value
        call_args = client.update_task.call_args[0][0]
        assert call_args.items is not None
        assert len(call_args.items) == 1
        assert call_args.items[0]["title"] == "Молоко"

    async def test_success_existing_items(self) -> None:
        existing_item = ChecklistItem(id="ci1", title="Хлеб", status=0)
        task = _make_task(task_id="t1", title="Список покупок", items=[existing_item])
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_add_checklist_item(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "2" in response.text  # count (1 existing + 1 new)

        client = mock_factory.return_value.__aenter__.return_value
        call_args = client.update_task.call_args[0][0]
        assert call_args.items is not None
        assert len(call_args.items) == 2

    async def test_api_error_on_fetch(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="Список")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_add_checklist_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_ITEM_ERROR

    async def test_api_error_on_update(self) -> None:
        task = _make_task(title="Список покупок")
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        client = mock_factory.return_value.__aenter__.return_value
        client.update_task = AsyncMock(side_effect=Exception("API error"))
        response = await handle_add_checklist_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_ITEM_ERROR


# =============================================================================
# handle_show_checklist
# =============================================================================


class TestShowChecklist:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_show_checklist(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_task_name_required(self) -> None:
        message = _make_message()
        response = await handle_show_checklist(message, _intent_data(), None)
        assert response.text == txt.SHOW_CHECKLIST_NAME_REQUIRED

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая")]
        message = _make_message()
        data = _intent_data(task_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_show_checklist(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_empty_checklist(self) -> None:
        task = _make_task(task_id="t1", title="Список покупок", items=[])
        tasks = [task]
        message = _make_message()
        data = _intent_data(task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_show_checklist(message, data, mock_factory)
        assert "пуст" in response.text

    async def test_success_with_items(self) -> None:
        items = [
            ChecklistItem(id="ci1", title="Молоко", status=0),
            ChecklistItem(id="ci2", title="Хлеб", status=1),
            ChecklistItem(id="ci3", title="Яйца", status=0),
        ]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_show_checklist(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "Хлеб" in response.text
        assert "Яйца" in response.text
        assert "Список покупок" in response.text

    async def test_api_error(self) -> None:
        message = _make_message()
        data = _intent_data(task_name="тест")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_show_checklist(message, data, mock_factory)
        assert response.text == txt.API_ERROR


# =============================================================================
# handle_check_item
# =============================================================================


class TestCheckItem:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_check_item(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_task_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко")
        response = await handle_check_item(message, data, None)
        assert response.text == txt.CHECKLIST_TASK_REQUIRED

    async def test_item_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(task_name="Список покупок")
        response = await handle_check_item(message, data, None)
        assert response.text == txt.CHECKLIST_ITEM_REQUIRED

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая")]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_check_item(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_empty_checklist_item_not_found(self) -> None:
        task = _make_task(task_id="t1", title="Список покупок", items=[])
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_check_item(message, data, mock_factory)
        assert "не найден" in response.text

    async def test_item_not_found_by_fuzzy(self) -> None:
        items = [ChecklistItem(id="ci1", title="Хлеб", status=0)]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="xxxxxx", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_check_item(message, data, mock_factory)
        assert "не найден" in response.text

    async def test_success(self) -> None:
        items = [
            ChecklistItem(id="ci1", title="Молоко", status=0),
            ChecklistItem(id="ci2", title="Хлеб", status=0),
        ]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_check_item(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "выполненным" in response.text

        client = mock_factory.return_value.__aenter__.return_value
        call_args = client.update_task.call_args[0][0]
        assert call_args.items is not None
        # Verify the matched item has status=1
        matched = [i for i in call_args.items if i["title"] == "Молоко"]
        assert matched[0]["status"] == 1
        # Verify the other item is unchanged
        other = [i for i in call_args.items if i["title"] == "Хлеб"]
        assert other[0]["status"] == 0

    async def test_api_error_on_fetch(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="Список")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_check_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_CHECK_ERROR

    async def test_api_error_on_update(self) -> None:
        items = [ChecklistItem(id="ci1", title="Молоко", status=0)]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        client = mock_factory.return_value.__aenter__.return_value
        client.update_task = AsyncMock(side_effect=Exception("API error"))
        response = await handle_check_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_CHECK_ERROR


# =============================================================================
# handle_delete_checklist_item
# =============================================================================


class TestDeleteChecklistItem:
    async def test_auth_required(self) -> None:
        message = _make_message(access_token=None)
        response = await handle_delete_checklist_item(message, _intent_data(), None)
        assert response.text == txt.AUTH_REQUIRED

    async def test_task_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко")
        response = await handle_delete_checklist_item(message, data, None)
        assert response.text == txt.CHECKLIST_TASK_REQUIRED

    async def test_item_name_required(self) -> None:
        message = _make_message()
        data = _intent_data(task_name="Список покупок")
        response = await handle_delete_checklist_item(message, data, None)
        assert response.text == txt.CHECKLIST_ITEM_REQUIRED

    async def test_task_not_found(self) -> None:
        tasks = [_make_task(title="Совсем другая")]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="xxxxxx")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert "не найдена" in response.text

    async def test_empty_checklist_item_not_found(self) -> None:
        task = _make_task(task_id="t1", title="Список покупок", items=[])
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert "не найден" in response.text

    async def test_item_not_found_by_fuzzy(self) -> None:
        items = [ChecklistItem(id="ci1", title="Хлеб", status=0)]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="xxxxxx", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert "не найден" in response.text

    async def test_success(self) -> None:
        items = [
            ChecklistItem(id="ci1", title="Молоко", status=0),
            ChecklistItem(id="ci2", title="Хлеб", status=0),
        ]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert "Молоко" in response.text
        assert "Список покупок" in response.text

        client = mock_factory.return_value.__aenter__.return_value
        call_args = client.update_task.call_args[0][0]
        assert call_args.items is not None
        # Verify only "Хлеб" remains
        assert len(call_args.items) == 1
        assert call_args.items[0]["title"] == "Хлеб"

    async def test_api_error_on_fetch(self) -> None:
        message = _make_message()
        data = _intent_data(item_name="Молоко", task_name="Список")
        mock_factory = _make_mock_client()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("API error"),
        )
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_ITEM_DELETE_ERROR

    async def test_api_error_on_update(self) -> None:
        items = [ChecklistItem(id="ci1", title="Молоко", status=0)]
        task = _make_task(task_id="t1", title="Список покупок", items=items)
        tasks = [task]
        message = _make_message()
        data = _intent_data(item_name="молоко", task_name="список покупок")
        mock_factory = _make_mock_client(tasks=tasks)
        client = mock_factory.return_value.__aenter__.return_value
        client.update_task = AsyncMock(side_effect=Exception("API error"))
        response = await handle_delete_checklist_item(message, data, mock_factory)
        assert response.text == txt.CHECKLIST_ITEM_DELETE_ERROR
