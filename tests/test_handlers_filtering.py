"""Tests for _apply_task_filters utility."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs.handlers import _apply_task_filters
from alice_ticktick.dialogs.nlp.date_parser import DateRange
from alice_ticktick.ticktick.models import Task, TaskPriority

UTC = ZoneInfo("UTC")


def _make_task(
    *,
    task_id: str = "t1",
    title: str = "Test",
    due_date: datetime.datetime | None = None,
    priority: TaskPriority = TaskPriority.NONE,
    status: int = 0,
) -> Task:
    return Task(
        id=task_id,
        projectId="proj-1",
        title=title,
        priority=priority,
        status=status,
        dueDate=due_date,
    )


def _dt(y: int, m: int, d: int) -> datetime.datetime:
    return datetime.datetime(y, m, d, 12, 0, tzinfo=datetime.UTC)


class TestApplyTaskFilters:
    def test_no_filters(self) -> None:
        tasks = [_make_task(task_id="t1"), _make_task(task_id="t2")]
        result = _apply_task_filters(tasks, user_tz=UTC)
        assert len(result) == 2

    def test_filter_by_single_date(self) -> None:
        tasks = [
            _make_task(task_id="t1", due_date=_dt(2026, 3, 4)),
            _make_task(task_id="t2", due_date=_dt(2026, 3, 5)),
            _make_task(task_id="t3", due_date=None),
        ]
        result = _apply_task_filters(
            tasks, date_filter=datetime.date(2026, 3, 4), user_tz=UTC
        )
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_filter_by_date_range(self) -> None:
        tasks = [
            _make_task(task_id="t1", due_date=_dt(2026, 3, 2)),  # in range
            _make_task(task_id="t2", due_date=_dt(2026, 3, 8)),  # in range (last day)
            _make_task(task_id="t3", due_date=_dt(2026, 3, 9)),  # out of range
            _make_task(task_id="t4", due_date=_dt(2026, 3, 1)),  # out of range
        ]
        dr = DateRange(
            date_from=datetime.date(2026, 3, 2),
            date_to=datetime.date(2026, 3, 8),
        )
        result = _apply_task_filters(tasks, date_filter=dr, user_tz=UTC)
        assert {t.id for t in result} == {"t1", "t2"}

    def test_filter_by_priority(self) -> None:
        tasks = [
            _make_task(task_id="t1", priority=TaskPriority.HIGH),
            _make_task(task_id="t2", priority=TaskPriority.MEDIUM),
            _make_task(task_id="t3", priority=TaskPriority.NONE),
        ]
        result = _apply_task_filters(
            tasks, priority_filter=TaskPriority.HIGH, user_tz=UTC
        )
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_filter_combined_date_and_priority(self) -> None:
        tasks = [
            _make_task(task_id="t1", due_date=_dt(2026, 3, 4), priority=TaskPriority.HIGH),
            _make_task(task_id="t2", due_date=_dt(2026, 3, 4), priority=TaskPriority.NONE),
            _make_task(task_id="t3", due_date=_dt(2026, 3, 5), priority=TaskPriority.HIGH),
        ]
        result = _apply_task_filters(
            tasks,
            date_filter=datetime.date(2026, 3, 4),
            priority_filter=TaskPriority.HIGH,
            user_tz=UTC,
        )
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_filter_by_range_and_priority(self) -> None:
        dr = DateRange(
            date_from=datetime.date(2026, 3, 2),
            date_to=datetime.date(2026, 3, 8),
        )
        tasks = [
            _make_task(task_id="t1", due_date=_dt(2026, 3, 4), priority=TaskPriority.HIGH),
            _make_task(task_id="t2", due_date=_dt(2026, 3, 4), priority=TaskPriority.MEDIUM),
            _make_task(task_id="t3", due_date=_dt(2026, 3, 10), priority=TaskPriority.HIGH),
        ]
        result = _apply_task_filters(
            tasks,
            date_filter=dr,
            priority_filter=TaskPriority.HIGH,
            user_tz=UTC,
        )
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_excludes_completed(self) -> None:
        tasks = [
            _make_task(task_id="t1", status=0),
            _make_task(task_id="t2", status=2),  # completed
        ]
        result = _apply_task_filters(tasks, user_tz=UTC)
        assert len(result) == 1
        assert result[0].id == "t1"


import unittest.mock as mock
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs.handlers import handle_list_tasks, _reset_project_cache
from alice_ticktick.dialogs import responses as txt
from alice_ticktick.ticktick.models import Project


def _make_message(*, access_token: str | None = "test-token") -> MagicMock:
    message = MagicMock()
    message.command = ""
    message.session.new = False
    if access_token is not None:
        message.user = MagicMock()
        message.user.access_token = access_token
    else:
        message.user = None
    message.nlu = None
    return message


def _make_client_factory(tasks: list, projects: list | None = None) -> type:
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects or [Project(id="p1", name="Test")])
    client.get_tasks = AsyncMock(return_value=tasks)
    client.get_inbox_tasks = AsyncMock(return_value=[])
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _reset_project_cache()


class TestListTasksWithDateRange:
    async def test_list_tasks_this_week(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Задача в эту неделю",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
            _make_task(
                task_id="t2",
                title="Следующая неделя",
                due_date=datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC),
            ),
        ]
        intent_data = {"slots": {"date_range": {"value": "this_week"}}}
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_list_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Задача в эту неделю" in response.text

    async def test_list_tasks_this_week_no_tasks(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Следующая неделя",
                due_date=datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC),
            ),
        ]
        intent_data = {"slots": {"date_range": {"value": "this_week"}}}
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_list_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "нет" in response.text.lower()

    async def test_list_tasks_this_week_with_priority(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Высокий приоритет",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.HIGH,
            ),
            _make_task(
                task_id="t2",
                title="Нет приоритета",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
        ]
        intent_data = {
            "slots": {
                "date_range": {"value": "this_week"},
                "priority": {"value": "высокий"},
            }
        }
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_list_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Высокий приоритет" in response.text
        assert "Нет приоритета" not in response.text

from alice_ticktick.dialogs.handlers import handle_project_tasks


class TestProjectTasksFiltering:
    async def test_project_tasks_with_priority(self) -> None:
        tasks = [
            _make_task(task_id="t1", title="Срочный", priority=TaskPriority.HIGH),
            _make_task(task_id="t2", title="Обычный", priority=TaskPriority.NONE),
        ]
        intent_data = {
            "slots": {
                "project_name": {"value": "Работа"},
                "priority": {"value": "высокий"},
            }
        }
        projects = [Project(id="p1", name="Работа")]
        message = _make_message()
        response = await handle_project_tasks(
            message,
            intent_data,
            ticktick_client_factory=_make_client_factory(tasks, projects=projects),
        )
        assert "Срочный" in response.text
        assert "Обычный" not in response.text

    async def test_project_tasks_with_date(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Сегодняшняя",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
            ),
            _make_task(
                task_id="t2",
                title="Другая дата",
                due_date=datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC),
            ),
        ]
        intent_data = {
            "slots": {
                "project_name": {"value": "Работа"},
                "date": {"value": {"year": 2026, "month": 3, "day": 4}},  # абсолютная дата
            }
        }
        projects = [Project(id="p1", name="Работа")]
        message = _make_message()
        response = await handle_project_tasks(
            message,
            intent_data,
            ticktick_client_factory=_make_client_factory(tasks, projects=projects),
        )
        assert "Сегодняшняя" in response.text
        assert "Другая дата" not in response.text

    async def test_project_tasks_with_date_range(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="В эту неделю",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
            ),
            _make_task(
                task_id="t2",
                title="Следующая неделя",
                due_date=datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC),
            ),
        ]
        intent_data = {
            "slots": {
                "project_name": {"value": "Работа"},
                "date_range": {"value": "this_week"},
            }
        }
        projects = [Project(id="p1", name="Работа")]
        message = _make_message()
        fixed_range = DateRange(
            date_from=datetime.date(2026, 3, 2),
            date_to=datetime.date(2026, 3, 8),
        )
        with mock.patch("alice_ticktick.dialogs.handlers.parse_date_range", return_value=fixed_range):
            response = await handle_project_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks, projects=projects),
            )
        assert "В эту неделю" in response.text
        assert "Следующая неделя" not in response.text

    async def test_project_tasks_combined_date_range_and_priority(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Срочная в неделю",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.HIGH,
            ),
            _make_task(
                task_id="t2",
                title="Обычная в неделю",
                due_date=datetime.datetime(2026, 3, 4, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
            _make_task(
                task_id="t3",
                title="Срочная не в неделю",
                due_date=datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.HIGH,
            ),
        ]
        intent_data = {
            "slots": {
                "project_name": {"value": "Работа"},
                "date_range": {"value": "this_week"},
                "priority": {"value": "высокий"},
            }
        }
        projects = [Project(id="p1", name="Работа")]
        message = _make_message()
        fixed_range = DateRange(
            date_from=datetime.date(2026, 3, 2),
            date_to=datetime.date(2026, 3, 8),
        )
        with mock.patch("alice_ticktick.dialogs.handlers.parse_date_range", return_value=fixed_range):
            response = await handle_project_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks, projects=projects),
            )
        assert "Срочная в неделю" in response.text
        assert "Обычная в неделю" not in response.text
        assert "Срочная не в неделю" not in response.text

from alice_ticktick.dialogs.handlers import handle_overdue_tasks


class TestOverdueTasksFiltering:
    async def test_overdue_with_high_priority(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Срочная просроченная",
                due_date=datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.HIGH,
            ),
            _make_task(
                task_id="t2",
                title="Обычная просроченная",
                due_date=datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
        ]
        intent_data = {"slots": {"priority": {"value": "высокий"}}}
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_overdue_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Срочная просроченная" in response.text
        assert "Обычная просроченная" not in response.text

    async def test_overdue_with_priority_no_match(self) -> None:
        tasks = [
            _make_task(
                task_id="t1",
                title="Обычная просроченная",
                due_date=datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
        ]
        intent_data = {"slots": {"priority": {"value": "высокий"}}}
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_overdue_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "нет" in response.text.lower()

    async def test_overdue_without_priority_filter(self) -> None:
        """Без priority-слота — показываем все просроченные (регрессия)."""
        tasks = [
            _make_task(
                task_id="t1",
                title="Просроченная",
                due_date=datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.UTC),
                priority=TaskPriority.NONE,
            ),
        ]
        intent_data = {"slots": {}}
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_overdue_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Просроченная" in response.text
