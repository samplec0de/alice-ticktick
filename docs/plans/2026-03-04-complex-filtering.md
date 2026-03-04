# Complex Task Filtering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Реализовать FR-15 — комбинированную фильтрацию задач (дата + диапазон недели/месяца + приоритет + проект) через TickTick API v1.

**Architecture:** Расширяем три существующих интента (`list_tasks`, `project_tasks`, `overdue_tasks`) новыми слотами. Добавляем `DateRange` в date_parser.py и общую утилиту `_apply_task_filters` в handlers.py. Теги (V2 only) — вне скоупа.

**Tech Stack:** Python 3.12, aliceio, pytest + pytest-asyncio, rapidfuzz, pydantic

---

## Task 1: DateRange model + parse_date_range

**Files:**
- Modify: `alice_ticktick/dialogs/nlp/date_parser.py`
- Test: `tests/test_date_parser.py` (дописываем в существующий файл)

### Step 1: Write failing tests

Добавить в `tests/test_date_parser.py`:

```python
import datetime
from zoneinfo import ZoneInfo

from alice_ticktick.dialogs.nlp.date_parser import DateRange, parse_date_range

MSK = ZoneInfo("Europe/Moscow")


class TestDateRange:
    def test_this_week_monday(self) -> None:
        # 2026-03-02 — понедельник
        now = datetime.date(2026, 3, 2)
        result = parse_date_range("this_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 2)
        assert result.date_to == datetime.date(2026, 3, 8)

    def test_this_week_wednesday(self) -> None:
        # 2026-03-04 — среда, неделя всё равно Пн–Вс
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("this_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 2)
        assert result.date_to == datetime.date(2026, 3, 8)

    def test_next_week(self) -> None:
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("next_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 9)
        assert result.date_to == datetime.date(2026, 3, 15)

    def test_this_month(self) -> None:
        now = datetime.date(2026, 3, 15)
        result = parse_date_range("this_month", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 1)
        assert result.date_to == datetime.date(2026, 3, 31)

    def test_this_month_february(self) -> None:
        # Февраль 2026 — 28 дней
        now = datetime.date(2026, 2, 10)
        result = parse_date_range("this_month", now=now, tz=MSK)
        assert result is not None
        assert result.date_to == datetime.date(2026, 2, 28)

    def test_unknown_value(self) -> None:
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("unknown_value", now=now, tz=MSK)
        assert result is None
```

### Step 2: Run to verify FAIL

```bash
uv run pytest tests/test_date_parser.py::TestDateRange -v
```
Expected: `ImportError: cannot import name 'DateRange'`

### Step 3: Implement DateRange + parse_date_range

В `alice_ticktick/dialogs/nlp/date_parser.py` добавить в конец файла:

```python
import calendar
from dataclasses import dataclass


@dataclass
class DateRange:
    """Inclusive date range."""

    date_from: datetime.date
    date_to: datetime.date


def parse_date_range(
    value: str,
    *,
    now: datetime.date | None = None,
    tz: ZoneInfo | None = None,
) -> DateRange | None:
    """Convert a date_range NLU slot value to a DateRange.

    Supported values:
    - 'this_week'  — Monday to Sunday of the current week
    - 'next_week'  — Monday to Sunday of the next week
    - 'this_month' — first to last day of the current month

    Returns None for unknown values.
    """
    if now is None:
        _tz = tz or ZoneInfo("UTC")
        now = datetime.datetime.now(tz=_tz).date()

    if value == "this_week":
        monday = now - datetime.timedelta(days=now.weekday())
        sunday = monday + datetime.timedelta(days=6)
        return DateRange(date_from=monday, date_to=sunday)

    if value == "next_week":
        monday = now - datetime.timedelta(days=now.weekday()) + datetime.timedelta(weeks=1)
        sunday = monday + datetime.timedelta(days=6)
        return DateRange(date_from=monday, date_to=sunday)

    if value == "this_month":
        first = now.replace(day=1)
        last_day = calendar.monthrange(now.year, now.month)[1]
        last = now.replace(day=last_day)
        return DateRange(date_from=first, date_to=last)

    return None
```

Убедиться что импорт `ZoneInfo` уже есть в файле (он используется в parse_yandex_datetime).
Если нет — добавить `from zoneinfo import ZoneInfo` в начало файла.
Также добавить `import calendar`.

Экспортировать `DateRange` и `parse_date_range` из `alice_ticktick/dialogs/nlp/__init__.py`:

