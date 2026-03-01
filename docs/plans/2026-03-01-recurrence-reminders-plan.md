# Повторяющиеся задачи и напоминания — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add recurring tasks (RRULE) and reminders (TRIGGER) support to the Alice-TickTick skill via API v1 fields `repeatFlag` and `reminders`.

**Architecture:** NLU grammars capture structured slots (rec_freq, rec_interval, rec_monthday, reminder_value, reminder_unit). Server-side parsers map slot values to RRULE/TRIGGER strings. Two new intents (create_recurring_task, add_reminder) + extensions to create_task and edit_task.

**Tech Stack:** Python 3.12+, pydantic, aliceio, pytest, rapidfuzz

**Design doc:** `docs/plans/2026-03-01-recurrence-reminders-design.md`

---

## Task 1: Add repeat_flag and reminders to Pydantic models

**Files:**
- Modify: `alice_ticktick/ticktick/models.py:30-44` (Task), `:54-68` (TaskCreate), `:70-91` (TaskUpdate)
- Test: `tests/test_models.py`

**Step 1: Write failing tests for new model fields**

Add to `tests/test_models.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v -k "Repeat or Reminders"`
Expected: FAIL — fields don't exist yet.

**Step 3: Add fields to models**

In `alice_ticktick/ticktick/models.py`:

Add to `Task` class (after line 42 `parent_id`):
```python
    repeat_flag: str | None = Field(default=None, alias="repeatFlag")
    reminders: list[str] = Field(default_factory=list)
```

Add to `TaskCreate` class (after line 65 `parent_id`):
```python
    repeat_flag: str | None = Field(default=None, alias="repeatFlag")
    reminders: list[str] | None = None
```

Add to `TaskUpdate` class (after line 80 `items`):
```python
    repeat_flag: str | None = Field(default=None, alias="repeatFlag")
    reminders: list[str] | None = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add alice_ticktick/ticktick/models.py tests/test_models.py
git commit -m "feat: add repeat_flag and reminders fields to TickTick models"
```

---

## Task 2: Create recurrence parser

**Files:**
- Create: `alice_ticktick/dialogs/nlp/recurrence_parser.py`
- Create: `tests/test_recurrence_parser.py`
- Modify: `alice_ticktick/dialogs/nlp/__init__.py`

**Step 1: Write failing tests**

Create `tests/test_recurrence_parser.py`:

```python
"""Tests for recurrence NLU slot → RRULE parser."""

import pytest

from alice_ticktick.dialogs.nlp.recurrence_parser import build_rrule, format_recurrence


class TestBuildRrule:
    """Tests for build_rrule: NLU slots → RRULE string."""

    # --- Basic frequencies ---
    @pytest.mark.parametrize(
        "freq, expected",
        [
            ("день", "RRULE:FREQ=DAILY"),
            ("дня", "RRULE:FREQ=DAILY"),
            ("дней", "RRULE:FREQ=DAILY"),
            ("ежедневно", "RRULE:FREQ=DAILY"),
            ("неделю", "RRULE:FREQ=WEEKLY"),
            ("недели", "RRULE:FREQ=WEEKLY"),
            ("недель", "RRULE:FREQ=WEEKLY"),
            ("еженедельно", "RRULE:FREQ=WEEKLY"),
            ("месяц", "RRULE:FREQ=MONTHLY"),
            ("месяца", "RRULE:FREQ=MONTHLY"),
            ("месяцев", "RRULE:FREQ=MONTHLY"),
            ("ежемесячно", "RRULE:FREQ=MONTHLY"),
            ("год", "RRULE:FREQ=YEARLY"),
            ("года", "RRULE:FREQ=YEARLY"),
            ("лет", "RRULE:FREQ=YEARLY"),
            ("ежегодно", "RRULE:FREQ=YEARLY"),
        ],
    )
    def test_basic_freq(self, freq: str, expected: str) -> None:
        assert build_rrule(rec_freq=freq) == expected

    # --- Days of week ---
    @pytest.mark.parametrize(
        "freq, byday",
        [
            ("понедельник", "MO"),
            ("вторник", "TU"),
            ("среду", "WE"),
            ("среда", "WE"),
            ("четверг", "TH"),
            ("пятницу", "FR"),
            ("пятница", "FR"),
            ("субботу", "SA"),
            ("суббота", "SA"),
            ("воскресенье", "SU"),
        ],
    )
    def test_weekday(self, freq: str, byday: str) -> None:
        assert build_rrule(rec_freq=freq) == f"RRULE:FREQ=WEEKLY;BYDAY={byday}"

    def test_weekdays(self) -> None:
        assert build_rrule(rec_freq="будни") == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_weekdays_alt(self) -> None:
        assert build_rrule(rec_freq="будням") == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_weekends(self) -> None:
        assert build_rrule(rec_freq="выходные") == "RRULE:FREQ=WEEKLY;BYDAY=SA,SU"

    def test_weekends_alt(self) -> None:
        assert build_rrule(rec_freq="выходным") == "RRULE:FREQ=WEEKLY;BYDAY=SA,SU"

    # --- Interval ---
    def test_interval_days(self) -> None:
        assert build_rrule(rec_freq="дня", rec_interval=3) == "RRULE:FREQ=DAILY;INTERVAL=3"

    def test_interval_weeks(self) -> None:
        assert build_rrule(rec_freq="недели", rec_interval=2) == "RRULE:FREQ=WEEKLY;INTERVAL=2"

    def test_interval_months(self) -> None:
        assert build_rrule(rec_freq="месяца", rec_interval=6) == "RRULE:FREQ=MONTHLY;INTERVAL=6"

    # --- By monthday ---
    def test_monthday(self) -> None:
        assert build_rrule(rec_monthday=15) == "RRULE:FREQ=MONTHLY;BYMONTHDAY=15"

    def test_monthday_1st(self) -> None:
        assert build_rrule(rec_monthday=1) == "RRULE:FREQ=MONTHLY;BYMONTHDAY=1"

    # --- None / unknown ---
    def test_none_freq(self) -> None:
        assert build_rrule() is None

    def test_unknown_freq(self) -> None:
        assert build_rrule(rec_freq="кварталу") is None

    # --- Case insensitive ---
    def test_case_insensitive(self) -> None:
        assert build_rrule(rec_freq="День") == "RRULE:FREQ=DAILY"


class TestFormatRecurrence:
    """Tests for format_recurrence: RRULE → human-readable Russian."""

    @pytest.mark.parametrize(
        "rrule, expected",
        [
            ("RRULE:FREQ=DAILY", "каждый день"),
            ("RRULE:FREQ=WEEKLY", "каждую неделю"),
            ("RRULE:FREQ=MONTHLY", "каждый месяц"),
            ("RRULE:FREQ=YEARLY", "каждый год"),
            ("RRULE:FREQ=DAILY;INTERVAL=3", "каждые 3 дня"),
            ("RRULE:FREQ=WEEKLY;INTERVAL=2", "каждые 2 недели"),
            ("RRULE:FREQ=WEEKLY;BYDAY=MO", "каждый понедельник"),
            ("RRULE:FREQ=WEEKLY;BYDAY=FR", "каждую пятницу"),
            ("RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "по будням"),
            ("RRULE:FREQ=WEEKLY;BYDAY=SA,SU", "по выходным"),
            ("RRULE:FREQ=MONTHLY;BYMONTHDAY=15", "каждое 15 число"),
        ],
    )
    def test_format(self, rrule: str, expected: str) -> None:
        assert format_recurrence(rrule) == expected

    def test_unknown_rrule(self) -> None:
        assert format_recurrence("RRULE:FREQ=SECONDLY") == "повторяется"

    def test_none_returns_none(self) -> None:
        assert format_recurrence(None) is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_recurrence_parser.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement recurrence_parser.py**

Create `alice_ticktick/dialogs/nlp/recurrence_parser.py`:

```python
"""Parser for recurrence NLU slots → RRULE strings (RFC 5545)."""

