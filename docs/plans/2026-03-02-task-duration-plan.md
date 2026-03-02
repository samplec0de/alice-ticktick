# Task Duration (Meetings) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Support creating tasks with duration ("на 2 часа") and time ranges ("с 14 до 16") by extending the existing `create_task` intent.

**Architecture:** Extend `CreateTaskSlots` with 4 new fields (duration_value, duration_unit, range_start, range_end). Add `parse_duration()` NLP function. Modify `handle_create_task` to compute startDate/dueDate from duration or range slots. New response templates with "Добавила!" format for timed tasks. Grammar changes are documented but applied manually in Yandex Dialogs UI after merge.

**Tech Stack:** Python 3.12+, aliceio, pydantic, pytest, pytest-asyncio

---

### Task 1: parse_duration — NLP function

**Files:**
- Create: `alice_ticktick/dialogs/nlp/duration_parser.py`
- Modify: `alice_ticktick/dialogs/nlp/__init__.py:1-19`
- Test: `tests/test_duration_parser.py`

**Step 1: Write the failing tests**

```python
"""Tests for duration parser."""

import datetime

from alice_ticktick.dialogs.nlp.duration_parser import parse_duration


class TestParseDuration:
    def test_hours_with_value(self) -> None:
        assert parse_duration(2, "час") == datetime.timedelta(hours=2)

    def test_hours_without_value(self) -> None:
        assert parse_duration(None, "час") == datetime.timedelta(hours=1)

    def test_minutes_with_value(self) -> None:
        assert parse_duration(30, "минута") == datetime.timedelta(minutes=30)

    def test_minutes_without_value(self) -> None:
        assert parse_duration(None, "минута") == datetime.timedelta(minutes=1)

    def test_half_hour(self) -> None:
        assert parse_duration(None, "полчаса") == datetime.timedelta(minutes=30)

    def test_half_hour_ignores_value(self) -> None:
        assert parse_duration(3, "полчаса") == datetime.timedelta(minutes=30)

    def test_none_unit_returns_none(self) -> None:
        assert parse_duration(2, None) is None

    def test_unknown_unit_returns_none(self) -> None:
        assert parse_duration(1, "неизвестное") is None

    def test_hours_declensions(self) -> None:
        for word in ("час", "часа", "часов"):
            assert parse_duration(3, word) == datetime.timedelta(hours=3)

    def test_minutes_declensions(self) -> None:
        for word in ("минута", "минуту", "минуты", "минут"):
            assert parse_duration(15, word) == datetime.timedelta(minutes=15)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_duration_parser.py -v`
Expected: FAIL — module not found

**Step 3: Write implementation**

`alice_ticktick/dialogs/nlp/duration_parser.py`:
```python
"""Parser for task duration from voice input."""

from __future__ import annotations

import datetime

_HOUR_WORDS = frozenset({"час", "часа", "часов"})
_MINUTE_WORDS = frozenset({"минута", "минуту", "минуты", "минут"})
_HALF_HOUR_WORDS = frozenset({"полчаса"})


def parse_duration(
    duration_value: int | None,
    duration_unit: str | None,
) -> datetime.timedelta | None:
    """Convert duration slot values into a timedelta.

    *duration_unit* is a Russian word (e.g. "час", "минута", "полчаса").
    *duration_value* is the count (None → 1, ignored for "полчаса").
    """
    if duration_unit is None:
        return None

    unit = duration_unit.lower().strip()

    if unit in _HALF_HOUR_WORDS:
        return datetime.timedelta(minutes=30)

    n = duration_value if duration_value is not None else 1

    if unit in _HOUR_WORDS:
        return datetime.timedelta(hours=n)
    if unit in _MINUTE_WORDS:
        return datetime.timedelta(minutes=n)

    return None
```

**Step 4: Export from nlp package**

In `alice_ticktick/dialogs/nlp/__init__.py`, add import and `__all__` entry:
```python
from alice_ticktick.dialogs.nlp.duration_parser import parse_duration
```
Add `"parse_duration"` to `__all__`.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_duration_parser.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/nlp/duration_parser.py alice_ticktick/dialogs/nlp/__init__.py tests/test_duration_parser.py
git commit -m "feat: parse_duration для длительности задач"
```

---

### Task 2: CreateTaskSlots — new duration/range fields

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py:49-143`
- Test: `tests/test_duration_parser.py` (extend)

