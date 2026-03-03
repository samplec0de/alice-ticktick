# FR-15: Фильтрация задач по приоритету — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Расширить интент `list_tasks` слотом `priority` для фильтрации задач по приоритету в комбинации с датой.

**Architecture:** Добавляем слот `priority` в `ListTasksSlots`, фильтруем задачи client-side после получения из API. Новые шаблоны ответов с указанием приоритета. Грамматику NLU нужно обновить в Яндекс Диалогах через браузер.

**Tech Stack:** Python, aliceio, pytest, rapidfuzz (parse_priority)

---

### Task 1: Расширить ListTasksSlots и extract_list_tasks_slots

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py:68-73` (ListTasksSlots)
- Modify: `alice_ticktick/dialogs/intents.py:154-158` (extract_list_tasks_slots)
- Test: `tests/test_intents.py:90-103` (TestListTasksSlots)

**Step 1: Написать failing-тест**

В `tests/test_intents.py`, в класс `TestListTasksSlots` добавить:

```python
def test_with_priority(self) -> None:
    data: dict[str, Any] = {
        "slots": {
            "priority": {"type": "YANDEX.STRING", "value": "высокий"},
        },
    }
    slots = extract_list_tasks_slots(data)
    assert slots.priority == "высокий"

def test_with_date_and_priority(self) -> None:
    data: dict[str, Any] = {
        "slots": {
            "date": {"type": "YANDEX.DATETIME", "value": {"day": 5, "month": 3}},
            "priority": {"type": "YANDEX.STRING", "value": "срочный"},
        },
    }
    slots = extract_list_tasks_slots(data)
    assert slots.date == {"day": 5, "month": 3}
    assert slots.priority == "срочный"

def test_no_priority(self) -> None:
    data: dict[str, Any] = {"slots": {}}
    slots = extract_list_tasks_slots(data)
    assert slots.priority is None
```

**Step 2: Запустить тест, убедиться что он падает**

Run: `uv run pytest tests/test_intents.py::TestListTasksSlots -v`
Expected: FAIL — `ListTasksSlots` не имеет поля `priority`

**Step 3: Реализовать**

В `alice_ticktick/dialogs/intents.py`:

1. Добавить поле `priority` в `ListTasksSlots` (строка 72):

```python
@dataclass(frozen=True, slots=True)
class ListTasksSlots:
    """Extracted slots for list_tasks intent."""

    date: YandexDateTime | None = None
    priority: str | None = None
```

2. Обновить `extract_list_tasks_slots` (строка 154):

```python
def extract_list_tasks_slots(intent_data: dict[str, Any]) -> ListTasksSlots:
    """Extract slots from list_tasks intent."""
    return ListTasksSlots(
        date=_get_slot_value(intent_data, "date"),
        priority=_get_slot_value(intent_data, "priority"),
    )
```

**Step 4: Запустить тесты, убедиться что они проходят**

Run: `uv run pytest tests/test_intents.py::TestListTasksSlots -v`
Expected: PASS

**Step 5: Коммит**

```bash
git add alice_ticktick/dialogs/intents.py tests/test_intents.py
git commit -m "feat: добавлен слот priority в ListTasksSlots"
```

---

### Task 2: Добавить шаблоны ответов с приоритетом

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py:67-69`

**Step 1: Добавить шаблоны**

В `alice_ticktick/dialogs/responses.py` после строки `NO_TASKS_TODAY` (строка 69) добавить:

```python
# Filter by priority
TASKS_FOR_DATE_WITH_PRIORITY = "На {date} с {priority}: {count}:\n{tasks}"
NO_TASKS_FOR_DATE_WITH_PRIORITY = "На {date} задач с {priority} нет."
NO_TASKS_TODAY_WITH_PRIORITY = "На сегодня задач с {priority} нет."
```

**Step 2: Коммит**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: шаблоны ответов для фильтрации по приоритету"
```

---

### Task 3: Обновить handle_list_tasks для фильтрации по приоритету

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:736-799` (handle_list_tasks)
- Test: `tests/test_handlers.py`