from __future__ import annotations

import re

# Mapping: normalized rec_freq value → (FREQ, optional BYDAY)
_FREQ_MAP: dict[str, tuple[str, str | None]] = {
    # Basic frequencies
    "день": ("DAILY", None),
    "дня": ("DAILY", None),
    "дней": ("DAILY", None),
    "ежедневно": ("DAILY", None),
    "неделю": ("WEEKLY", None),
    "неделя": ("WEEKLY", None),
    "недели": ("WEEKLY", None),
    "недель": ("WEEKLY", None),
    "еженедельно": ("WEEKLY", None),
    "месяц": ("MONTHLY", None),
    "месяца": ("MONTHLY", None),
    "месяцев": ("MONTHLY", None),
    "ежемесячно": ("MONTHLY", None),
    "год": ("YEARLY", None),
    "года": ("YEARLY", None),
    "лет": ("YEARLY", None),
    "ежегодно": ("YEARLY", None),
    # Days of week
    "понедельник": ("WEEKLY", "MO"),
    "вторник": ("WEEKLY", "TU"),
    "среду": ("WEEKLY", "WE"),
    "среда": ("WEEKLY", "WE"),
    "четверг": ("WEEKLY", "TH"),
    "пятницу": ("WEEKLY", "FR"),
    "пятница": ("WEEKLY", "FR"),
    "субботу": ("WEEKLY", "SA"),
    "суббота": ("WEEKLY", "SA"),
    "воскресенье": ("WEEKLY", "SU"),
    # Groups
    "будни": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "будний": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "будням": ("WEEKLY", "MO,TU,WE,TH,FR"),
    "выходные": ("WEEKLY", "SA,SU"),
    "выходным": ("WEEKLY", "SA,SU"),
}

# Reverse mapping for format_recurrence
_BYDAY_TO_RU: dict[str, str] = {
    "MO": "понедельник",
    "TU": "вторник",
    "WE": "среду",
    "TH": "четверг",
    "FR": "пятницу",
    "SA": "субботу",
    "SU": "воскресенье",
}

_FREQ_TO_RU: dict[str, tuple[str, str]] = {
    # (singular "каждый X", plural base for interval)
    "DAILY": ("каждый день", "дня"),
    "WEEKLY": ("каждую неделю", "недели"),
    "MONTHLY": ("каждый месяц", "месяца"),
    "YEARLY": ("каждый год", "года"),
}


def build_rrule(
    *,
    rec_freq: str | None = None,
    rec_interval: int | None = None,
    rec_monthday: int | None = None,
) -> str | None:
    """Convert NLU recurrence slots to an RRULE string.

    Returns None if no valid recurrence could be built.
    """
    # Monthday takes priority: "каждое 15 число"
    if rec_monthday is not None:
        return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={rec_monthday}"

    if rec_freq is None:
        return None

    normalized = rec_freq.lower().strip()
    entry = _FREQ_MAP.get(normalized)
    if entry is None:
        return None

    freq, byday = entry

    parts = [f"FREQ={freq}"]
    if rec_interval is not None and rec_interval > 1:
        parts.append(f"INTERVAL={rec_interval}")
    if byday is not None:
        parts.append(f"BYDAY={byday}")

    return "RRULE:" + ";".join(parts)


def format_recurrence(rrule: str | None) -> str | None:
    """Convert an RRULE string to a human-readable Russian description.

    Returns None if rrule is None.
    """
    if rrule is None:
        return None

    # Parse RRULE components
    body = rrule.removeprefix("RRULE:")
    params: dict[str, str] = {}
    for part in body.split(";"):
        if "=" in part:
            key, val = part.split("=", 1)
            params[key] = val

    freq = params.get("FREQ")
    interval = params.get("INTERVAL")
    byday = params.get("BYDAY")
    bymonthday = params.get("BYMONTHDAY")

    if bymonthday is not None:
        return f"каждое {bymonthday} число"

    if byday is not None:
        if byday == "MO,TU,WE,TH,FR":
            return "по будням"
        if byday == "SA,SU":
            return "по выходным"
        day_name = _BYDAY_TO_RU.get(byday)
        if day_name:
            return f"каждый {day_name}" if byday in ("MO", "TU", "TH") else f"каждую {day_name}"

    if freq and freq in _FREQ_TO_RU:
        singular, plural_base = _FREQ_TO_RU[freq]
        if interval:
            return f"каждые {interval} {plural_base}"
        return singular

    return "повторяется"