**Step 1: Write failing tests**

Append to `tests/test_duration_parser.py`:
```python
from alice_ticktick.dialogs.intents import extract_create_task_slots


class TestCreateTaskSlotsExtraction:
    def test_duration_slots_extracted(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {"value": {"day": 1, "day_is_relative": True}},
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.task_name == "совещание"
        assert slots.duration_value == 2
        assert slots.duration_unit == "часа"

    def test_duration_unit_only(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "ланч"},
                "duration_unit": {"value": "час"},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.duration_value is None
        assert slots.duration_unit == "час"

    def test_range_slots_extracted(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "митинг"},
                "range_start": {"value": {"hour": 14}},
                "range_end": {"value": {"hour": 16}},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.range_start == {"hour": 14}
        assert slots.range_end == {"hour": 16}

    def test_no_duration_fields_default_none(self) -> None:
        intent_data = {"slots": {"task_name": {"value": "тест"}}}
        slots = extract_create_task_slots(intent_data)
        assert slots.duration_value is None
        assert slots.duration_unit is None
        assert slots.range_start is None
        assert slots.range_end is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_duration_parser.py::TestCreateTaskSlotsExtraction -v`
Expected: FAIL — `CreateTaskSlots` has no `duration_value` attribute

**Step 3: Modify CreateTaskSlots and extract function**

In `alice_ticktick/dialogs/intents.py`:

Add 4 fields to `CreateTaskSlots` (after line 61):
```python
    duration_value: int | None = None
    duration_unit: str | None = None
    range_start: YandexDateTime | None = None
    range_end: YandexDateTime | None = None
```

Update `extract_create_task_slots` to extract the new slots (in the return statement, after `reminder_unit`):
```python
        duration_value=_as_int(_get_slot_value(intent_data, "duration_value")),
        duration_unit=_get_slot_value(intent_data, "duration_unit"),
        range_start=_get_slot_value(intent_data, "range_start"),
        range_end=_get_slot_value(intent_data, "range_end"),
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_duration_parser.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/intents.py tests/test_duration_parser.py
git commit -m "feat: duration/range слоты в CreateTaskSlots"
```

---

### Task 3: Response templates

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py:32-49`

**Step 1: Add new response constants**

After line 47 (`TASK_CREATED_RECURRING_WITH_REMINDER`) in `responses.py`, add:
```python
# Create task with duration/range
TASK_CREATED_WITH_DURATION = 'Добавила! "{name}" на {date}, {start_time} до {end_time}.'
TASK_CREATED_WITH_DURATION_AND_PRIORITY = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, приоритет — {priority}.'
)
TASK_CREATED_WITH_DURATION_RECURRING = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, {recurrence}.'
)
TASK_CREATED_WITH_DURATION_AND_REMINDER = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, напоминание {reminder}.'
)
TASK_CREATED_WITH_DURATION_RECURRING_AND_REMINDER = (
    'Добавила! "{name}" на {date}, {start_time} до {end_time}, {recurrence}, напоминание {reminder}.'
)
DURATION_MISSING_START_TIME = "Во сколько начинается? Скажите время."
```

**Step 2: No separate test needed — templates are string constants. Tested via handler tests in Task 4.**

**Step 3: Commit**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: шаблоны ответов для задач с длительностью"
```

---

### Task 4: Handler logic — duration and range in handle_create_task

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:345-523`
- Test: `tests/test_handlers.py` (extend)

This is the largest task. The handler needs to:
1. Check for range slots → compute startDate/dueDate
2. Check for duration slots + date → compute startDate/dueDate
3. Check for duration slots without date → return clarification prompt
4. Build response with new "Добавила!" templates when duration/range present

**Step 1: Write failing tests**

Create `tests/test_handlers_duration.py`:
```python
"""Tests for task duration/range handling in create_task."""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import handle_create_task
from alice_ticktick.ticktick.models import Task, TaskPriority

TZ = ZoneInfo("Europe/Moscow")


def _make_message(
    *,
    tokens: list[str] | None = None,
    entities: list[Any] | None = None,
    access_token: str = "test-token",
) -> MagicMock:
    msg = MagicMock()
    msg.user = MagicMock()
    msg.user.access_token = access_token
    nlu = MagicMock()
    nlu.tokens = tokens or []
    nlu.entities = entities or []
    msg.nlu = nlu
    return msg


