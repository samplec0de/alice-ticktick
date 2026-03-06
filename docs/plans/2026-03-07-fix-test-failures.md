# Fix Test Failures Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Исправить 5 критических ошибок, найденных при тестировании через Yandex Dialogs: неправильный часовой пояс, `edit_task` теряет чистое имя задачи, `check_item`/`delete_checklist_item` перехватываются неверными интентами, и `overdue_tasks` перехватывается `list_tasks`.

**Architecture:** Все исправления локальны — no new modules, only targeted edits to `_helpers.py`, `tasks.py`, and `router.py`. Каждая задача независима.

**Tech Stack:** Python 3.12+, aliceio, rapidfuzz, pytest, pytest-asyncio

---

## Диагностика (задокументированная)

| # | Баг | Root cause | Файл |
|---|-----|-----------|------|
| 1 | «Завтра» создаёт задачу на сегодня | `_get_user_tz` fallback → UTC вместо Europe/Moscow | `_helpers.py:131` |
| 2 | `edit_task` «Не удалось понять, что изменить» при «на завтра» | `handle_edit_task` не передаёт `nlu_dates.task_name` в fuzzy-поиск, поэтому когда `.+` съедает дату, имя задачи не соответствует | `tasks.py:927` |
| 3 | «Отметь пункт X в чеклисте задачи Y» → `complete_task` | В `on_complete_task` нет детектора паттерна чеклиста, только в `on_create_task` | `router.py:263` |
| 4 | «Удали пункт X из чеклиста задачи Y» → `delete_task` | Аналогично — в `on_delete_task` нет детектора | `router.py:304` |
| 5 | «Какие задачи просрочены» показывает все задачи недели | `LIST_TASKS` зарегистрирован раньше `OVERDUE_TASKS`; грамматика `list_tasks` pattern 4 поглощает «просрочены» как `$DateRange` | `router.py:233,243` |

---

## Task 1: Timezone — сменить UTC-fallback на Europe/Moscow

**Files:**
- Modify: `alice_ticktick/dialogs/handlers/_helpers.py:131`
- Test: `tests/test_handlers.py`

**Step 1: Написать падающий тест**

```python
# tests/test_handlers.py — добавить в раздел "# --- Helpers ---" (если нет, в конец файла)
async def test_get_user_tz_fallback_is_moscow() -> None:
    """When no timezone in request, default must be Europe/Moscow, not UTC."""
    from zoneinfo import ZoneInfo
    from alice_ticktick.dialogs.handlers._helpers import _get_user_tz
    tz = _get_user_tz(None)
    assert tz == ZoneInfo("Europe/Moscow")
```

**Step 2: Запустить, убедиться, что падает**

```bash
uv run pytest tests/test_handlers.py::test_get_user_tz_fallback_is_moscow -v
```

Expected: FAILED (`AssertionError: ZoneInfo('UTC') != ZoneInfo('Europe/Moscow')`)

**Step 3: Исправить код**

В `alice_ticktick/dialogs/handlers/_helpers.py:131` заменить:
```python
    logger.warning("No timezone in request, falling back to UTC")
    return ZoneInfo("UTC")
```
На:
```python
    logger.warning("No timezone in request, falling back to Europe/Moscow")
    return ZoneInfo("Europe/Moscow")
```

**Step 4: Запустить тест**

```bash
uv run pytest tests/test_handlers.py::test_get_user_tz_fallback_is_moscow -v
```

Expected: PASSED

**Step 5: Убедиться, что существующие тесты не сломались**

```bash
uv run pytest -v
```

Expected: все тесты PASSED (или не более чем ±1 WARN, поскольку `test_overdue_tasks_found` использует UTC-based datetime для создания "вчера")

Если `test_overdue_tasks_found` падает: поправить тест так, чтобы `yesterday` использовал `Europe/Moscow` вместо `UTC`:
```python
# В test_overdue_tasks_found заменить:
tz = ZoneInfo("Europe/Moscow")
yesterday = datetime.datetime.combine(
    datetime.datetime.now(tz=tz).date() - datetime.timedelta(days=1),
    datetime.time(),
    tzinfo=tz,
)
```

**Step 6: Коммит**

```bash
git add alice_ticktick/dialogs/handlers/_helpers.py tests/test_handlers.py
git commit -m "fix: сменить UTC-fallback на Europe/Moscow в _get_user_tz"
```