```

**Step 4: Export from `__init__.py`**

Add to `alice_ticktick/dialogs/nlp/__init__.py`:

```python
from alice_ticktick.dialogs.nlp.recurrence_parser import build_rrule, format_recurrence
```

And add to `__all__`:
```python
    "build_rrule",
    "format_recurrence",
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_recurrence_parser.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/nlp/recurrence_parser.py alice_ticktick/dialogs/nlp/__init__.py tests/test_recurrence_parser.py
git commit -m "feat: recurrence parser — NLU slots to RRULE"
```

---

## Task 3: Create reminder parser

**Files:**
- Create: `alice_ticktick/dialogs/nlp/reminder_parser.py`
- Create: `tests/test_reminder_parser.py`
- Modify: `alice_ticktick/dialogs/nlp/__init__.py`

**Step 1: Write failing tests**

Create `tests/test_reminder_parser.py`:

```python
"""Tests for reminder NLU slot → TRIGGER parser."""

import pytest

from alice_ticktick.dialogs.nlp.reminder_parser import build_trigger, format_reminder


class TestBuildTrigger:
    """Tests for build_trigger: NLU slots → iCal TRIGGER string."""

    @pytest.mark.parametrize(
        "value, unit, expected",
        [
            (30, "минут", "TRIGGER:-PT30M"),
            (15, "минуты", "TRIGGER:-PT15M"),
            (1, "минуту", "TRIGGER:-PT1M"),
            (1, "час", "TRIGGER:-PT1H"),
            (2, "часа", "TRIGGER:-PT2H"),
            (24, "часов", "TRIGGER:-PT24H"),
            (1, "день", "TRIGGER:-P1D"),
            (3, "дня", "TRIGGER:-P3D"),
            (7, "дней", "TRIGGER:-P7D"),
        ],
    )
    def test_trigger(self, value: int, unit: str, expected: str) -> None:
        assert build_trigger(value, unit) == expected

    def test_zero_value(self) -> None:
        """value=0 means 'at the time of the task'."""
        assert build_trigger(0, "минут") == "TRIGGER:PT0S"

    def test_none_value(self) -> None:
        assert build_trigger(None, "минут") is None

    def test_none_unit(self) -> None:
        assert build_trigger(30, None) is None

    def test_unknown_unit(self) -> None:
        assert build_trigger(5, "секунд") is None

    def test_case_insensitive(self) -> None:
        assert build_trigger(10, "Минут") == "TRIGGER:-PT10M"


class TestFormatReminder:
    """Tests for format_reminder: TRIGGER → human-readable Russian."""

    @pytest.mark.parametrize(
        "trigger, expected",
        [
            ("TRIGGER:-PT30M", "за 30 минут"),
            ("TRIGGER:-PT1M", "за 1 минуту"),
            ("TRIGGER:-PT5M", "за 5 минут"),
            ("TRIGGER:-PT1H", "за 1 час"),
            ("TRIGGER:-PT2H", "за 2 часа"),
            ("TRIGGER:-PT5H", "за 5 часов"),
            ("TRIGGER:-P1D", "за 1 день"),
            ("TRIGGER:-P3D", "за 3 дня"),
            ("TRIGGER:-P7D", "за 7 дней"),
            ("TRIGGER:PT0S", "в момент задачи"),
        ],
    )
    def test_format(self, trigger: str, expected: str) -> None:
        assert format_reminder(trigger) == expected

    def test_unknown_trigger(self) -> None:
        assert format_reminder("TRIGGER:UNKNOWN") == "напоминание"

    def test_none(self) -> None:
        assert format_reminder(None) is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reminder_parser.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement reminder_parser.py**

Create `alice_ticktick/dialogs/nlp/reminder_parser.py`:

```python
"""Parser for reminder NLU slots → iCal TRIGGER strings."""

from __future__ import annotations

import re

_UNIT_MAP: dict[str, str] = {
    # minutes
    "минуту": "M",
    "минута": "M",
    "минуты": "M",
    "минут": "M",
    # hours
    "час": "H",
    "часа": "H",
    "часов": "H",
    # days
    "день": "D",
    "дня": "D",
    "дней": "D",
}

# For pluralization in format_reminder
_MINUTE_FORMS = ("минуту", "минуты", "минут")  # 1, 2-4, 5+
_HOUR_FORMS = ("час", "часа", "часов")
_DAY_FORMS = ("день", "дня", "дней")

_TRIGGER_RE = re.compile(
    r"TRIGGER:(-?)P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?|(\d+)D)"
)


def build_trigger(value: int | None, unit: str | None) -> str | None:
    """Convert NLU reminder slots to an iCal TRIGGER string.

    Returns None if value or unit is missing/unknown.
    """
    if value is None or unit is None:
        return None

    if value == 0:
        return "TRIGGER:PT0S"

    code = _UNIT_MAP.get(unit.lower().strip())
    if code is None:
        return None

    if code == "D":
        return f"TRIGGER:-P{value}D"
    return f"TRIGGER:-PT{value}{code}"


def _pluralize(n: int, forms: tuple[str, str, str]) -> str:
    """Russian pluralization: 1 минуту, 2 минуты, 5 минут."""
    abs_n = abs(n)
    if abs_n % 10 == 1 and abs_n % 100 != 11:
        return f"{n} {forms[0]}"
    if abs_n % 10 in (2, 3, 4) and abs_n % 100 not in (12, 13, 14):
        return f"{n} {forms[1]}"
    return f"{n} {forms[2]}"


def format_reminder(trigger: str | None) -> str | None:
    """Convert an iCal TRIGGER string to a human-readable Russian description.

    Returns None if trigger is None.
    """
    if trigger is None:
        return None

    if trigger == "TRIGGER:PT0S":
        return "в момент задачи"

    m = _TRIGGER_RE.match(trigger)
    if not m:
        return "напоминание"

    _sign, hours, minutes, _seconds, days = m.groups()

    if days:
        return f"за {_pluralize(int(days), _DAY_FORMS)}"
    if hours:
        return f"за {_pluralize(int(hours), _HOUR_FORMS)}"
    if minutes:
        return f"за {_pluralize(int(minutes), _MINUTE_FORMS)}"

    return "напоминание"
```