```python
from alice_ticktick.dialogs.nlp.date_parser import DateRange, parse_date_range
```

### Step 4: Run to verify PASS

```bash
uv run pytest tests/test_date_parser.py::TestDateRange -v
```
Expected: 6 passed

### Step 5: Commit

```bash
git add alice_ticktick/dialogs/nlp/date_parser.py alice_ticktick/dialogs/nlp/__init__.py tests/test_date_parser.py
git commit -m "feat: добавить DateRange и parse_date_range в date_parser"
```

---

## Task 2: Утилита _apply_task_filters в handlers.py

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Test: `tests/test_handlers_filtering.py` (новый файл)

### Step 1: Write failing tests

Создать `tests/test_handlers_filtering.py`:

```python
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
```

### Step 2: Run to verify FAIL

```bash
uv run pytest tests/test_handlers_filtering.py::TestApplyTaskFilters -v
```
Expected: `ImportError: cannot import name '_apply_task_filters'`

### Step 3: Implement _apply_task_filters

В `alice_ticktick/dialogs/handlers.py` добавить импорт в начало файла:

```python
from alice_ticktick.dialogs.nlp.date_parser import DateRange
```

После функции `_format_task_context` (около строки 170) добавить:

```python
def _apply_task_filters(
    tasks: list[Task],
    *,
    date_filter: datetime.date | DateRange | None = None,
    priority_filter: TaskPriority | None = None,
    user_tz: ZoneInfo,
) -> list[Task]:
    """Filter active tasks by date (single day or range) and/or priority."""
    result = [t for t in tasks if t.status == 0]

    if date_filter is not None:
        if isinstance(date_filter, DateRange):
            result = [
                t
                for t in result
                if t.due_date is not None
                and date_filter.date_from
                <= _to_user_date(t.due_date, user_tz)
                <= date_filter.date_to
            ]
        else:
            result = [
                t
                for t in result
                if t.due_date is not None
                and _to_user_date(t.due_date, user_tz) == date_filter
            ]

    if priority_filter is not None:
        result = [t for t in result if t.priority == priority_filter]

    return result
```

### Step 4: Run to verify PASS

```bash
uv run pytest tests/test_handlers_filtering.py::TestApplyTaskFilters -v
```
Expected: 7 passed

### Step 5: Commit

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_filtering.py
git commit -m "feat: добавить _apply_task_filters в handlers"
```

---

## Task 3: Добавить date_range в list_tasks

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py`
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `alice_ticktick/dialogs/responses.py`
- Test: `tests/test_handlers_filtering.py` (дописываем)

### Step 1: Write failing tests

Добавить в `tests/test_handlers_filtering.py`:

```python
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

        # Patch now to 2026-03-04 (Wednesday)
        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
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

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
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

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_list_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Высокий приоритет" in response.text
        assert "Нет приоритета" not in response.text
```

### Step 2: Run to verify FAIL

```bash
uv run pytest tests/test_handlers_filtering.py::TestListTasksWithDateRange -v
```
Expected: FAIL (slots.date_range не распознаётся)

### Step 3: Обновить intents.py

В `alice_ticktick/dialogs/intents.py` найти класс `ListTasksSlots` и добавить поле:

```python
@dataclass(frozen=True, slots=True)
class ListTasksSlots:
    """Extracted slots for list_tasks intent."""

    date: YandexDateTime | None = None
    priority: str | None = None
    date_range: str | None = None   # ← добавить
```

В функцию `extract_list_tasks_slots` добавить извлечение:

```python
def extract_list_tasks_slots(intent_data: dict[str, Any]) -> ListTasksSlots:
    """Extract slots from list_tasks intent."""
    return ListTasksSlots(
        date=_get_slot_value(intent_data, "date"),
        priority=_get_slot_value(intent_data, "priority"),
        date_range=_get_slot_value(intent_data, "date_range"),   # ← добавить
    )
```

### Step 4: Добавить response strings

В `alice_ticktick/dialogs/responses.py` после блока `# Filter by priority` добавить:

```python
# Date range responses
TASKS_FOR_WEEK = "На этой неделе {count}:\n{tasks}"
TASKS_FOR_NEXT_WEEK = "На следующей неделе {count}:\n{tasks}"
TASKS_FOR_MONTH = "В этом месяце {count}:\n{tasks}"
TASKS_FOR_WEEK_WITH_PRIORITY = "На этой неделе с {priority}, {count}:\n{tasks}"
TASKS_FOR_NEXT_WEEK_WITH_PRIORITY = "На следующей неделе с {priority}, {count}:\n{tasks}"
TASKS_FOR_MONTH_WITH_PRIORITY = "В этом месяце с {priority}, {count}:\n{tasks}"
NO_TASKS_FOR_WEEK = "На этой неделе задач нет."
NO_TASKS_FOR_NEXT_WEEK = "На следующей неделе задач нет."
NO_TASKS_FOR_MONTH = "В этом месяце задач нет."
NO_TASKS_FOR_WEEK_WITH_PRIORITY = "На этой неделе задач с {priority} нет."
NO_TASKS_FOR_NEXT_WEEK_WITH_PRIORITY = "На следующей неделе задач с {priority} нет."
NO_TASKS_FOR_MONTH_WITH_PRIORITY = "В этом месяце задач с {priority} нет."
```

### Step 5: Обновить handle_list_tasks

В `alice_ticktick/dialogs/handlers.py` в функции `handle_list_tasks` добавить обработку `date_range` после извлечения слотов.

Найти текущий блок определения `target_day` (строки ~808–818):

```python
    # Determine target date (in user timezone)
    if slots.date:
        ...
    else:
        target_day = datetime.datetime.now(tz=user_tz).date()
```

Заменить на:

```python
    # Determine target date or range (in user timezone)
    date_range_filter: DateRange | None = None
    date_range_label: str | None = None

    if slots.date_range:
        date_range_filter = parse_date_range(
            slots.date_range,
            now=datetime.datetime.now(tz=user_tz).date(),
            tz=user_tz,
        )
        date_range_label = {
            "this_week": "на этой неделе",
            "next_week": "на следующей неделе",
            "this_month": "в этом месяце",
        }.get(slots.date_range)

    if date_range_filter is not None:
        # Range-based filtering path
        priority_filter = parse_priority(slots.priority) if slots.priority else None
        priority_label = (
            _format_priority_label(priority_filter) if priority_filter is not None else None
        )

        filtered = _apply_task_filters(
            all_tasks,
            date_filter=date_range_filter,
            priority_filter=priority_filter,
            user_tz=user_tz,
        )

        _range_txt_map = {
            "this_week": (
                txt.TASKS_FOR_WEEK,
                txt.TASKS_FOR_WEEK_WITH_PRIORITY,
                txt.NO_TASKS_FOR_WEEK,
                txt.NO_TASKS_FOR_WEEK_WITH_PRIORITY,
            ),
            "next_week": (
                txt.TASKS_FOR_NEXT_WEEK,
                txt.TASKS_FOR_NEXT_WEEK_WITH_PRIORITY,
                txt.NO_TASKS_FOR_NEXT_WEEK,
                txt.NO_TASKS_FOR_NEXT_WEEK_WITH_PRIORITY,
            ),
            "this_month": (
                txt.TASKS_FOR_MONTH,
                txt.TASKS_FOR_MONTH_WITH_PRIORITY,
                txt.NO_TASKS_FOR_MONTH,
                txt.NO_TASKS_FOR_MONTH_WITH_PRIORITY,
            ),
        }
        tmpl_found, tmpl_found_p, tmpl_none, tmpl_none_p = _range_txt_map.get(
            slots.date_range,
            (txt.TASKS_FOR_WEEK, txt.TASKS_FOR_WEEK_WITH_PRIORITY,
             txt.NO_TASKS_FOR_WEEK, txt.NO_TASKS_FOR_WEEK_WITH_PRIORITY),
        )

        if not filtered:
            if priority_label:
                return Response(text=tmpl_none_p.format(priority=priority_label))
            return Response(text=tmpl_none)

        count_str = txt.pluralize_tasks(len(filtered))
        lines = [_format_task_line(i + 1, t) for i, t in enumerate(filtered[:5])]
        task_list = "\n".join(lines)

        if priority_label:
            return Response(
                text=_truncate_response(
                    tmpl_found_p.format(priority=priority_label, count=count_str, tasks=task_list)
                )
            )
        return Response(
            text=_truncate_response(tmpl_found.format(count=count_str, tasks=task_list))
        )

    # Single-day path (existing logic continues below)
    if slots.date:
        ...
```

**Важно:** убедись что `parse_date_range` импортирован в `handlers.py`. Добавить в импорты из `alice_ticktick.dialogs.nlp`:

```python
from alice_ticktick.dialogs.nlp import (
    ...
    parse_date_range,
    ...
)
```

И убедиться что `parse_date_range` экспортирован из `alice_ticktick/dialogs/nlp/__init__.py` (это сделано в Task 1).

Также нужно переставить блок получения `all_tasks` до условия `date_range`, т.к. он сейчас стоит после. Текущий порядок в `handle_list_tasks`:
1. auth check
2. slots extraction
3. target_day determination
4. `_gather_all_tasks` call
5. filter

Новый порядок:
1. auth check
2. slots extraction
3. `_gather_all_tasks` call (переместить выше)
4. date_range check → early return
5. single-day path (existing)

### Step 6: Run to verify PASS

```bash
uv run pytest tests/test_handlers_filtering.py::TestListTasksWithDateRange -v
```
Expected: 3 passed

### Step 7: Run full suite

```bash
uv run pytest tests/test_handlers.py tests/test_handlers_filtering.py -v
```
Expected: все проходят (регрессия не сломана)

### Step 8: Commit

```bash
git add alice_ticktick/dialogs/intents.py alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers_filtering.py
git commit -m "feat: поддержка date_range (неделя/месяц) в list_tasks"
```

---

## Task 4: Расширить project_tasks — date + priority фильтры

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py`
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `alice_ticktick/dialogs/responses.py`
- Test: `tests/test_handlers_filtering.py` (дописываем)

### Step 1: Write failing tests

Добавить в `tests/test_handlers_filtering.py`:

```python
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
                "date": {"value": {"day": 0, "day_is_relative": True}},  # сегодня
            }
        }
        projects = [Project(id="p1", name="Работа")]
        message = _make_message()
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_project_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks, projects=projects),
                event_update=event_update,
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
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_project_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks, projects=projects),
                event_update=event_update,
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
        event_update = MagicMock()
        event_update.meta.timezone = "UTC"
        event_update.meta.interfaces = MagicMock()
        event_update.meta.interfaces.account_linking = None

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_project_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks, projects=projects),
                event_update=event_update,
            )
        assert "Срочная в неделю" in response.text
        assert "Обычная в неделю" not in response.text
        assert "Срочная не в неделю" not in response.text
```

### Step 2: Run to verify FAIL

```bash
uv run pytest tests/test_handlers_filtering.py::TestProjectTasksFiltering -v
```
Expected: FAIL

### Step 3: Обновить ProjectTasksSlots в intents.py

```python
@dataclass(frozen=True, slots=True)
class ProjectTasksSlots:
    """Extracted slots for project_tasks intent."""

    project_name: str | None = None
    date: YandexDateTime | None = None          # ← добавить
    date_range: str | None = None               # ← добавить
    priority: str | None = None                 # ← добавить
```

Обновить `extract_project_tasks_slots`:

```python
def extract_project_tasks_slots(intent_data: dict[str, Any]) -> ProjectTasksSlots:
    """Extract slots from project_tasks intent."""
    return ProjectTasksSlots(
        project_name=_get_slot_value(intent_data, "project_name"),
        date=_get_slot_value(intent_data, "date"),
        date_range=_get_slot_value(intent_data, "date_range"),
        priority=_get_slot_value(intent_data, "priority"),
    )
```

### Step 4: Добавить response strings

В `alice_ticktick/dialogs/responses.py`:

```python
# Project tasks with filters
PROJECT_TASKS_WITH_PRIORITY = 'В проекте "{project}" с {priority}, {count}:\n{tasks}'
PROJECT_NO_TASKS_WITH_PRIORITY = 'В проекте "{project}" задач с {priority} нет.'
PROJECT_NO_TASKS_WITH_DATE = 'В проекте "{project}" на {date} задач нет.'
PROJECT_TASKS_WITH_DATE = 'В проекте "{project}" на {date}, {count}:\n{tasks}'
```

### Step 5: Обновить handle_project_tasks

Найти в `handlers.py` функцию `handle_project_tasks`. После получения `tasks` добавить применение фильтров.

Заменить блок:
```python
    active = [t for t in tasks if t.status == 0]
    if not active:
        return Response(text=txt.PROJECT_NO_TASKS.format(project=project.name))