---

## Task 2: edit_task — использовать nlu_dates.task_name для fuzzy-поиска

**Files:**
- Modify: `alice_ticktick/dialogs/handlers/tasks.py:927`
- Test: `tests/test_handlers.py`

**Context:** Когда грамматика `.+` поглощает дату ("купить хлеб на завтра" → `task_name`), а затем `_extract_nlu_dates` успешно выделяет дату из NLU-entities и очищает имя ("купить хлеб"), `handle_edit_task` всё равно использует грязное имя из слотов для fuzzy-поиска. Это мешает точному матчингу.

**Step 1: Написать падающий тест**

```python
# tests/test_handlers.py — добавить в раздел "# --- Edit task ---"
async def test_edit_task_uses_nlu_task_name_when_grammar_swallowed_date() -> None:
    """When grammar .+ swallows date into task_name, NLU entity provides clean name for search."""
    from aliceio.types import DateTimeEntity

    tasks = [_make_task(title="Купить хлеб")]
    # Grammar зафиксировало task_name="купить хлеб на завтра" (дата поглощена)
    message = _make_message(command="перенеси задачу купить хлеб на завтра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перенеси", "задачу", "купить", "хлеб", "на", "завтра"]

    dt_value = MagicMock(spec=DateTimeEntity)
    dt_value.day = 1
    dt_value.day_is_relative = True
    dt_value.year = None
    dt_value.month = None
    dt_value.hour = None
    dt_value.minute = None
    dt_value.year_is_relative = False
    dt_value.month_is_relative = False
    dt_value.hour_is_relative = False
    dt_value.minute_is_relative = False

    entity = MagicMock()
    entity.type = "YANDEX.DATETIME"
    entity.tokens = MagicMock()
    entity.tokens.start = 5  # "завтра" at index 5
    entity.tokens.end = 6
    entity.value = dt_value
    message.nlu.entities = [entity]

    # Слот task_name содержит "на завтра" из-за greedy .+
    intent_data = {
        "slots": {
            "task_name": {"value": "купить хлеб на завтра"},
            # new_date slot отсутствует — грамматика съела дату в task_name
        }
    }
    mock_factory = _make_mock_client(tasks=tasks)
    response = await handle_edit_task(message, intent_data, _make_state(), mock_factory)
    # Задача должна быть найдена и обновлена
    assert "обновлена" in response.text
    assert "Купить хлеб" in response.text
```

**Step 2: Запустить, убедиться, что падает**

```bash
uv run pytest tests/test_handlers.py::test_edit_task_uses_nlu_task_name_when_grammar_swallowed_date -v
```

Expected: FAILED (task not found OR EDIT_NO_CHANGES)

**Step 3: Исправить код**

В `alice_ticktick/dialogs/handlers/tasks.py` после строки 877 (`nlu_has_date = ...`) и перед строкой 879 (defence-блок про `new_name`) — добавить обновление `task_name_for_search`:

Найти блок (строка ~880):
```python
    # Defence: grammar "(в $NewName)?" splits task names containing "в"
    tokens = message.nlu.tokens if message.nlu else []
    is_rename_verb = len(tokens) > 0 and tokens[0] in {"переименуй"}
    if slots.new_name is not None and not is_rename_verb:
        merged_name = f"{slots.task_name} в {slots.new_name}"
        slots = dataclasses.replace(slots, task_name=merged_name, new_name=None)
```

И найти строку ~927:
```python
    task_name: str = slots.task_name  # type: ignore[assignment]  # guaranteed by early return
```

Заменить эту строку на:
```python
    # When NLU entities extracted a clean task name (date was removed), prefer it for search.
    # Grammar .+ may swallow date tokens, making the slot value dirty (e.g. "купить хлеб на завтра").
    task_name: str = slots.task_name  # type: ignore[assignment]  # guaranteed by early return
    if (
        nlu_dates is not None
        and nlu_has_date
        and nlu_dates.task_name
        and not _is_only_stopwords(nlu_dates.task_name)
    ):
        task_name = nlu_dates.task_name
```

**Step 4: Запустить тест**

```bash
uv run pytest tests/test_handlers.py::test_edit_task_uses_nlu_task_name_when_grammar_swallowed_date -v
```

Expected: PASSED

**Step 5: Запустить все тесты**

```bash
uv run pytest -v
```

Expected: все PASSED

**Step 6: Коммит**