**Step 4: Export from `__init__.py`**

Add to `alice_ticktick/dialogs/nlp/__init__.py`:

```python
from alice_ticktick.dialogs.nlp.reminder_parser import build_trigger, format_reminder
```

And add to `__all__`:
```python
    "build_trigger",
    "format_reminder",
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reminder_parser.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/nlp/reminder_parser.py alice_ticktick/dialogs/nlp/__init__.py tests/test_reminder_parser.py
git commit -m "feat: reminder parser — NLU slots to TRIGGER"
```

---

## Task 4: Add new intent constants, slot dataclasses, and extractors

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py`
- Test: `tests/test_handlers.py` (extractors tested indirectly via handler tests in Task 6+)

**Step 1: Add intent constants**

In `alice_ticktick/dialogs/intents.py`, after line 24 (`DELETE_CHECKLIST_ITEM`):

```python
CREATE_RECURRING_TASK = "create_recurring_task"
ADD_REMINDER = "add_reminder"
```

Add to `ALL_INTENTS` frozenset (after `DELETE_CHECKLIST_ITEM`):

```python
        CREATE_RECURRING_TASK,
        ADD_REMINDER,
```

**Step 2: Extend CreateTaskSlots with recurrence/reminder fields**

Replace the `CreateTaskSlots` dataclass (lines 45-53) with:

```python
@dataclass(frozen=True, slots=True)
class CreateTaskSlots:
    """Extracted slots for create_task intent."""

    task_name: str | None = None
    date: YandexDateTime | None = None
    priority: str | None = None
    project_name: str | None = None
    rec_freq: str | None = None
    rec_interval: int | None = None
    rec_monthday: int | None = None
    reminder_value: int | None = None
    reminder_unit: str | None = None
```

**Step 3: Update extract_create_task_slots**

Replace the function (lines 102-109) with:

```python
def extract_create_task_slots(intent_data: dict[str, Any]) -> CreateTaskSlots:
    """Extract slots from create_task intent."""
    return CreateTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        date=_get_slot_value(intent_data, "date"),
        priority=_get_slot_value(intent_data, "priority"),
        project_name=_get_slot_value(intent_data, "project_name"),
        rec_freq=_get_slot_value(intent_data, "rec_freq"),
        rec_interval=_as_int(_get_slot_value(intent_data, "rec_interval")),
        rec_monthday=_as_int(_get_slot_value(intent_data, "rec_monthday")),
        reminder_value=_as_int(_get_slot_value(intent_data, "reminder_value")),
        reminder_unit=_get_slot_value(intent_data, "reminder_unit"),
    )