def _make_update(tz: str = "Europe/Moscow") -> MagicMock:
    update = MagicMock()
    update.meta.interfaces.account_linking = None
    update.meta.timezone = tz
    return update


def _mock_client_factory() -> type:
    created_payload = {}

    class MockClient:
        def __init__(self, token: str) -> None:
            pass

        async def __aenter__(self) -> "MockClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def create_task(self, payload: Any) -> Task:
            created_payload.update(payload.model_dump(by_alias=True, exclude_none=True))
            return Task(
                id="t1",
                projectId="inbox",
                title=payload.title,
            )

    MockClient._created_payload = created_payload  # type: ignore[attr-defined]
    return MockClient


class TestDurationCreateTask:
    """Duration pattern: 'создай встречу совещание завтра в 10 на 2 часа'."""

    @pytest.mark.asyncio
    async def test_duration_with_date(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "2", "часа"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        assert "совещание" in resp.text.lower()
        payload = factory._created_payload  # type: ignore[attr-defined]
        assert payload.get("startDate") is not None
        assert payload.get("dueDate") is not None
        assert payload.get("isAllDay") is False

    @pytest.mark.asyncio
    async def test_duration_without_value(self) -> None:
        """'на час' → duration_value=None, duration_unit='час' → 1 hour."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "ланч"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 12,
                    }
                },
                "duration_unit": {"value": "час"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "ланч", "завтра", "в", "12", "на", "час"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        payload = factory._created_payload  # type: ignore[attr-defined]
        assert payload.get("startDate") is not None
        assert payload.get("dueDate") is not None

    @pytest.mark.asyncio
    async def test_duration_without_date_asks_clarification(self) -> None:
        """Duration without start time → ask for time."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "duration_unit": {"value": "час"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "совещание", "на", "час"])

        resp = await handle_create_task(msg, intent_data, None, _make_update())

        assert resp.text == txt.DURATION_MISSING_START_TIME

    @pytest.mark.asyncio
    async def test_duration_half_hour(self) -> None:
        """'на полчаса' → 30 minutes."""
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "стендап"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_unit": {"value": "полчаса"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "стендап", "завтра", "в", "10", "на", "полчаса"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        assert "стендап" in resp.text.lower()


class TestRangeCreateTask:
    """Range pattern: 'создай задачу митинг с 14 до 16'."""

    @pytest.mark.asyncio
    async def test_range_basic(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "митинг"},
                "range_start": {"value": {"hour": 14}},
                "range_end": {"value": {"hour": 16}},
            }
        }
        msg = _make_message(tokens=["создай", "задачу", "митинг", "с", "14", "до", "16"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        assert "митинг" in resp.text.lower()
        payload = factory._created_payload  # type: ignore[attr-defined]
        assert payload.get("startDate") is not None
        assert payload.get("dueDate") is not None
        assert payload.get("isAllDay") is False


class TestDurationCombinations:
    """Duration + priority/recurrence/reminder."""

    @pytest.mark.asyncio
    async def test_duration_with_priority(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
                "priority": {"value": "высокий"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "2", "часа"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        assert "приоритет" in resp.text

    @pytest.mark.asyncio
    async def test_duration_with_reminder(self) -> None:
        intent_data: dict[str, Any] = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {
                    "value": {
                        "day": 1,
                        "day_is_relative": True,
                        "hour": 10,
                    }
                },
                "duration_value": {"value": 1},
                "duration_unit": {"value": "час"},
                "reminder_value": {"value": 15},
                "reminder_unit": {"value": "минут"},
            }
        }
        msg = _make_message(tokens=["создай", "встречу", "совещание", "завтра", "в", "10", "на", "час"])
        factory = _mock_client_factory()

        resp = await handle_create_task(msg, intent_data, factory, _make_update())

        assert "Добавила" in resp.text
        assert "напоминание" in resp.text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers_duration.py -v`
Expected: FAIL — handler doesn't handle duration/range yet

**Step 3: Modify handle_create_task**

In `alice_ticktick/dialogs/handlers.py`, add import at top (after existing nlp imports around line 33-42):
```python
from alice_ticktick.dialogs.nlp.duration_parser import parse_duration
```

Then in `handle_create_task`, after the slot extraction (line 356) and task_name validation (lines 358-376), but **before** the NLU date extraction (line 380), add duration/range handling:

```python
    # --- Duration / Range handling ---
    duration = parse_duration(slots.duration_value, slots.duration_unit)

    # Duration without date → ask for start time
    if duration and not slots.date:
        # Check if NLU extracted a date anyway
        nlu_check = _extract_nlu_dates(message, user_tz)
        if not nlu_check or not nlu_check.start_date:
            return Response(text=txt.DURATION_MISSING_START_TIME)
```

Then, after the existing date parsing block (after line 423), add the duration/range date computation block. The simplest approach: insert a new branch that checks for range or duration **after** dates have been parsed:

After the date parsing section and before priority parsing (before line 425), add:

```python
    # --- Compute start/end from range slots ---
    has_duration_or_range = False
    start_time_display: str | None = None
    end_time_display: str | None = None

    if slots.range_start and slots.range_end:
        now_local = datetime.datetime.now(tz=user_tz)
        try:
            parsed_rs = parse_yandex_datetime(slots.range_start, now=now_local)
            parsed_re = parse_yandex_datetime(slots.range_end, now=now_local)
            # Ensure both are datetime (with time)
            if isinstance(parsed_rs, datetime.date) and not isinstance(parsed_rs, datetime.datetime):
                parsed_rs = datetime.datetime.combine(parsed_rs, datetime.time(), tzinfo=user_tz)
            if isinstance(parsed_re, datetime.date) and not isinstance(parsed_re, datetime.datetime):
                parsed_re = datetime.datetime.combine(parsed_re, datetime.time(), tzinfo=user_tz)
            start_date_str = _format_ticktick_dt(parsed_rs)
            due_date_str = _format_ticktick_dt(parsed_re)
            is_all_day = False
            date_display = _format_date(parsed_rs, user_tz)
            start_time_display = parsed_rs.strftime("%H:%M")
            end_time_display = parsed_re.strftime("%H:%M")
            has_duration_or_range = True
        except ValueError:
            pass
    elif duration and (start_date_str or due_date_str):
        # Duration with a start datetime: compute end = start + duration
        # start_date_str is set from NLU or grammar parsing above
        source_str = start_date_str or due_date_str
        if source_str:
            # Parse back the formatted string to get datetime
            # Use the already parsed start date from NLU
            if nlu_dates and nlu_dates.start_date and isinstance(nlu_dates.start_date, datetime.datetime):
                start_dt = nlu_dates.start_date
            elif slots.date:
                now_local = datetime.datetime.now(tz=user_tz)
                parsed = parse_yandex_datetime(slots.date, now=now_local)
                start_dt = parsed if isinstance(parsed, datetime.datetime) else datetime.datetime.combine(parsed, datetime.time(), tzinfo=user_tz)
            else:
                start_dt = None

            if start_dt:
                end_dt = start_dt + duration
                start_date_str = _format_ticktick_dt(start_dt)
                due_date_str = _format_ticktick_dt(end_dt)
                is_all_day = False
                date_display = _format_date(start_dt, user_tz)
                start_time_display = start_dt.strftime("%H:%M")
                end_time_display = end_dt.strftime("%H:%M")
                has_duration_or_range = True
```

Then, in the response building section (lines 474-523), add a new block **before** the existing response logic (before line 474):

```python
    # --- Duration/range response ---
    if has_duration_or_range and start_time_display and end_time_display:
        rec_display = format_recurrence(repeat_flag)
        rem_display = format_reminder(reminder_trigger)
        priority_short = _format_priority_short(priority_value)

        if rec_display and rem_display:
            return Response(
                text=txt.TASK_CREATED_WITH_DURATION_RECURRING_AND_REMINDER.format(
                    name=task_name, date=date_display,
                    start_time=start_time_display, end_time=end_time_display,
                    recurrence=rec_display, reminder=rem_display,
                )
            )
        if rec_display:
            return Response(
                text=txt.TASK_CREATED_WITH_DURATION_RECURRING.format(
                    name=task_name, date=date_display,
                    start_time=start_time_display, end_time=end_time_display,
                    recurrence=rec_display,
                )
            )
        if rem_display:
            return Response(
                text=txt.TASK_CREATED_WITH_DURATION_AND_REMINDER.format(
                    name=task_name, date=date_display,
                    start_time=start_time_display, end_time=end_time_display,
                    reminder=rem_display,
                )
            )
        if priority_short:
            return Response(
                text=txt.TASK_CREATED_WITH_DURATION_AND_PRIORITY.format(
                    name=task_name, date=date_display,
                    start_time=start_time_display, end_time=end_time_display,
                    priority=priority_short,
                )
            )
        return Response(
            text=txt.TASK_CREATED_WITH_DURATION.format(
                name=task_name, date=date_display,
                start_time=start_time_display, end_time=end_time_display,
            )
        )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers_duration.py -v`
Expected: all PASS

**Step 5: Run full regression**

Run: `uv run pytest -v`
Expected: all existing tests still PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_duration.py
git commit -m "feat: поддержка длительности и диапазона при создании задач"
```

---

### Task 5: Update PRD

**Files:**
- Modify: `docs/PRD.md`

**Step 1: Add FR-21 after FR-15 (line ~195, before "### Фаза 5")**

Insert before line 196 (`### Фаза 5`):
```markdown
#### FR-21: Задачи с длительностью (встречи)
- **Команды:**
  - "Создай встречу [название] [дата] на [N] часов/минут" (длительность)
  - "Создай задачу [название] с [время] до [время]" (диапазон)
- **Примеры:**
  - "Создай встречу совещание завтра в 10 на 2 часа"
  - "Добавь встречу ланч завтра в 12 на час"
  - "Создай задачу митинг с 14 до 16"
- **Реализация:** расширение интента `create_task` — новые слоты `duration_value`, `duration_unit`, `range_start`, `range_end`. В TickTick API: `startDate` + `dueDate` + `isAllDay=false`
- **Уточнение:** при указании длительности без времени начала навык спрашивает: "Во сколько начинается? Скажите время."
- **Комбинации:** поддерживаются с приоритетом, повторением, напоминанием

```

**Step 2: Commit**

```bash
git add docs/PRD.md
git commit -m "docs: FR-21 — задачи с длительностью в PRD"
```

---

### Task 6: Update grammar documentation

**Files:**
- Modify: `docs/grammars/create_task.grammar`

**Step 1: Update grammar file with new patterns**

This file is reference documentation (actual grammar is in Yandex Dialogs UI). Add 3 new root lines, new slots, and new nonterminals as tested in the browser:

Add to root (3 new lines after existing 3):
```
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание|встречу)? $TaskName (на $Date) на $DurationValue $DurationUnit (с приоритетом (низкий|средний|высокий))? ($Recurrence)? (с напоминанием за $ReminderValue $ReminderUnit)?
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание|встречу)? $TaskName (на $Date) на $DurationUnit (с приоритетом (низкий|средний|высокий))? ($Recurrence)? (с напоминанием за $ReminderValue $ReminderUnit)?
    (создай|добавь|запиши|новая|поставь) (задачу|задача|напоминание|встречу)? $TaskName с $RangeStart до $RangeEnd (с приоритетом (низкий|средний|высокий))? ($Recurrence)? (с напоминанием за $ReminderValue $ReminderUnit)?
```

Also add "встречу" to existing 3 root lines: `(задачу|задача|напоминание)` → `(задачу|задача|напоминание|встречу)`.

Add to slots section:
```
    duration_value:
        source: $DurationValue
        type: YANDEX.NUMBER
    duration_unit:
        source: $DurationUnit
        type: YANDEX.STRING
    range_start:
        source: $RangeStart
        type: YANDEX.DATETIME
    range_end:
        source: $RangeEnd
        type: YANDEX.DATETIME
```

Add nonterminals:
```
$DurationValue:
    $YANDEX.NUMBER

$DurationUnit:
    час
    минута
    полчаса

$RangeStart:
    $YANDEX.DATETIME

$RangeEnd:
    $YANDEX.DATETIME
```

**Step 2: Commit**

```bash
git add docs/grammars/create_task.grammar
git commit -m "docs: грамматика create_task с длительностью и диапазоном"
```

---

### Task 7: Update VOICE_TESTING.md

**Files:**
- Modify: `docs/VOICE_TESTING.md`

**Step 1: Add section 2.2 addendum and checklist items**

In section 2.2 (create_task), after existing row 13 (line 86), add new rows:
```markdown
| 14 | «создай встречу совещание завтра в 10 на 2 часа» | name=совещание, date=завтра в 10, duration_value=2, duration_unit=часа | Добавила! "Совещание" на завтра, 10:00 до 12:00. | [ ] |
| 15 | «добавь встречу ланч завтра в 12 на час» | name=ланч, date=завтра в 12, duration_unit=час | Добавила! "Ланч" на завтра, 12:00 до 13:00. | [ ] |
| 16 | «создай встречу стендап завтра в 10 на полчаса» | name=стендап, date=завтра в 10, duration_unit=полчаса | Добавила! "Стендап" на завтра, 10:00 до 10:30. | [ ] |
| 17 | «создай задачу митинг с 14 до 16» | name=митинг, range_start=14, range_end=16 | Добавила! "Митинг" на сегодня, 14:00 до 16:00. | [ ] |
| 18 | «создай встречу на час» | name=?, duration_unit=час, date=пусто | Во сколько начинается? Скажите время. | [ ] |
| 19 | «создай встречу совещание завтра в 10 на 2 часа с напоминанием за 15 минут» | name=совещание, date=завтра в 10, duration_value=2, duration_unit=часа, reminder_value=15, reminder_unit=минут | Добавила с напоминанием | [ ] |
```

In section 2.2 expected answers, add:
```
- С длительностью: `Добавила! "..." на ..., HH:MM до HH:MM.`
- Длительность без времени: `Во сколько начинается? Скажите время.`
```

In section 2.2 slot list, add: `duration_value` (NUMBER), `duration_unit` (STRING), `range_start` (DATETIME), `range_end` (DATETIME)

In section 6 checklist, add under "### Задачи с длительностью (встречи)":
```markdown
### Задачи с длительностью (встречи)

- [ ] «создай встречу совещание завтра в 10 на 2 часа» — создана с duration
- [ ] «добавь встречу ланч завтра в 12 на час» — duration без числа
- [ ] «создай встречу стендап завтра в 10 на полчаса» — полчаса
- [ ] «создай задачу митинг с 14 до 16» — range
- [ ] «создай встречу на час» — уточняющий вопрос
- [ ] «создай встречу совещание завтра в 10 на час с напоминанием за 15 минут» — комбинация
- [ ] «создай встречу стендап завтра в 10 на полчаса каждый день» — комбинация с повторением
```

**Step 2: Commit**

```bash
git add docs/VOICE_TESTING.md
git commit -m "docs: тесты голосового тестирования для задач с длительностью"
```

---

### Task 8: Update README

**Files:**
- Modify: `README.md:19-29`

**Step 1: Add duration examples**

After the "### Создание задач" section (line 29), add a new section:
```markdown
### Задачи с длительностью (встречи)

```
создай встречу совещание завтра в 10 на 2 часа
добавь встречу ланч завтра в 12 на час
создай встречу стендап завтра в 10 на полчаса
создай задачу митинг с 14 до 16
```
```

Also add "Встречи и события с длительностью" to the "## Возможности" list (after line 17).

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: примеры задач с длительностью в README"
```

---

### Task 9: Lint, type-check, final regression

**Step 1: Run formatter and linter**

```bash
uv run ruff format .
uv run ruff check .
```

Fix any issues.

**Step 2: Run type checker**

```bash
uv run mypy alice_ticktick/
```

Fix any issues.

**Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: all PASS, no regressions.

**Step 4: Commit fixes if any**

```bash
git add -A
git commit -m "chore: lint и type fixes"
```

---

### Task 10: Create PR

**Step 1: Push branch and create PR**

```bash
git push -u origin feat/task-duration
gh pr create --title "feat: задачи с длительностью (встречи)" --body "$(cat <<'EOF'
## Summary
- Поддержка создания задач с указанием длительности ("на 2 часа") и временного диапазона ("с 14 до 16")
- Расширение интента `create_task` — новые слоты duration_value, duration_unit, range_start, range_end
- Новая NLP-функция `parse_duration` для парсинга длительности
- Новые шаблоны ответов в формате "Добавила!"
- Обновлён PRD (FR-21), README, VOICE_TESTING.md, грамматика

## Test plan
- [ ] `uv run pytest -v` — все тесты проходят
- [ ] `uv run ruff check .` — без замечаний
- [ ] `uv run mypy alice_ticktick/` — без ошибок
- [ ] После мерджа: обновить грамматику в Яндекс Диалогах
- [ ] Протестировать в текстовой консоли Яндекс Диалогов
EOF
)"
```
