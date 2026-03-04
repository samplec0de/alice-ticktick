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