```

**Step 4: Add `_as_int` helper**

After `_get_slot_value` (line 99):

```python
def _as_int(value: Any) -> int | None:
    """Coerce a slot value to int, or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
```

**Step 5: Add new slot dataclasses**

After `DeleteChecklistItemSlots` (after line 195):

```python
@dataclass(frozen=True, slots=True)
class CreateRecurringTaskSlots:
    """Extracted slots for create_recurring_task intent."""

    task_name: str | None = None
    rec_freq: str | None = None
    rec_interval: int | None = None
    rec_monthday: int | None = None


@dataclass(frozen=True, slots=True)
class AddReminderSlots:
    """Extracted slots for add_reminder intent."""

    task_name: str | None = None
    reminder_value: int | None = None
    reminder_unit: str | None = None
```

**Step 6: Add new extractors**

After `extract_delete_checklist_item_slots`:

```python
def extract_create_recurring_task_slots(
    intent_data: dict[str, Any],
) -> CreateRecurringTaskSlots:
    """Extract slots from create_recurring_task intent."""
    return CreateRecurringTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        rec_freq=_get_slot_value(intent_data, "rec_freq"),
        rec_interval=_as_int(_get_slot_value(intent_data, "rec_interval")),
        rec_monthday=_as_int(_get_slot_value(intent_data, "rec_monthday")),
    )


def extract_add_reminder_slots(intent_data: dict[str, Any]) -> AddReminderSlots:
    """Extract slots from add_reminder intent."""
    return AddReminderSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        reminder_value=_as_int(_get_slot_value(intent_data, "reminder_value")),
        reminder_unit=_get_slot_value(intent_data, "reminder_unit"),
    )
```

**Step 7: Extend EditTaskSlots**

Replace `EditTaskSlots` dataclass (lines 76-85) with:

```python
@dataclass(frozen=True, slots=True)
class EditTaskSlots:
    """Extracted slots for edit_task intent."""

    task_name: str | None = None
    new_date: YandexDateTime | None = None
    new_end_date: YandexDateTime | None = None
    new_priority: str | None = None
    new_name: str | None = None
    new_project: str | None = None
    rec_freq: str | None = None
    rec_interval: int | None = None
    rec_monthday: int | None = None
    reminder_value: int | None = None
    reminder_unit: str | None = None
    remove_recurrence: bool = False
    remove_reminder: bool = False
```

**Step 8: Update extract_edit_task_slots**

Replace the function (lines 133-142) with:

```python
def extract_edit_task_slots(intent_data: dict[str, Any]) -> EditTaskSlots:
    """Extract slots from edit_task intent."""
    return EditTaskSlots(
        task_name=_get_slot_value(intent_data, "task_name"),
        new_date=_get_slot_value(intent_data, "new_date"),
        new_end_date=_get_slot_value(intent_data, "new_end_date"),
        new_priority=_get_slot_value(intent_data, "new_priority"),
        new_name=_get_slot_value(intent_data, "new_name"),
        new_project=_get_slot_value(intent_data, "new_project"),
        rec_freq=_get_slot_value(intent_data, "rec_freq"),
        rec_interval=_as_int(_get_slot_value(intent_data, "rec_interval")),
        rec_monthday=_as_int(_get_slot_value(intent_data, "rec_monthday")),
        reminder_value=_as_int(_get_slot_value(intent_data, "reminder_value")),
        reminder_unit=_get_slot_value(intent_data, "reminder_unit"),
        remove_recurrence=_get_slot_value(intent_data, "remove_recurrence") is not None,
        remove_reminder=_get_slot_value(intent_data, "remove_reminder") is not None,
    )
```

**Step 9: Run existing tests to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 10: Commit**

```bash
git add alice_ticktick/dialogs/intents.py
git commit -m "feat: intent constants, slots, extractors for recurrence/reminders"
```

---

## Task 5: Add response templates

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py`

**Step 1: Add response constants**

After line 38 (`CREATE_ERROR`), add:

```python
# Create task with recurrence
TASK_CREATED_RECURRING = 'Готово! Задача "{name}" создана, {recurrence}.'
TASK_CREATED_WITH_REMINDER = 'Готово! Задача "{name}" создана с напоминанием {reminder}.'
TASK_CREATED_RECURRING_WITH_REMINDER = (
    'Готово! Задача "{name}" создана, {recurrence}, напоминание {reminder}.'
)
```

After line 68 (`EDIT_ERROR`), add:

```python
# Recurrence/reminder edit
RECURRENCE_UPDATED = 'Повторение задачи "{name}" изменено: {recurrence}.'
RECURRENCE_REMOVED = 'Повторение задачи "{name}" убрано.'
REMINDER_UPDATED = 'Напоминание задачи "{name}" изменено: {reminder}.'
REMINDER_REMOVED = 'Напоминание задачи "{name}" убрано.'
```

After line 98 (or after CHECKLIST section), add:

```python
# Add reminder to existing task
REMINDER_ADDED = 'Напоминание {reminder} добавлено к задаче "{name}".'
REMINDER_TASK_REQUIRED = "К какой задаче добавить напоминание?"
REMINDER_VALUE_REQUIRED = "За сколько напомнить? Скажите, например, «за 30 минут» или «за час»."
REMINDER_PARSE_ERROR = "Не поняла время напоминания. Скажите, например, «за 30 минут» или «за час»."
REMINDER_ERROR = "Не удалось добавить напоминание. Попробуйте ещё раз."
```

**Step 2: Update HELP text**

Replace the HELP constant (lines 9-21) with:

```python
HELP = (
    "Я умею:\n"
    "- Создать: «создай задачу купить молоко на завтра»\n"
    "- Повторяющуюся: «создай задачу каждый понедельник»\n"
    "- С напоминанием: «создай задачу с напоминанием за час»\n"
    "- Показать: «что на сегодня?»\n"
    "- Просроченные: «какие задачи просрочены?»\n"
    "- Найти: «найди задачу про отчёт»\n"
    "- Изменить: «перенеси задачу на завтра»\n"
    "- Удалить: «удали задачу купить молоко»\n"
    "- Завершить: «отметь задачу купить молоко»\n"
    "- Напоминание: «напомни о задаче за 30 минут»\n"
    "- Чеклист: «добавь пункт в чеклист задачи»"
)
```

**Step 3: Run existing tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS (response constants are just strings, used in later tasks).

**Step 4: Commit**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: response templates for recurrence and reminders"
```

---

## Task 6: Extend handle_create_task with recurrence and reminder support

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py` — `handle_create_task` function (lines 273-394)
- Test: `tests/test_handlers.py`

**Step 1: Write failing tests for create_task with recurrence**

Add to `tests/test_handlers.py`:

```python
class TestHandleCreateTaskRecurrence:
    """Tests for create_task with recurrence slots."""

    @pytest.mark.asyncio
    async def test_create_daily_recurring(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "зарядка"},
                "rec_freq": {"value": "день"},
            }
        }
        message = _make_message(command="создай задачу зарядка каждый день")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "зарядка" in response.text
        assert "создана" in response.text
        # Verify repeatFlag was passed
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=DAILY"

    @pytest.mark.asyncio
    async def test_create_weekly_monday(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "стендап"},
                "rec_freq": {"value": "понедельник"},
            }
        }
        message = _make_message(command="создай задачу стендап каждый понедельник")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "стендап" in response.text
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=WEEKLY;BYDAY=MO"

    @pytest.mark.asyncio
    async def test_create_with_interval(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "полив цветов"},
                "rec_freq": {"value": "дня"},
                "rec_interval": {"value": 3},
            }
        }
        message = _make_message(command="создай задачу полив цветов каждые 3 дня")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=DAILY;INTERVAL=3"

    @pytest.mark.asyncio
    async def test_create_with_reminder(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "встреча"},
                "reminder_value": {"value": 30},
                "reminder_unit": {"value": "минут"},
            }
        }
        message = _make_message(command="создай задачу встреча с напоминанием за 30 минут")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "встреча" in response.text
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.reminders == ["TRIGGER:-PT30M"]

    @pytest.mark.asyncio
    async def test_create_with_recurrence_and_reminder(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "зарядка"},
                "rec_freq": {"value": "день"},
                "reminder_value": {"value": 1},
                "reminder_unit": {"value": "час"},
            }
        }
        message = _make_message(command="создай задачу зарядка каждый день с напоминанием за час")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=DAILY"
        assert payload.reminders == ["TRIGGER:-PT1H"]

    @pytest.mark.asyncio
    async def test_create_without_recurrence_no_repeat_flag(self, mock_client_class: type) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "обычная задача"},
            }
        }
        message = _make_message(command="создай задачу обычная задача")
        response = await handle_create_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag is None
        assert payload.reminders is None
```

NOTE: These tests require a `mock_client_class` fixture. Check how existing tests mock the TickTick client and follow the same pattern. The fixture should capture `create_task` calls and their payload arguments.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py -v -k "Recurrence"`
Expected: FAIL — new imports and test methods don't match handler code yet.

**Step 3: Extend handle_create_task**

In `alice_ticktick/dialogs/handlers.py`, add imports at the top:

```python
from alice_ticktick.dialogs.nlp import (
    build_rrule,
    build_trigger,
    find_best_match,
    find_matches,
    format_recurrence,
    format_reminder,
    parse_priority,
    parse_yandex_datetime,
)
```

In `handle_create_task`, after the priority parsing block (after line 345 `priority_value = TaskPriority(priority_raw)`) and before the API call block, add:

```python
    # Parse recurrence
    repeat_flag = build_rrule(
        rec_freq=slots.rec_freq,
        rec_interval=slots.rec_interval,
        rec_monthday=slots.rec_monthday,
    )

    # Parse reminder
    reminder_trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
    reminders_list: list[str] | None = [reminder_trigger] if reminder_trigger else None
```

Update the `TaskCreate` payload construction to include the new fields:

```python
            payload = TaskCreate(
                title=task_name,
                projectId=project_id,
                priority=priority_value,
                startDate=start_date_str,
                dueDate=due_date_str,
                isAllDay=is_all_day,
                repeat_flag=repeat_flag,
                reminders=reminders_list,
            )
```

Update the response block to include recurrence/reminder info. Replace the response logic (lines 377-394) with:

```python
    # Build response with recurrence/reminder info
    rec_display = format_recurrence(repeat_flag)
    rem_display = format_reminder(reminder_trigger)

    base_name = task_name

    if rec_display and rem_display:
        return Response(
            text=txt.TASK_CREATED_RECURRING_WITH_REMINDER.format(
                name=base_name, recurrence=rec_display, reminder=rem_display
            )
        )
    if rec_display:
        return Response(text=txt.TASK_CREATED_RECURRING.format(name=base_name, recurrence=rec_display))
    if rem_display:
        return Response(text=txt.TASK_CREATED_WITH_REMINDER.format(name=base_name, reminder=rem_display))

    if project_name_display:
        if date_display:
            return Response(
                text=txt.TASK_CREATED_IN_PROJECT_WITH_DATE.format(
                    name=task_name, project=project_name_display, date=date_display
                )
            )
        return Response(
            text=txt.TASK_CREATED_IN_PROJECT.format(name=task_name, project=project_name_display)
        )
    if date_display:
        return Response(
            text=txt.TASK_CREATED_WITH_DATE.format(name=task_name, date=date_display)
        )
    return Response(text=txt.TASK_CREATED.format(name=slots.task_name))
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "feat: recurrence and reminder support in create_task handler"
```

---

## Task 7: Add handle_create_recurring_task handler

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers.py`

**Step 1: Write failing tests**

Add to `tests/test_handlers.py`:

```python
class TestHandleCreateRecurringTask:
    """Tests for create_recurring_task intent ('напоминай каждый...')."""

    @pytest.mark.asyncio
    async def test_create_recurring_delegates(self, mock_client_class: type) -> None:
        """create_recurring_task delegates to handle_create_task."""
        intent_data = {
            "slots": {
                "task_name": {"value": "проверить отчёт"},
                "rec_freq": {"value": "понедельник"},
            }
        }
        message = _make_message(command="напоминай каждый понедельник проверить отчёт")
        response = await handle_create_recurring_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "проверить отчёт" in response.text
        call_args = mock_client_class.instance.create_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=WEEKLY;BYDAY=MO"

    @pytest.mark.asyncio
    async def test_create_recurring_no_auth(self) -> None:
        intent_data = {"slots": {"task_name": {"value": "тест"}}}
        message = _make_message(access_token=None)
        response = await handle_create_recurring_task(message, intent_data)
        assert "привязать" in response.text.lower()

    @pytest.mark.asyncio
    async def test_create_recurring_no_name(self, mock_client_class: type) -> None:
        intent_data = {"slots": {"rec_freq": {"value": "день"}}}
        message = _make_message()
        response = await handle_create_recurring_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "назвать" in response.text.lower() or "название" in response.text.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py -v -k "RecurringTask"`
Expected: FAIL — function doesn't exist.

**Step 3: Implement handle_create_recurring_task**

In `alice_ticktick/dialogs/handlers.py`, add after `handle_create_task`:

```python
async def handle_create_recurring_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_recurring_task intent ('напоминай каждый...')."""
    from alice_ticktick.dialogs.intents import extract_create_recurring_task_slots

    slots = extract_create_recurring_task_slots(intent_data)

    # Delegate to create_task with recurrence slots mapped
    create_intent_data: dict[str, Any] = {"slots": {}}
    if slots.task_name:
        create_intent_data["slots"]["task_name"] = {"value": slots.task_name}
    if slots.rec_freq:
        create_intent_data["slots"]["rec_freq"] = {"value": slots.rec_freq}
    if slots.rec_interval is not None:
        create_intent_data["slots"]["rec_interval"] = {"value": slots.rec_interval}
    if slots.rec_monthday is not None:
        create_intent_data["slots"]["rec_monthday"] = {"value": slots.rec_monthday}

    return await handle_create_task(
        message,
        create_intent_data,
        ticktick_client_factory=ticktick_client_factory,
        event_update=event_update,
    )