```

На:
```python
    user_tz = _get_user_tz(event_update)

    # Build date filter
    date_filter: datetime.date | DateRange | None = None
    if slots.date_range:
        date_filter = parse_date_range(
            slots.date_range,
            now=datetime.datetime.now(tz=user_tz).date(),
            tz=user_tz,
        )
    elif slots.date:
        try:
            parsed = parse_yandex_datetime(slots.date)
            date_filter = parsed.date() if isinstance(parsed, datetime.datetime) else parsed
        except ValueError:
            pass

    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = (
        _format_priority_label(priority_filter) if priority_filter is not None else None
    )

    active = _apply_task_filters(
        tasks,
        date_filter=date_filter,
        priority_filter=priority_filter,
        user_tz=user_tz,
    )
    if not active:
        if priority_label:
            return Response(
                text=txt.PROJECT_NO_TASKS_WITH_PRIORITY.format(
                    project=project.name, priority=priority_label
                )
            )
        return Response(text=txt.PROJECT_NO_TASKS.format(project=project.name))
```

Также убрать строку `user_tz = _get_user_tz(event_update)` которая была ниже (теперь она поднята вверх).

Обновить формирование ответа — в конце функции использовать `priority_label` если есть:

```python
    count = txt.pluralize_tasks(len(active))
    lines: list[str] = []
    for i, task in enumerate(active[:10]):
        line = f"{i + 1}. {task.title}"
        parts: list[str] = []
        if task.due_date:
            parts.append(_format_date(task.due_date, user_tz))
        prio = _format_priority_short(task.priority)
        if prio:
            parts.append(prio)
        if parts:
            line += f" — {', '.join(parts)}"
        lines.append(line)

    if priority_label:
        text = txt.PROJECT_TASKS_WITH_PRIORITY.format(
            project=project.name, priority=priority_label, count=count, tasks="\n".join(lines)
        )
    else:
        text = txt.PROJECT_TASKS_HEADER.format(
            project=project.name, count=count, tasks="\n".join(lines)
        )
    return Response(text=_truncate_response(text))
```

### Step 6: Run to verify PASS

```bash
uv run pytest tests/test_handlers_filtering.py::TestProjectTasksFiltering -v
```
Expected: 4 passed

### Step 7: Run projects tests for regression

```bash
uv run pytest tests/test_handlers_projects.py -v
```
Expected: все проходят

### Step 8: Commit

```bash
git add alice_ticktick/dialogs/intents.py alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers_filtering.py
git commit -m "feat: фильтры date/date_range/priority в project_tasks"
```

---

## Task 5: Расширить overdue_tasks — priority фильтр

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py`
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `alice_ticktick/dialogs/responses.py`
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers_filtering.py` (дописываем)

### Step 1: Write failing tests

Добавить в `tests/test_handlers_filtering.py`:

```python
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

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
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

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
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

        import unittest.mock as mock
        with mock.patch("alice_ticktick.dialogs.handlers.datetime") as mock_dt:
            mock_dt.datetime = datetime.datetime
            mock_dt.date = datetime.date
            mock_dt.timedelta = datetime.timedelta
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 3, 4, 10, 0, tzinfo=datetime.UTC)
            response = await handle_overdue_tasks(
                message,
                intent_data,
                ticktick_client_factory=_make_client_factory(tasks),
                event_update=event_update,
            )
        assert "Просроченная" in response.text
```

### Step 2: Run to verify FAIL

```bash
uv run pytest tests/test_handlers_filtering.py::TestOverdueTasksFiltering -v
```
Expected: FAIL (`handle_overdue_tasks` не принимает `intent_data`)

### Step 3: Добавить OverdueTasksSlots в intents.py

```python
@dataclass(frozen=True, slots=True)
class OverdueTasksSlots:
    """Extracted slots for overdue_tasks intent."""

    priority: str | None = None


def extract_overdue_tasks_slots(intent_data: dict[str, Any]) -> OverdueTasksSlots:
    """Extract slots from overdue_tasks intent."""
    return OverdueTasksSlots(
        priority=_get_slot_value(intent_data, "priority"),
    )