**Step 1: Написать failing-тесты**

В `tests/test_handlers.py` после `test_list_tasks_api_error` (строка 507) добавить:

```python
async def test_list_tasks_filter_by_priority() -> None:
    """Filter tasks by priority — only high-priority tasks returned."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Важная", priority=5, due_date=today),
        _make_task(task_id="task-2", title="Обычная", priority=0, due_date=today),
        _make_task(task_id="task-3", title="Ещё важная", priority=5, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "высокий"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Важная" in response.text
    assert "Ещё важная" in response.text
    assert "Обычная" not in response.text
    assert "высокий приоритет" in response.text


async def test_list_tasks_filter_by_priority_no_matches() -> None:
    """Filter by priority when no tasks match — specific empty message."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Обычная", priority=0, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "высокий"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "высокий приоритет" in response.text
    assert "нет" in response.text


async def test_list_tasks_filter_by_priority_with_date() -> None:
    """Filter tasks by priority + specific date."""
    tomorrow = datetime.datetime.now(tz=datetime.UTC).date() + datetime.timedelta(days=1)
    tomorrow_dt = datetime.datetime.combine(
        tomorrow,
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Срочная", priority=5, due_date=tomorrow_dt),
        _make_task(task_id="task-2", title="Несрочная", priority=1, due_date=tomorrow_dt),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "date": {"value": {"day": 1, "day_is_relative": True}},
            "priority": {"value": "срочный"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Срочная" in response.text
    assert "Несрочная" not in response.text
    assert "завтра" in response.text


async def test_list_tasks_unknown_priority_ignored() -> None:
    """Unknown priority string — ignore filter, show all tasks."""
    today = datetime.datetime.combine(
        datetime.datetime.now(tz=datetime.UTC).date(),
        datetime.time(),
        tzinfo=datetime.UTC,
    )
    tasks = [
        _make_task(title="Задача 1", priority=5, due_date=today),
        _make_task(task_id="task-2", title="Задача 2", priority=0, due_date=today),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"priority": {"value": "абракадабра"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_list_tasks(message, intent_data, mock_factory)
    assert "Задача 1" in response.text
    assert "Задача 2" in response.text
```

**Step 2: Запустить тесты, убедиться что они падают**

Run: `uv run pytest tests/test_handlers.py::test_list_tasks_filter_by_priority tests/test_handlers.py::test_list_tasks_filter_by_priority_no_matches tests/test_handlers.py::test_list_tasks_filter_by_priority_with_date tests/test_handlers.py::test_list_tasks_unknown_priority_ignored -v`
Expected: FAIL

**Step 3: Обновить handle_list_tasks**

В `alice_ticktick/dialogs/handlers.py`, функция `handle_list_tasks` (строка 736). Заменить текущую реализацию (736-799) на:

```python
async def handle_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_tasks intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    user_tz = _get_user_tz(event_update)
    slots = extract_list_tasks_slots(intent_data)

    # Determine target date (in user timezone)
    if slots.date:
        try:
            target_date = parse_yandex_datetime(slots.date)
            if isinstance(target_date, datetime.datetime):
                target_day = target_date.date()
            else:
                target_day = target_date
        except ValueError:
            target_day = datetime.datetime.now(tz=user_tz).date()
    else:
        target_day = datetime.datetime.now(tz=user_tz).date()

    date_display = _format_date(target_day, user_tz)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to list tasks")
        return Response(text=txt.API_ERROR)

    # Filter tasks for the target date (convert due_date to user timezone)
    day_tasks = [
        t
        for t in all_tasks
        if t.due_date is not None
        and _to_user_date(t.due_date, user_tz) == target_day
        and t.status == 0
    ]

    # Apply priority filter if provided
    priority_filter = parse_priority(slots.priority) if slots.priority else None
    priority_label = _format_priority_label(priority_filter) if priority_filter is not None else None

    if priority_filter is not None:
        day_tasks = [t for t in day_tasks if t.priority == priority_filter]

    if not day_tasks:
        if priority_label:
            if target_day == datetime.datetime.now(tz=user_tz).date():
                return Response(
                    text=txt.NO_TASKS_TODAY_WITH_PRIORITY.format(priority=priority_label)
                )
            return Response(
                text=txt.NO_TASKS_FOR_DATE_WITH_PRIORITY.format(
                    date=date_display, priority=priority_label
                )
            )
        if target_day == datetime.datetime.now(tz=user_tz).date():
            return Response(text=txt.NO_TASKS_TODAY)
        return Response(text=txt.NO_TASKS_FOR_DATE.format(date=date_display))

    count_str = txt.pluralize_tasks(len(day_tasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(day_tasks[:5])]
    task_list = "\n".join(lines)

    if priority_label:
        return Response(
            text=_truncate_response(
                txt.TASKS_FOR_DATE_WITH_PRIORITY.format(
                    date=date_display,
                    priority=priority_label,
                    count=count_str,
                    tasks=task_list,
                )
            )
        )

    return Response(
        text=_truncate_response(
            txt.TASKS_FOR_DATE.format(
                date=date_display,
                count=count_str,
                tasks=task_list,
            )
        )
    )
```

**Step 4: Запустить все тесты**

Run: `uv run pytest tests/test_handlers.py -v -k list_tasks`
Expected: ALL PASS

**Step 5: Коммит**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "feat: фильтрация задач по приоритету в handle_list_tasks"
```

---

### Task 4: Обновить текст помощи и прогнать полный набор тестов

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py:8-22` (HELP)

**Step 1: Обновить HELP**

В `alice_ticktick/dialogs/responses.py`, добавить строку в HELP после "Показать":

```python
HELP = (
    "Я умею:\n"
    "- Создать: «создай задачу купить молоко на завтра»\n"
    "- Повторяющуюся: «создай задачу каждый понедельник»\n"
    "- С напоминанием: «создай задачу с напоминанием за час»\n"
    "- Показать: «что на сегодня?»\n"
    "- По приоритету: «покажи срочные задачи на завтра»\n"
    "- Просроченные: «какие задачи просрочены?»\n"
    "- Найти: «найди задачу про отчёт»\n"
    "- Изменить: «перенеси задачу на завтра»\n"
    "- Удалить: «удали задачу купить молоко»\n"
    "- Завершить: «отметь задачу купить молоко»\n"
    "- Напоминание: «напомни о задаче за 30 минут»\n"
    "- Подзадача: «добавь подзадачу к задаче»\n"
    "- Чеклист: «добавь пункт в чеклист задачи»"
)
```

**Step 2: Прогнать полный набор тестов + линтер + типы**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy alice_ticktick/`
Expected: ALL PASS

**Step 3: Коммит**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: обновлён HELP — фильтрация по приоритету"
```

---

### Task 5: Настроить NLU-интент в Яндекс Диалогах (браузер)

**Требования:**
- Открыть https://dialogs.yandex.ru/developer/skills/d3f073db-dece-42b8-9447-87511df30c83/draft/settings/intents
- Найти интент `list_tasks`
- Добавить слот `priority` (type: YANDEX.STRING) в грамматику
- Обновить грамматику: добавить фразы с приоритетом
- Нажать «Протестировать» и убедиться что Точность и Полнота = 100%

**Примерная грамматика (добавить к существующей):**

```
покажи $Priority задачи на $Date
какие $Priority задачи на $Date
что $Priority на $Date

slots:
  priority:
    source: $Priority
    type: YANDEX.STRING
```

Где `$Priority` — нетерминал для слов: срочные, важные, высокого приоритета, и т.д.

**ВАЖНО:** Эта задача выполняется вручную через браузер. Используй правило из MEMORY.md: `$YANDEX.STRING` НЕ является валидным нетерминалом в грамматике, использовать `.+` или конкретные слова.