```

**Step 4: Add route in router.py**

In `alice_ticktick/dialogs/router.py`, add import:

```python
from alice_ticktick.dialogs.handlers import handle_create_recurring_task
from alice_ticktick.dialogs.intents import CREATE_RECURRING_TASK
```

Add route BEFORE the `on_create_task` handler (before `@router.message(IntentFilter(CREATE_TASK))`):

```python
@router.message(IntentFilter(CREATE_RECURRING_TASK))
async def on_create_recurring_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_recurring_task intent."""
    return await handle_create_recurring_task(message, intent_data, event_update=event_update)
```

**Step 5: Run tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "feat: handle_create_recurring_task handler + route"
```

---

## Task 8: Add handle_add_reminder handler

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers.py`

**Step 1: Write failing tests**

Add to `tests/test_handlers.py`:

```python
class TestHandleAddReminder:
    """Tests for add_reminder intent ('напомни о задаче X за час')."""

    @pytest.mark.asyncio
    async def test_add_reminder_success(self, mock_client_class: type) -> None:
        mock_client_class.instance.get_inbox_tasks.return_value = [
            _make_task(title="Встреча с клиентом"),
        ]
        # Mock get_projects to return empty list (no project tasks)
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "встреча"},
                "reminder_value": {"value": 30},
                "reminder_unit": {"value": "минут"},
            }
        }
        message = _make_message(command="напомни о задаче встреча за 30 минут")
        response = await handle_add_reminder(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "напоминание" in response.text.lower()
        assert "30 минут" in response.text

    @pytest.mark.asyncio
    async def test_add_reminder_no_auth(self) -> None:
        intent_data = {"slots": {"task_name": {"value": "тест"}}}
        message = _make_message(access_token=None)
        response = await handle_add_reminder(message, intent_data)
        assert "привязать" in response.text.lower()

    @pytest.mark.asyncio
    async def test_add_reminder_no_task_name(self, mock_client_class: type) -> None:
        intent_data = {"slots": {"reminder_value": {"value": 30}, "reminder_unit": {"value": "минут"}}}
        message = _make_message()
        response = await handle_add_reminder(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert response.text == txt.REMINDER_TASK_REQUIRED

    @pytest.mark.asyncio
    async def test_add_reminder_no_value(self, mock_client_class: type) -> None:
        intent_data = {"slots": {"task_name": {"value": "встреча"}}}
        message = _make_message()
        response = await handle_add_reminder(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert response.text == txt.REMINDER_VALUE_REQUIRED

    @pytest.mark.asyncio
    async def test_add_reminder_task_not_found(self, mock_client_class: type) -> None:
        mock_client_class.instance.get_inbox_tasks.return_value = []
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "несуществующая"},
                "reminder_value": {"value": 30},
                "reminder_unit": {"value": "минут"},
            }
        }
        message = _make_message()
        response = await handle_add_reminder(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "не найдена" in response.text.lower()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py -v -k "AddReminder"`
Expected: FAIL — function doesn't exist.

**Step 3: Implement handle_add_reminder**

In `alice_ticktick/dialogs/handlers.py`:

```python
async def handle_add_reminder(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle add_reminder intent ('напомни о задаче X за Y')."""
    from alice_ticktick.dialogs.intents import extract_add_reminder_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_add_reminder_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.REMINDER_TASK_REQUIRED)

    if slots.reminder_value is None or slots.reminder_unit is None:
        return Response(text=txt.REMINDER_VALUE_REQUIRED)

    trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
    if trigger is None:
        return Response(text=txt.REMINDER_PARSE_ERROR)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)

            active_tasks = [t for t in all_tasks if t.status == 0]
            if not active_tasks:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            titles = [t.title for t in active_tasks]
            match_result = find_best_match(slots.task_name, titles)
            if match_result is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            best_match, match_idx = match_result
            matched_task = active_tasks[match_idx]

            # Merge with existing reminders
            existing_reminders = list(matched_task.reminders)
            if trigger not in existing_reminders:
                existing_reminders.append(trigger)

            payload = TaskUpdate(
                id=matched_task.id,
                projectId=matched_task.project_id,
                reminders=existing_reminders,
            )
            await client.update_task(payload)
            _invalidate_task_cache()
    except Exception:
        logger.exception("Failed to add reminder")
        return Response(text=txt.REMINDER_ERROR)

    rem_display = format_reminder(trigger) or ""
    return Response(text=txt.REMINDER_ADDED.format(reminder=rem_display, name=best_match))