```

### Step 4: Добавить response strings

```python
# Overdue with priority
OVERDUE_WITH_PRIORITY = "Просроченных с {priority}: {count}:\n{tasks}"
NO_OVERDUE_WITH_PRIORITY = "Просроченных задач с {priority} нет."
```

### Step 5: Обновить handle_overdue_tasks

Изменить сигнатуру функции — добавить `intent_data`:

```python
async def handle_overdue_tasks(
    message: Message,
    intent_data: dict[str, Any] | None = None,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
```

В начале функции после auth check добавить:

```python
    from alice_ticktick.dialogs.intents import extract_overdue_tasks_slots

    slots = extract_overdue_tasks_slots(intent_data or {})
    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = (
        _format_priority_label(priority_filter) if priority_filter is not None else None
    )
```

Заменить блок фильтрации просроченных:

```python
    overdue = [
        t
        for t in all_tasks
        if t.due_date is not None and _to_user_date(t.due_date, user_tz) < today and t.status == 0
    ]
```

На:
```python
    overdue = _apply_task_filters(
        [t for t in all_tasks if t.due_date is not None and _to_user_date(t.due_date, user_tz) < today],
        priority_filter=priority_filter,
        user_tz=user_tz,
    )
```

Обновить формирование ответа:

```python
    if not overdue:
        if priority_label:
            return Response(text=txt.NO_OVERDUE_WITH_PRIORITY.format(priority=priority_label))
        return Response(text=txt.NO_OVERDUE)

    count_str = txt.pluralize_tasks(len(overdue))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(overdue[:5])]
    task_list = "\n".join(lines)

    if priority_label:
        return Response(
            text=_truncate_response(
                txt.OVERDUE_WITH_PRIORITY.format(
                    priority=priority_label, count=count_str, tasks=task_list
                )
            )
        )
    return Response(
        text=_truncate_response(
            txt.OVERDUE_TASKS_HEADER.format(count=count_str, tasks=task_list)
        )
    )
```

### Step 6: Обновить router.py

Найти `on_overdue_tasks` и добавить передачу `intent_data`:

```python
@router.message(IntentFilter(OVERDUE_TASKS))
async def on_overdue_tasks(
    message: Message,
    intent_data: dict[str, Any],
    event_update: Update,
) -> Response:
    """Handle overdue_tasks intent."""
    return await handle_overdue_tasks(message, intent_data, event_update=event_update)
```

### Step 7: Run to verify PASS

```bash
uv run pytest tests/test_handlers_filtering.py::TestOverdueTasksFiltering -v
```
Expected: 3 passed

### Step 8: Full test suite

```bash
uv run pytest -v
```
Expected: все проходят

### Step 9: Commit

```bash
git add alice_ticktick/dialogs/intents.py alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py alice_ticktick/dialogs/router.py tests/test_handlers_filtering.py
git commit -m "feat: фильтр приоритета в overdue_tasks"
```

---

## Task 6: NLU-грамматики в Яндекс.Диалогах

Это ручной шаг — изменения в консоли Яндекс.Диалогов.

### Что обновить

**Интент `list_tasks`** — добавить слот `date_range`:
- Тип слота: `string` (custom)
- Грамматика слота: `.+`
- Обучающие примеры с разметкой:

```
Покажи задачи [на этой неделе](date_range=this_week)
Что у меня [в эту неделю](date_range=this_week)
Задачи [на следующей неделе](date_range=next_week)
Покажи [в этом месяце](date_range=this_month)
Срочные задачи [на этой неделе](date_range=this_week) с высоким приоритетом
```

**Интент `project_tasks`** — добавить слоты `date`, `date_range`, `priority`:
- `date`: тип `YANDEX.DATETIME`
- `date_range`: тип `string`, грамматика `.+`
- `priority`: тип `string`, грамматика `.+`

Обучающие примеры:
```
Задачи проекта [Работа](project_name) [на этой неделе](date_range=this_week)
Покажи [Работа](project_name) [с высоким приоритетом](priority=высокий)
Что в проекте [Дом](project_name) [на завтра](date)
Задачи [Работа](project_name) [на следующей неделе](date_range=next_week) [срочные](priority=срочный)
```

**Интент `overdue_tasks`** — добавить слот `priority`:
- `priority`: тип `string`, грамматика `.+`

Обучающие примеры:
```
Какие [срочные](priority=срочный) задачи просрочены
Просроченные [с высоким приоритетом](priority=высокий)
Что я пропустил [важного](priority=важный)
```

### После изменений

Нажать "Протестировать" в Яндекс.Диалогах для каждого интента.
Убедиться что Точность и Полнота — 100%.

---

## Final verification

```bash
uv run pytest -v
uv run ruff check .
uv run mypy alice_ticktick/
```

Все тесты должны пройти, линтер и mypy — без ошибок.
