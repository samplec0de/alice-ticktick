# Search Details & Action Confirmations — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show task description + checklist in search results for the best match; improve action confirmations across all handlers to describe exactly what was done.

**Architecture:** Add `_format_priority_label` and `_format_task_context` helpers to `handlers.py`. Rewrite `handle_search_task` with budget-aware response builder. Update response templates in `responses.py`. Modify 5 handlers for richer confirmations.

**Tech Stack:** Python, aliceio, pytest, pytest-asyncio

---

### Task 1: Add helper `_format_priority_label(priority)` in handlers.py

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:138-141`
- Test: `tests/test_handlers.py`

**Step 1: Write the failing test**

Add at top of test file alongside existing imports, then add test:

```python
# In tests/test_handlers.py, add to imports:
from alice_ticktick.dialogs.handlers import _format_priority_label

# Add test:
class TestFormatPriorityLabel:
    def test_high(self) -> None:
        assert _format_priority_label(5) == "высокий приоритет"

    def test_medium(self) -> None:
        assert _format_priority_label(3) == "средний приоритет"

    def test_low(self) -> None:
        assert _format_priority_label(1) == "низкий приоритет"

    def test_none(self) -> None:
        assert _format_priority_label(0) == ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::TestFormatPriorityLabel -v`
Expected: FAIL — `ImportError: cannot import name '_format_priority_label'`

**Step 3: Write minimal implementation**

Add after line 141 in `handlers.py`:

```python
def _format_priority_label(priority: int) -> str:
    """Format task priority as Russian text for voice output."""
    return {5: "высокий приоритет", 3: "средний приоритет", 1: "низкий приоритет"}.get(
        priority, ""
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_handlers.py::TestFormatPriorityLabel -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "feat: хелпер _format_priority_label для текстового приоритета"
```

---

### Task 2: Add helper `_format_task_context(task, tz)` in handlers.py

Returns string like `" (завтра, высокий приоритет)"` or `""` — used by complete/delete confirmations.

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Test: `tests/test_handlers.py`

**Step 1: Write the failing test**

```python
# In tests/test_handlers.py, add to imports:
from alice_ticktick.dialogs.handlers import _format_task_context

# Add test:
import datetime
from zoneinfo import ZoneInfo

class TestFormatTaskContext:
    def test_with_date_and_priority(self) -> None:
        tz = ZoneInfo("UTC")
        now = datetime.datetime.now(tz=tz)
        tomorrow = now + datetime.timedelta(days=1)
        task = _make_task(title="X", due_date=tomorrow, priority=5)
        result = _format_task_context(task, tz)
        assert "завтра" in result
        assert "высокий приоритет" in result
        assert result.startswith(" (")
        assert result.endswith(")")

    def test_with_date_only(self) -> None:
        tz = ZoneInfo("UTC")
        now = datetime.datetime.now(tz=tz)
        tomorrow = now + datetime.timedelta(days=1)
        task = _make_task(title="X", due_date=tomorrow, priority=0)
        result = _format_task_context(task, tz)
        assert "завтра" in result
        assert "приоритет" not in result

    def test_with_priority_only(self) -> None:
        tz = ZoneInfo("UTC")
        task = _make_task(title="X", priority=3)
        result = _format_task_context(task, tz)
        assert "средний приоритет" in result

    def test_empty(self) -> None:
        tz = ZoneInfo("UTC")
        task = _make_task(title="X", priority=0)
        result = _format_task_context(task, tz)
        assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::TestFormatTaskContext -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Add after `_format_priority_label` in `handlers.py`:

```python
def _format_task_context(task: Task, tz: ZoneInfo) -> str:
    """Format task date+priority as ' (завтра, высокий приоритет)' or ''."""
    parts: list[str] = []
    if task.due_date:
        parts.append(_format_date(task.due_date, tz))
    prio = _format_priority_label(task.priority)
    if prio:
        parts.append(prio)
    if not parts:
        return ""
    return " (" + ", ".join(parts) + ")"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_handlers.py::TestFormatTaskContext -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "feat: хелпер _format_task_context для контекста задачи"
```

---

### Task 3: Rewrite `handle_search_task` with budget-aware response builder

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:734-776`
- Modify: `alice_ticktick/dialogs/responses.py:63-65`
- Test: `tests/test_handlers.py`

**Step 1: Update response templates in `responses.py`**

Replace lines 63-65:
```python
# Search — old
SEARCH_QUERY_REQUIRED = "Какую задачу найти? Скажите название или часть названия."
SEARCH_NO_RESULTS = 'По запросу "{query}" ничего не найдено.'
SEARCH_RESULTS = "Найдено {count}:\n{tasks}"
```

With:
```python
# Search
SEARCH_QUERY_REQUIRED = "Какую задачу найти? Скажите название или часть названия."
SEARCH_NO_RESULTS = 'По запросу "{query}" ничего не найдено.'
SEARCH_RESULTS = "Найдено {count}:\n{tasks}"
SEARCH_BEST_MATCH = "Лучшее совпадение — «{name}»{context}:"
SEARCH_BEST_MATCH_SINGLE = "Найдена задача «{name}»{context}:"
SEARCH_DESCRIPTION = "Описание: {description}"
SEARCH_ALSO_FOUND = "\nТакже найдено:"
SEARCH_CHECKLIST_MORE = "…и ещё {count}"
```

**Step 2: Write the failing tests**

```python
# In tests/test_handlers.py — new tests for search_task with details

async def test_search_task_best_match_with_description() -> None:
    """Best match shows description."""
    tasks = [
        Task(
            id="t1", title="Купить продукты", projectId="p1",
            content="Зайти в Перекрёсток", priority=0, status=0,
        ),
        Task(id="t2", title="Купить хлеб", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "купить продукты"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Лучшее совпадение" in response.text
    assert "Купить продукты" in response.text
    assert "Зайти в Перекрёсток" in response.text
    assert "Также найдено" in response.text
    assert "Купить хлеб" in response.text


async def test_search_task_best_match_with_checklist() -> None:
    """Best match shows checklist with statuses."""
    tasks = [
        Task(
            id="t1", title="Список покупок", projectId="p1",
            content="", priority=0, status=0,
            items=[
                ChecklistItem(id="c1", title="Молоко", status=1),
                ChecklistItem(id="c2", title="Хлеб", status=0),
            ],
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "список покупок"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Список покупок" in response.text
    assert "[x] Молоко" in response.text
    assert "[ ] Хлеб" in response.text


async def test_search_task_single_result_no_also_found() -> None:
    """Single match — no 'Также найдено' section."""
    tasks = [
        Task(id="t1", title="Уникальная задача", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "уникальная задача"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Найдена задача" in response.text
    assert "Также найдено" not in response.text


async def test_search_task_no_description_no_checklist() -> None:
    """Best match without description/checklist skips those sections."""
    tasks = [
        Task(id="t1", title="Простая задача", projectId="p1", priority=0, status=0),
        Task(id="t2", title="Простой тест", projectId="p1", priority=0, status=0),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "простая"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "Лучшее совпадение" in response.text
    assert "Описание" not in response.text
    assert "Чеклист" not in response.text


async def test_search_task_budget_truncates_checklist() -> None:
    """When checklist is too long, show partial + 'и ещё N'."""
    long_items = [
        ChecklistItem(id=f"c{i}", title=f"Пункт номер {i} с очень длинным названием для теста", status=0)
        for i in range(30)
    ]
    tasks = [
        Task(
            id="t1", title="Задача", projectId="p1",
            content="Описание " * 20,
            priority=5, status=0,
            items=long_items,
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "задача"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert len(response.text) <= 1024
    assert "и ещё" in response.text


async def test_search_task_best_match_with_context() -> None:
    """Best match shows date and priority in context."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [
        Task(
            id="t1", title="Важное дело", projectId="p1",
            priority=5, status=0, dueDate=tomorrow,
        ),
    ]
    message = _make_message()
    intent_data: dict[str, Any] = {"slots": {"query": {"value": "важное дело"}}}
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_search_task(message, intent_data, mock_factory)
    assert "завтра" in response.text
    assert "высокий приоритет" in response.text
```

Note: need to add `from zoneinfo import ZoneInfo` and `from alice_ticktick.ticktick.models import ChecklistItem` to test imports.

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py::test_search_task_best_match_with_description tests/test_handlers.py::test_search_task_best_match_with_checklist tests/test_handlers.py::test_search_task_single_result_no_also_found -v`
Expected: FAIL

**Step 4: Rewrite `handle_search_task` in handlers.py**

Replace lines 734-776 with:

```python
def _build_search_response(
    best_task: Task,
    other_tasks: list[Task],
    tz: ZoneInfo,
) -> str:
    """Build budget-aware search response with details for the best match."""
    budget = ALICE_RESPONSE_MAX_LENGTH
    parts: list[str] = []

    # 1. Header for best match
    context = _format_task_context(best_task, tz)
    if other_tasks:
        header = txt.SEARCH_BEST_MATCH.format(name=best_task.title, context=context)
    else:
        header = txt.SEARCH_BEST_MATCH_SINGLE.format(name=best_task.title, context=context)
    parts.append(header)
    budget -= len(header) + 1  # +1 for \n

    # 2. Description (priority over checklist)
    if best_task.content.strip():
        desc_line = txt.SEARCH_DESCRIPTION.format(description=best_task.content.strip())
        if len(desc_line) + 1 <= budget:
            parts.append(desc_line)
            budget -= len(desc_line) + 1
        else:
            # Truncate description to fit
            available = budget - len("Описание: ") - 2  # 1 for \n, 1 for …
            if available > 20:
                parts.append("Описание: " + best_task.content.strip()[:available] + "…")
                budget = 0

    # 3. Checklist
    if best_task.items and budget > 30:
        checklist_header = "Чеклист:"
        parts.append(checklist_header)
        budget -= len(checklist_header) + 1

        shown = 0
        remaining = len(best_task.items)
        for i, item in enumerate(best_task.items, 1):
            mark = "[x]" if item.status == 1 else "[ ]"
            line = f"{i}. {mark} {item.title}"
            if len(line) + 1 <= budget:
                parts.append(line)
                budget -= len(line) + 1
                shown += 1
                remaining -= 1
            else:
                break

        if remaining > 0 and shown > 0:
            more_line = txt.SEARCH_CHECKLIST_MORE.format(count=remaining)
            parts.append(more_line)
            budget -= len(more_line) + 1

    # 4. Other matches
    if other_tasks and budget > 20:
        parts.append(txt.SEARCH_ALSO_FOUND.strip())
        budget -= len(txt.SEARCH_ALSO_FOUND.strip()) + 1

        for i, task in enumerate(other_tasks, 2):
            line = _format_task_line(i, task)
            if len(line) + 1 <= budget:
                parts.append(line)
                budget -= len(line) + 1
            else:
                break

    return "\n".join(parts)


async def handle_search_task(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle search_task intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_search_task_slots(intent_data)

    if not slots.query:
        return Response(text=txt.SEARCH_QUERY_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to search tasks")
        return Response(text=txt.API_ERROR)

    active_tasks = [t for t in all_tasks if t.status == 0]
    if not active_tasks:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    titles = [t.title for t in active_tasks]
    matches = find_matches(slots.query, titles, limit=5)

    if not matches:
        return Response(text=txt.SEARCH_NO_RESULTS.format(query=slots.query))

    matched_tasks = [active_tasks[idx] for _title, _score, idx in matches]
    best_task = matched_tasks[0]
    other_tasks = matched_tasks[1:]

    user_tz = _get_user_tz(event_update)
    response_text = _build_search_response(best_task, other_tasks, user_tz)

    return Response(text=response_text)
```

**Step 5: Run all search tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py -k "search_task" -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "feat: поиск задачи показывает описание и чеклист лучшего совпадения"
```

---

### Task 4: Improve `edit_task` confirmation — show what changed

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:977-1000`
- Modify: `alice_ticktick/dialogs/responses.py:75`
- Test: `tests/test_handlers.py`

**Step 1: Update response template in `responses.py`**

Replace line 75:
```python
EDIT_SUCCESS = 'Задача "{name}" обновлена.'
```

With:
```python
EDIT_SUCCESS = 'Задача "{name}" обновлена: {changes}.'
EDIT_SUCCESS_NO_DETAILS = 'Задача "{name}" обновлена.'
```

**Step 2: Write the failing tests**

```python
async def test_edit_task_reschedule_confirms_date() -> None:
    """Edit task with date change confirms the new date."""
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "дата" in response.text.lower()
    assert "завтра" in response.text


async def test_edit_task_change_priority_confirms() -> None:
    """Edit task with priority change confirms the new priority."""
    tasks = [_make_task(title="Купить молоко")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "купить молоко"},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "приоритет" in response.text.lower()
    assert "высокий" in response.text.lower()


async def test_edit_task_multiple_changes_confirms_all() -> None:
    """Edit with date+priority confirms both changes."""
    tasks = [_make_task(title="Отчёт")]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "отчёт"},
            "new_date": {"value": {"day": 1, "day_is_relative": True}},
            "new_priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, mock_factory)
    assert "дата" in response.text.lower()
    assert "приоритет" in response.text.lower()
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py::test_edit_task_reschedule_confirms_date tests/test_handlers.py::test_edit_task_change_priority_confirms tests/test_handlers.py::test_edit_task_multiple_changes_confirms_all -v`
Expected: FAIL — the current response doesn't contain "дата" or "приоритет"

**Step 4: Modify the generic edit success path in `handle_edit_task`**

Replace lines 977-1000 (the response building section at the end of `handle_edit_task`) with:

```python
    # Specific messages for recurrence/reminder changes
    if has_remove_recurrence and new_repeat_flag is not None:
        return Response(text=txt.RECURRENCE_REMOVED.format(name=best_match))
    if has_remove_reminder and new_reminders is not None and not new_reminders:
        return Response(text=txt.REMINDER_REMOVED.format(name=best_match))
    if has_recurrence and new_repeat_flag:
        rec_display = format_recurrence(new_repeat_flag)
        return Response(
            text=txt.RECURRENCE_UPDATED.format(name=best_match, recurrence=rec_display)
        )
    if has_reminder and new_reminders:
        rem_display = format_reminder(new_reminders[0])
        return Response(text=txt.REMINDER_UPDATED.format(name=best_match, reminder=rem_display))

    # Only project changed → specific move message
    only_project = (
        target_project_id is not None
        and new_title is None
        and new_due_date is None
        and new_priority_value is None
    )
    if only_project and target_project_name:
        return Response(text=txt.TASK_MOVED.format(name=best_match, project=target_project_name))

    # Build detailed confirmation of what changed
    user_tz = _get_user_tz(event_update)
    changes: list[str] = []
    if new_due_date is not None:
        changes.append(f"дата изменена на {_format_date(new_due_date, user_tz)}")
    if new_priority_value is not None:
        prio_label = _format_priority_label(new_priority_value)
        if prio_label:
            changes.append(f"приоритет — {prio_label.replace(' приоритет', '')}")
        else:
            changes.append("приоритет убран")
    if new_title is not None:
        changes.append(f'название изменено на "{new_title}"')
    if target_project_name:
        changes.append(f'перемещена в проект "{target_project_name}"')

    if changes:
        return Response(
            text=txt.EDIT_SUCCESS.format(name=best_match, changes=", ".join(changes))
        )
    return Response(text=txt.EDIT_SUCCESS_NO_DETAILS.format(name=best_match))
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py -k "edit_task" -v`
Expected: ALL PASS (including existing tests that assert "обновлена")

Note: existing tests assert `"обновлена" in response.text` — the new template still contains "обновлена" so they should pass. But `test_edit_task_change_priority` asserts only `"обновлена"` — should still work since the new response is `'Задача "X" обновлена: приоритет — высокий.'`.

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "feat: edit_task подтверждение описывает что именно изменилось"
```

---

### Task 5: Improve `complete_task` confirmation — show task context

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:731`
- Modify: `alice_ticktick/dialogs/responses.py:57`
- Test: `tests/test_handlers.py`

**Step 1: Update response template in `responses.py`**

Replace line 57:
```python
TASK_COMPLETED = 'Задача "{name}" отмечена выполненной.'
```

With:
```python
TASK_COMPLETED = 'Задача "{name}"{context} отмечена выполненной.'
```

**Step 2: Write the failing test**

```python
async def test_complete_task_confirms_with_context() -> None:
    """Complete task shows date and priority in confirmation."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [_make_task(title="Купить молоко", due_date=tomorrow, priority=1)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "купить молоко"}},
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_complete_task(message, intent_data, mock_factory)
    assert "Купить молоко" in response.text
    assert "завтра" in response.text
    assert "низкий приоритет" in response.text
    assert "выполненной" in response.text
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_complete_task_confirms_with_context -v`
Expected: FAIL — "завтра" not in response

**Step 4: Modify `handle_complete_task` response**

Change line 731 from:
```python
    return Response(text=txt.TASK_COMPLETED.format(name=best_match))
```
To:
```python
    user_tz = _get_user_tz(event_update)
    context = _format_task_context(matched_task, user_tz)
    return Response(text=txt.TASK_COMPLETED.format(name=best_match, context=context))
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py -k "complete_task" -v`
Expected: ALL PASS

Note: existing `test_complete_task_success` asserts `"Купить молоко" in response.text` and `"выполненной" in response.text` — both still true. The task has no date/priority so context will be `""`.

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "feat: complete_task подтверждение показывает дату и приоритет задачи"
```

---

### Task 6: Improve `delete_task` confirmation — show task context

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:1050` (delete prompt) and `:1091` (delete success)
- Modify: `alice_ticktick/dialogs/responses.py:86-87`
- Test: `tests/test_handlers.py`

**Step 1: Update response templates in `responses.py`**

Replace lines 86-87:
```python
DELETE_CONFIRM = 'Удалить задачу "{name}"? Скажите да или нет.'
DELETE_SUCCESS = 'Задача "{name}" удалена.'
```

With:
```python
DELETE_CONFIRM = 'Удалить задачу "{name}"{context}? Скажите да или нет.'
DELETE_SUCCESS = 'Задача "{name}"{context} удалена.'
```

**Step 2: Write the failing test**

```python
async def test_delete_task_confirm_shows_context() -> None:
    """Delete confirmation shows task date."""
    tz = ZoneInfo("UTC")
    tomorrow = datetime.datetime.now(tz=tz) + datetime.timedelta(days=1)
    tasks = [_make_task(title="Старый отчёт", due_date=tomorrow)]
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "старый отчёт"}},
    }
    state = AsyncMock()
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_delete_task(message, intent_data, state, mock_factory)
    assert "Старый отчёт" in response.text
    assert "завтра" in response.text
    assert "Удалить" in response.text
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_delete_task_confirm_shows_context -v`
Expected: FAIL

**Step 4: Modify `handle_delete_task`**

In `handle_delete_task`, change the confirm response (around line 1050):
```python
    # Before:
    return Response(text=txt.DELETE_CONFIRM.format(name=best_match))

    # After:
    user_tz = _get_user_tz(event_update)
    context = _format_task_context(matched_task, user_tz)
    await state.set_data(
        {
            "task_id": matched_task.id,
            "project_id": matched_task.project_id,
            "task_name": best_match,
            "task_context": context,
        }
    )
    return Response(text=txt.DELETE_CONFIRM.format(name=best_match, context=context))
```

Also update `handle_delete_confirm` to pass context to success message (around line 1091):
```python
    # Add after existing data reads:
    task_context = data.get("task_context", "")

    # Change:
    return Response(text=txt.DELETE_SUCCESS.format(name=task_name, context=task_context))
```

Note: the `await state.set_data` call replaces the existing one — make sure `task_context` is included in the dict.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py -k "delete_task" -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "feat: delete_task подтверждение и результат показывают контекст задачи"
```

---

### Task 7: Improve `create_task` confirmation — add priority

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:448-484`
- Modify: `alice_ticktick/dialogs/responses.py:33-43`
- Test: `tests/test_handlers.py`

**Step 1: Update response templates in `responses.py`**

Add new template after line 34:
```python
TASK_CREATED_WITH_PRIORITY = 'Готово! Задача "{name}" создана, приоритет — {priority}.'
TASK_CREATED_WITH_DATE_AND_PRIORITY = 'Готово! Задача "{name}" создана на {date}, приоритет — {priority}.'
```

**Step 2: Write the failing test**

```python
async def test_create_task_with_priority_confirms() -> None:
    """Create task with priority shows priority in confirmation."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Важный отчёт"},
            "priority": {"value": "высокий"},
        },
    }
    mock_factory = _make_mock_client(tasks=[_make_task()])
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Важный отчёт" in response.text
    assert "приоритет" in response.text.lower()
    assert "высокий" in response.text.lower()


async def test_create_task_with_date_and_priority_confirms() -> None:
    """Create task with date + priority shows both."""
    message = _make_message()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "Отчёт"},
            "priority": {"value": "средний"},
            "date": {"value": {"day": 1, "day_is_relative": True}},
        },
    }
    mock_factory = _make_mock_client(tasks=[_make_task()])
    response = await handle_create_task(message, intent_data, mock_factory)
    assert "Отчёт" in response.text
    assert "завтра" in response.text
    assert "средний" in response.text.lower()
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_create_task_with_priority_confirms -v`
Expected: FAIL

**Step 4: Modify `handle_create_task` response building**

At the end of `handle_create_task` (after the recurrence/reminder checks), modify the response chain. The key change is in the `else` branches where no recurrence/reminder:

```python
    # After recurrence/reminder checks...

    priority_display = _format_priority_label(priority_value)
    # Remove " приоритет" suffix for inline use
    priority_short = priority_display.replace(" приоритет", "") if priority_display else ""

    if project_name_display:
        if date_display:
            resp = txt.TASK_CREATED_IN_PROJECT_WITH_DATE.format(
                name=task_name, project=project_name_display, date=date_display
            )
        else:
            resp = txt.TASK_CREATED_IN_PROJECT.format(name=task_name, project=project_name_display)
        if priority_short:
            resp = resp.rstrip(".") + f", приоритет — {priority_short}."
        return Response(text=resp)

    if date_display and priority_short:
        return Response(
            text=txt.TASK_CREATED_WITH_DATE_AND_PRIORITY.format(
                name=task_name, date=date_display, priority=priority_short
            )
        )
    if date_display:
        return Response(text=txt.TASK_CREATED_WITH_DATE.format(name=task_name, date=date_display))
    if priority_short:
        return Response(
            text=txt.TASK_CREATED_WITH_PRIORITY.format(name=task_name, priority=priority_short)
        )
    return Response(text=txt.TASK_CREATED.format(name=slots.task_name))
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py -k "create_task" -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "feat: create_task подтверждение показывает приоритет"
```

---

### Task 8: Improve `check_item` confirmation — add task name

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py:1400`
- Modify: `alice_ticktick/dialogs/responses.py:108`
- Test: `tests/test_handlers_phase3.py`

**Step 1: Update response template in `responses.py`**

Replace line 108:
```python
CHECKLIST_ITEM_CHECKED = "Пункт «{item}» отмечен выполненным."
```

With:
```python
CHECKLIST_ITEM_CHECKED = "Пункт «{item}» в задаче «{task}» отмечен выполненным."
```

**Step 2: Write the failing test (or update existing)**

The existing test in `test_handlers_phase3.py::TestCheckItem::test_success` already checks for `"Молоко" in response.text` and `"выполненным" in response.text`. Add a new assertion:

```python
# In TestCheckItem.test_success, add:
        assert "Список покупок" in response.text
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers_phase3.py::TestCheckItem::test_success -v`
Expected: FAIL — "Список покупок" not in response

**Step 4: Modify `handle_check_item` response**

Change line 1400 from:
```python
    return Response(text=txt.CHECKLIST_ITEM_CHECKED.format(item=matched_item_title))
```
To:
```python
    return Response(text=txt.CHECKLIST_ITEM_CHECKED.format(item=matched_item_title, task=best_match))
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers_phase3.py::TestCheckItem -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py alice_ticktick/dialogs/responses.py tests/test_handlers_phase3.py
git commit -m "feat: check_item подтверждение включает название задачи"
```

---

### Task 9: Run full test suite and lint

**Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS, no regressions

**Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors

**Step 3: Run formatter**

Run: `uv run ruff format .`
Expected: Files formatted (or already formatted)

**Step 4: Run type checker**

Run: `uv run mypy alice_ticktick/`
Expected: No errors

**Step 5: Fix any issues found, then commit**

```bash
git add -A
git commit -m "chore: lint и типы после рефакторинга подтверждений"
```

---

### Task 10: Create feature branch and PR

**Step 1: Create branch and push**

```bash
git checkout -b improve/search-details-confirmations
git push -u origin improve/search-details-confirmations
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "Детали поиска и подтверждения действий" \
  --body "$(cat <<'EOF'
## Summary
- При поиске задачи лучшее совпадение показывает описание и чеклист (со статусами)
- Все успешные действия подтверждаются с описанием что именно было сделано
- Умный бюджет символов: описание > чеклист > остальные совпадения (лимит 1024)

## Changes
- `search_task` — описание + чеклист для лучшего совпадения, бюджетная сборка ответа
- `edit_task` — подтверждение перечисляет изменённые поля
- `complete_task` — подтверждение показывает дату и приоритет задачи
- `delete_task` — подтверждение и prompt показывают контекст задачи
- `create_task` — подтверждение показывает приоритет если указан
- `check_item` — подтверждение включает название задачи

## Test plan
- [ ] uv run pytest -v — все тесты проходят
- [ ] uv run ruff check . — нет ошибок линтера
- [ ] uv run mypy alice_ticktick/ — нет ошибок типов
EOF
)"
```