```

**Step 4: Add route in router.py**

Add import:
```python
from alice_ticktick.dialogs.handlers import handle_add_reminder
from alice_ticktick.dialogs.intents import ADD_REMINDER
```

Add route BEFORE the `on_create_task` handler:

```python
@router.message(IntentFilter(ADD_REMINDER))
async def on_add_reminder(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle add_reminder intent."""
    return await handle_add_reminder(message, intent_data, event_update=event_update)
```

**Step 5: Run tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "feat: handle_add_reminder handler + route"
```

---

## Task 9: Extend handle_edit_task with recurrence/reminder edit and remove

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py` — `handle_edit_task` function
- Test: `tests/test_handlers.py`

**Step 1: Write failing tests**

Add to `tests/test_handlers.py`:

```python
class TestHandleEditTaskRecurrence:
    """Tests for edit_task with recurrence/reminder changes."""

    @pytest.mark.asyncio
    async def test_edit_add_recurrence(self, mock_client_class: type) -> None:
        mock_client_class.instance.get_inbox_tasks.return_value = [
            _make_task(title="Зарядка"),
        ]
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "зарядка"},
                "rec_freq": {"value": "день"},
            }
        }
        message = _make_message(command="поменяй повторение задачи зарядка на каждый день")
        response = await handle_edit_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "повторение" in response.text.lower() or "обновлена" in response.text.lower()
        call_args = mock_client_class.instance.update_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == "RRULE:FREQ=DAILY"

    @pytest.mark.asyncio
    async def test_edit_remove_recurrence(self, mock_client_class: type) -> None:
        task = _make_task(title="Зарядка")
        task.repeat_flag = "RRULE:FREQ=DAILY"
        mock_client_class.instance.get_inbox_tasks.return_value = [task]
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "зарядка"},
                "remove_recurrence": {"value": "повторение"},
            }
        }
        message = _make_message(command="убери повторение задачи зарядка")
        response = await handle_edit_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        assert "убрано" in response.text.lower() or "обновлена" in response.text.lower()
        call_args = mock_client_class.instance.update_task.call_args
        payload = call_args[0][0]
        assert payload.repeat_flag == ""

    @pytest.mark.asyncio
    async def test_edit_add_reminder(self, mock_client_class: type) -> None:
        mock_client_class.instance.get_inbox_tasks.return_value = [
            _make_task(title="Встреча"),
        ]
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "встреча"},
                "reminder_value": {"value": 30},
                "reminder_unit": {"value": "минут"},
            }
        }
        message = _make_message(command="поставь напоминание задачи встреча за 30 минут")
        response = await handle_edit_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        call_args = mock_client_class.instance.update_task.call_args
        payload = call_args[0][0]
        assert payload.reminders == ["TRIGGER:-PT30M"]

    @pytest.mark.asyncio
    async def test_edit_remove_reminder(self, mock_client_class: type) -> None:
        task = _make_task(title="Встреча")
        task.reminders = ["TRIGGER:-PT30M"]
        mock_client_class.instance.get_inbox_tasks.return_value = [task]
        mock_client_class.instance.get_projects.return_value = []

        intent_data = {
            "slots": {
                "task_name": {"value": "встреча"},
                "remove_reminder": {"value": "напоминание"},
            }
        }
        message = _make_message(command="убери напоминание задачи встреча")
        response = await handle_edit_task(
            message, intent_data, ticktick_client_factory=mock_client_class
        )
        call_args = mock_client_class.instance.update_task.call_args
        payload = call_args[0][0]
        assert payload.reminders == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py -v -k "EditTaskRecurrence"`
Expected: FAIL — handler doesn't handle these slots yet.

**Step 3: Extend handle_edit_task**

In `handle_edit_task`, after the `has_project` check (after line 616), add:

```python
    has_recurrence = slots.rec_freq is not None or slots.rec_monthday is not None
    has_reminder = slots.reminder_value is not None and slots.reminder_unit is not None
    has_remove_recurrence = slots.remove_recurrence
    has_remove_reminder = slots.remove_reminder
```

Update the "no changes" check to include new fields:

```python
    if (
        not has_date
        and not has_priority
        and not has_name
        and not has_project
        and not has_recurrence
        and not has_reminder
        and not has_remove_recurrence
        and not has_remove_reminder
    ):
        return Response(text=txt.EDIT_NO_CHANGES)
```

After building `new_priority_value` and before the project resolution block, add:

```python
    # Build recurrence
    new_repeat_flag: str | None = None
    if has_remove_recurrence:
        new_repeat_flag = ""  # empty string = remove
    elif has_recurrence:
        new_repeat_flag = build_rrule(
            rec_freq=slots.rec_freq,
            rec_interval=slots.rec_interval,
            rec_monthday=slots.rec_monthday,
        )

    # Build reminder
    new_reminders: list[str] | None = None
    if has_remove_reminder:
        new_reminders = []  # empty list = remove
    elif has_reminder:
        trigger = build_trigger(slots.reminder_value, slots.reminder_unit)
        if trigger:
            new_reminders = [trigger]
```

Update the "at least one field parsed" check:

```python
    if (
        new_title is None
        and new_due_date is None
        and new_priority_value is None
        and target_project_id is None
        and new_repeat_flag is None
        and new_reminders is None
    ):
```

Add new fields to the `TaskUpdate` payload:

```python
    payload = TaskUpdate(
        id=matched_task.id,
        projectId=target_project_id or matched_task.project_id,
        title=new_title,
        priority=new_priority_value,
        startDate=new_start_date,
        dueDate=new_due_date,
        isAllDay=new_is_all_day,
        repeat_flag=new_repeat_flag,
        reminders=new_reminders,
    )
```

Update response logic before the generic `EDIT_SUCCESS` to add specific messages:

```python
    # Specific messages for recurrence/reminder changes
    if has_remove_recurrence and new_repeat_flag == "":
        return Response(text=txt.RECURRENCE_REMOVED.format(name=best_match))
    if has_remove_reminder and new_reminders == []:
        return Response(text=txt.REMINDER_REMOVED.format(name=best_match))
    if has_recurrence and new_repeat_flag:
        rec_display = format_recurrence(new_repeat_flag)
        return Response(text=txt.RECURRENCE_UPDATED.format(name=best_match, recurrence=rec_display))
    if has_reminder and new_reminders:
        rem_display = format_reminder(new_reminders[0])
        return Response(text=txt.REMINDER_UPDATED.format(name=best_match, reminder=rem_display))
```

**Step 4: Run tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "feat: recurrence/reminder edit and remove in edit_task handler"
```

---

## Task 10: Update NLU grammars (docs) and tests.yaml

**Files:**
- Modify: `docs/grammars/create_task.grammar`
- Modify: `docs/grammars/edit_task.grammar`
- Create: `docs/grammars/create_recurring_task.grammar`
- Create: `docs/grammars/add_reminder.grammar`
- Modify: `docs/grammars/tests.yaml`
- Modify: `docs/grammars/README.md`

**Step 1: Update create_task.grammar**

Replace contents of `docs/grammars/create_task.grammar` with the new grammar from the design doc (section 1.1).

**Step 2: Update edit_task.grammar**

Add the new patterns from design doc (section 1.4) to the existing grammar.

**Step 3: Create create_recurring_task.grammar**

Write the grammar from design doc (section 1.2).

**Step 4: Create add_reminder.grammar**

Write the grammar from design doc (section 1.3).

**Step 5: Update tests.yaml**

Add test cases for:
- `create_task` with recurrence: positive examples with "каждый день", "каждые 3 дня", "с напоминанием за час"
- `create_recurring_task`: positive examples with "напоминай каждый понедельник..."
- `add_reminder`: positive examples with "напомни о задаче за 30 минут"
- `edit_task` with recurrence/reminder: positive examples

**Step 6: Update README.md**

Add `create_recurring_task` and `add_reminder` to the intents table.

**Step 7: Commit**

```bash
git add docs/grammars/
git commit -m "docs: NLU grammars for recurrence and reminder intents"
```

---

## Task 11: Run full test suite, linting, type checking

**Step 1: Run tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 2: Run linting**

Run: `uv run ruff check .`
Expected: No errors. Fix any issues.

**Step 3: Run formatting**

Run: `uv run ruff format .`

**Step 4: Run type checking**

Run: `uv run mypy alice_ticktick/`
Expected: No errors. Fix any issues.

**Step 5: Commit any fixes**

```bash
git add -u
git commit -m "fix: lint and type check fixes"
```

---

## Summary

| Task | Description | Est. Tests |
|------|-------------|-----------|
| 1 | Pydantic models: repeat_flag, reminders | ~10 |
| 2 | recurrence_parser.py (build_rrule, format_recurrence) | ~25 |
| 3 | reminder_parser.py (build_trigger, format_reminder) | ~15 |
| 4 | Intents: constants, slots, extractors | 0 (tested via handlers) |
| 5 | Response templates | 0 (string constants) |
| 6 | handle_create_task extension | ~6 |
| 7 | handle_create_recurring_task | ~3 |
| 8 | handle_add_reminder | ~5 |
| 9 | handle_edit_task extension | ~4 |
| 10 | NLU grammars (docs) | 0 (manual Yandex) |
| 11 | Full test suite + lint + types | 0 (verification) |

**Total new tests: ~68**

After completing all tasks, manually update Yandex Dialogs:
1. Update create_task grammar
2. Update edit_task grammar
3. Create create_recurring_task intent
4. Create add_reminder intent
5. Publish draft