```bash
git add alice_ticktick/dialogs/handlers/tasks.py tests/test_handlers.py
git commit -m "fix: edit_task использует nlu_dates.task_name для fuzzy-поиска когда .+ съедает дату"
```

---

## Task 3: Disambiguation — check_item в on_complete_task

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers.py`

**Context:** NLU иногда стреляет только `complete_task` для «отметь пункт X в чеклисте задачи Y». В `on_create_task` уже есть редирект для чеклиста, но в `on_complete_task` его нет.

**Step 1: Написать падающий тест**

```python
# tests/test_handlers.py — добавить в конец файла (или в раздел "# --- Complete task ---")
async def test_complete_task_redirects_to_check_item_on_checklist_command() -> None:
    """on_complete_task must redirect to handle_check_item for 'отметь пункт X в чеклисте задачи Y'."""
    from unittest.mock import AsyncMock, patch
    from alice_ticktick.dialogs.router import on_complete_task

    message = _make_message(command="отметь пункт молоко в чеклисте задачи покупки")
    message.nlu = MagicMock()
    message.nlu.tokens = ["отметь", "пункт", "молоко", "в", "чеклисте", "задачи", "покупки"]
    message.nlu.intents = {}

    intent_data: dict[str, Any] = {"slots": {}}

    with patch(
        "alice_ticktick.dialogs.router.handle_check_item", new_callable=AsyncMock
    ) as mock_check:
        from aliceio.types import Response as AliceResponse
        mock_check.return_value = AliceResponse(text="Пункт молоко отмечен в задаче Покупки")
        response = await on_complete_task(message, intent_data, _make_state())

    mock_check.assert_called_once()
    assert "молоко" in response.text.lower() or "отмечен" in response.text.lower()
```

**Step 2: Запустить, убедиться, что падает**

```bash
uv run pytest tests/test_handlers.py::test_complete_task_redirects_to_check_item_on_checklist_command -v
```

Expected: FAILED (`mock_check` not called)

**Step 3: Исправить код в router.py**

В `alice_ticktick/dialogs/router.py`:

1. После существующих модульных переменных (после `_CHECKLIST_ITEM_RE`) добавить новые regex-ы:

```python
_CHECK_ITEM_RE = re.compile(
    r"(?:отметь|выполни)\s+(?:пункт|элемент)\s+(.+?)\s+(?:в|из)\s+(?:чеклиста?|списка?|чеклисте?)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)

_DELETE_CHECKLIST_ITEM_RE = re.compile(
    r"(?:удали|убери)\s+(?:пункт|элемент)\s+(.+?)\s+(?:из|от)\s+(?:чеклиста?|списка?)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)
```

2. Найти handler `on_complete_task` (~строка 262) и заменить его тело:

```python
@router.message(IntentFilter(COMPLETE_TASK))
async def on_complete_task(
    message: Message, intent_data: dict[str, Any], state: FSMContext, event_update: Update
) -> Response:
    """Handle complete_task intent.

    Also detects when NLU fired complete_task but the utterance is actually
    a check_item command (e.g. 'отметь пункт X в чеклисте задачи Y').
    """
    if message.nlu:
        tokens = set(message.nlu.tokens or [])
        if tokens & _CHECKLIST_KEYWORDS and tokens & _ITEM_KEYWORDS:
            m = _CHECK_ITEM_RE.search(message.command or "")
            if m:
                item_name, task_name = m.group(1).strip(), m.group(2).strip()
                fake_intent_data: dict[str, Any] = {
                    "slots": {
                        "item_name": {"value": item_name},
                        "task_name": {"value": task_name},
                    }
                }
                return await handle_check_item(
                    message, fake_intent_data, event_update=event_update
                )
    return await handle_complete_task(message, intent_data, state, event_update=event_update)
```

**Step 4: Запустить тест**

```bash
uv run pytest tests/test_handlers.py::test_complete_task_redirects_to_check_item_on_checklist_command -v
```

Expected: PASSED

**Step 5: Запустить все тесты**

```bash
uv run pytest -v
```

Expected: все PASSED

**Step 6: Коммит**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: on_complete_task редиректит в check_item при паттерне чеклиста"
```

---

## Task 4: Disambiguation — delete_checklist_item в on_delete_task

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers.py`

**Step 1: Написать падающий тест**

```python
# tests/test_handlers.py — добавить в конец файла (или в раздел "# --- Delete task ---")
async def test_delete_task_redirects_to_delete_checklist_item_on_checklist_command() -> None:
    """on_delete_task must redirect to handle_delete_checklist_item for 'удали пункт X из чеклиста задачи Y'."""
    from unittest.mock import AsyncMock, patch
    from alice_ticktick.dialogs.router import on_delete_task

    message = _make_message(command="удали пункт молоко из чеклиста задачи покупки")
    message.nlu = MagicMock()
    message.nlu.tokens = ["удали", "пункт", "молоко", "из", "чеклиста", "задачи", "покупки"]
    message.nlu.intents = {}

    intent_data: dict[str, Any] = {"slots": {}}

    with patch(
        "alice_ticktick.dialogs.router.handle_delete_checklist_item", new_callable=AsyncMock
    ) as mock_delete:
        from aliceio.types import Response as AliceResponse
        mock_delete.return_value = AliceResponse(text="Пункт молоко удалён из задачи Покупки")
        response = await on_delete_task(message, intent_data, _make_state())

    mock_delete.assert_called_once()
    assert "молоко" in response.text.lower() or "удалён" in response.text.lower()
```

**Step 2: Запустить, убедиться, что падает**

```bash
uv run pytest tests/test_handlers.py::test_delete_task_redirects_to_delete_checklist_item_on_checklist_command -v
```

Expected: FAILED

**Step 3: Исправить код в router.py**

Найти handler `on_delete_task` (~строка 304) и заменить тело:

```python
@router.message(IntentFilter(DELETE_TASK))
async def on_delete_task(
    message: Message, intent_data: dict[str, Any], state: FSMContext, event_update: Update
) -> Response:
    """Handle delete_task intent.

    Also detects when NLU fired delete_task but the utterance is actually
    a delete_checklist_item command (e.g. 'удали пункт X из чеклиста задачи Y').
    """
    if message.nlu:
        tokens = set(message.nlu.tokens or [])
        if tokens & _CHECKLIST_KEYWORDS and tokens & _ITEM_KEYWORDS:
            m = _DELETE_CHECKLIST_ITEM_RE.search(message.command or "")
            if m:
                item_name, task_name = m.group(1).strip(), m.group(2).strip()
                fake_intent_data: dict[str, Any] = {
                    "slots": {
                        "item_name": {"value": item_name},
                        "task_name": {"value": task_name},
                    }
                }
                return await handle_delete_checklist_item(
                    message, fake_intent_data, event_update=event_update
                )
    return await handle_delete_task(message, intent_data, state, event_update=event_update)
```

Примечание: `_DELETE_CHECKLIST_ITEM_RE` добавлен на предыдущем шаге (Task 3).

**Step 4: Запустить тест**

```bash
uv run pytest tests/test_handlers.py::test_delete_task_redirects_to_delete_checklist_item_on_checklist_command -v
```

Expected: PASSED

**Step 5: Запустить все тесты**

```bash
uv run pytest -v
```

Expected: все PASSED

**Step 6: Коммит**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: on_delete_task редиректит в delete_checklist_item при паттерне чеклиста"
```

---

## Task 5: Router — OVERDUE_TASKS перед LIST_TASKS

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers.py`

**Context:** Грамматика `list_tasks` pattern 4 (`$Priority? (задачи) $DateRange`) поглощает «какие задачи просрочены» → `date_range = "просрочены"`. Так как `LIST_TASKS` зарегистрирован раньше `OVERDUE_TASKS` (~строка 233 vs 243), `on_list_tasks` выполняется первым и возвращает все задачи с шаблоном «На этой неделе».

**Step 1: Написать падающий тест**

```python
# tests/test_handlers.py — добавить рядом с тестами overdue
async def test_overdue_tasks_not_intercepted_by_list_tasks() -> None:
    """handle_overdue_tasks must filter by past dates, not return all tasks."""
    import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    today = datetime.datetime.now(tz=tz).date()
    yesterday = today - datetime.timedelta(days=1)

    overdue_task = _make_task(
        title="Просроченная",
        due_date=datetime.datetime.combine(yesterday, datetime.time(), tzinfo=tz),
    )
    future_task = _make_task(
        title="Будущая",
        due_date=datetime.datetime.combine(today + datetime.timedelta(days=5), datetime.time(), tzinfo=tz),
    )
    message = _make_message()
    mock_factory = _make_mock_client(tasks=[overdue_task, future_task])
    event_update = MagicMock()
    event_update.meta = MagicMock()
    event_update.meta.timezone = "Europe/Moscow"
    event_update.meta.interfaces = MagicMock()
    event_update.meta.interfaces.account_linking = None

    response = await handle_overdue_tasks(
        message, {}, ticktick_client_factory=mock_factory, event_update=event_update
    )
    assert "Просроченная" in response.text
    assert "Будущая" not in response.text
```

Этот тест проверяет поведение `handle_overdue_tasks` напрямую, независимо от порядка в роутере.

**Step 2: Запустить тест — он должен быть зелёным уже сейчас**

```bash
uv run pytest tests/test_handlers.py::test_overdue_tasks_not_intercepted_by_list_tasks -v
```

Expected: PASSED (handler сам по себе правильный, проблема в роутере)

**Step 3: Написать тест на порядок регистрации в роутере**

```python
# tests/test_handlers.py — добавить в конец файла
def test_router_overdue_registered_before_list_tasks() -> None:
    """OVERDUE_TASKS handler must appear before LIST_TASKS in the router.

    This prevents list_tasks grammar from intercepting 'какие задачи просрочены'
    via its $DateRange slot (which captures 'просрочены' as a range value).
    """
    from alice_ticktick.dialogs.router import router
    from alice_ticktick.dialogs.intents import LIST_TASKS, OVERDUE_TASKS

    handler_intents: list[str] = []
    for observer in router.observers.values():
        for handler in getattr(observer, "handlers", []):
            for filter_ in getattr(handler, "filters", []):
                intent = getattr(filter_, "intent", None)
                if intent in (LIST_TASKS, OVERDUE_TASKS):
                    handler_intents.append(intent)

    assert OVERDUE_TASKS in handler_intents, "OVERDUE_TASKS не зарегистрирован"
    assert LIST_TASKS in handler_intents, "LIST_TASKS не зарегистрирован"
    assert handler_intents.index(OVERDUE_TASKS) < handler_intents.index(LIST_TASKS), (
        "OVERDUE_TASKS должен быть зарегистрирован ДО LIST_TASKS в роутере"
    )
```

**Step 4: Запустить тест, убедиться что падает**

```bash
uv run pytest tests/test_handlers.py::test_router_overdue_registered_before_list_tasks -v
```

Expected: FAILED (`OVERDUE_TASKS` зарегистрирован после `LIST_TASKS`)

> **Примечание:** Если тест падает по другой причине (структура observer не та), упростить до проверки через чтение исходника или убрать этот step и перейти сразу к Step 5.

**Step 5: Переместить OVERDUE_TASKS перед LIST_TASKS в router.py**

В `alice_ticktick/dialogs/router.py` переместить блок:
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

...чтобы он стоял **перед** `@router.message(IntentFilter(LIST_TASKS))`.

**Step 6: Запустить тесты**

```bash
uv run pytest -v
```

Expected: все PASSED

**Step 7: Коммит**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: зарегистрировать OVERDUE_TASKS в роутере раньше LIST_TASKS"
```

---

## Task 6: Финальная проверка и PR

**Step 1: Полный прогон CI**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy alice_ticktick/
uv run pytest -v
```

Expected: 0 errors, 0 format issues, 0 mypy errors, все тесты зелёные.

**Step 2: Если mypy ругается**

Скорее всего на новые `fake_intent_data` в router.py — уже типизированы как `dict[str, Any]`, должно быть ок.

**Step 3: Если ruff format ругается**

```bash
uv run ruff format .
git add -u
git commit -m "style: ruff format"
```

**Step 4: Push и PR**

```bash
git push origin <branch>
```

Открыть PR в main с описанием исправлений.

---

## Краткая сводка изменений

| Task | Файл | Изменение |
|------|------|-----------|
| 1 | `_helpers.py:131` | UTC → Europe/Moscow fallback |
| 2 | `tasks.py:927` | +4 строки: use `nlu_dates.task_name` for search |
| 3 | `router.py` | +regex `_CHECK_ITEM_RE` + guard в `on_complete_task` |
| 4 | `router.py` | +regex `_DELETE_CHECKLIST_ITEM_RE` + guard в `on_delete_task` |
| 5 | `router.py` | Переставить `on_overdue_tasks` перед `on_list_tasks` |
