# Fix xfail/xpass E2E Test Bugs — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate all 24 xfail e2e tests by fixing underlying code bugs (router fallbacks, FSM persistence, handler-level extraction).

**Architecture:** 7 independent bug fixes, each adding code-level workarounds in the router or handlers when Yandex NLU fails to match the correct intent. Grammar files updated locally for future deploy to Yandex Dialogs.

**Tech Stack:** Python 3.12+, aliceio (FSM API storage), pytest, re (regex fallbacks)

---

## Bug Summary

| # | Bug | Tests | Root Cause | Fix Location |
|---|-----|-------|-----------|-------------|
| 1 | edit_task NLU not recognized | 16 | Grammar too complex for NLU | router.py `on_unknown` fallback |
| 2 | show_checklist intercepted by list_tasks | 2 | `$Priority: .+` matches "чеклист" | router.py `on_list_tasks` redirect |
| 3 | search_task intercepted | 1 | "поиск" not in grammar | router.py `on_unknown` + grammar |
| 4 | create_task project slot lost | 1 | `$TaskName: .+` eats "в проекте X" | tasks.py `handle_create_task` regex |
| 5 | delete FSM state lost | 2 | In-memory FSM in serverless | main.py `use_api_storage=True` |
| 6 | recurring "каждый день" consumed as DATETIME | 1 | NLU DATETIME vs $Recurrence conflict | `_infer_rec_freq_from_tokens` extend |
| 7 | goodbye in text mode | 1 | YANDEX.GOODBYE only fires in voice | router.py `on_unknown` fallback |

---

### Task 1: Fix #7 — Goodbye text mode fallback

**Files:**
- Modify: `alice_ticktick/dialogs/router.py:483-488` (on_unknown)
- Test: `tests/test_handlers.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_unknown_handler_catches_goodbye_in_text_mode() -> None:
    """on_unknown should detect goodbye keywords and return goodbye response."""
    from alice_ticktick.dialogs.router import on_unknown

    for phrase in ["до свидания", "пока", "до встречи"]:
        message = _make_message(command=phrase)
        message.nlu = MagicMock()
        message.nlu.tokens = phrase.split()
        message.nlu.intents = {}
        response = await on_unknown(message)
        assert response.text == txt.GOODBYE, f"Failed for '{phrase}': {response.text}"
        assert response.end_session is True


@pytest.mark.asyncio
async def test_unknown_handler_still_returns_unknown_for_normal_input() -> None:
    """on_unknown should still return UNKNOWN for non-goodbye phrases."""
    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="абракадабра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["абракадабра"]
    message.nlu.intents = {}
    response = await on_unknown(message)
    assert response.text == txt.UNKNOWN
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_unknown_handler_catches_goodbye_in_text_mode -v`
Expected: FAIL (on_unknown returns UNKNOWN, not GOODBYE)

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/router.py`, add a constant and modify `on_unknown`:

```python
# Near top, after other constants:
_GOODBYE_KEYWORDS = frozenset({"до свидания", "пока", "до встречи", "до скорого"})

# Replace on_unknown:
@router.message()
async def on_unknown(message: Message) -> Response:
    """Fallback for unrecognized commands."""
    command_lower = (message.command or "").lower().strip()
    if command_lower in _GOODBYE_KEYWORDS:
        return await handle_goodbye(message)
    return await handle_unknown(message)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py::test_unknown_handler_catches_goodbye_in_text_mode tests/test_handlers.py::test_unknown_handler_still_returns_unknown_for_normal_input -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: fallback goodbye detection in text mode (on_unknown)"
```

---

### Task 2: Fix #2 — show_checklist intercepted by list_tasks

**Files:**
- Modify: `alice_ticktick/dialogs/router.py:257-264` (on_list_tasks)
- Test: `tests/test_handlers.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_list_tasks_redirects_to_show_checklist() -> None:
    """on_list_tasks should redirect to show_checklist when 'чеклист' in utterance."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_list_tasks

    message = _make_message(command="покажи чеклист задачи купить хлеб")
    message.nlu = MagicMock()
    message.nlu.tokens = ["покажи", "чеклист", "задачи", "купить", "хлеб"]
    message.nlu.intents = {"list_tasks": {"slots": {"priority": {"value": "чеклист"}}}}
    message.nlu.entities = []

    intent_data: dict[str, Any] = {"slots": {"priority": {"value": "чеклист"}}}
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    with patch(
        "alice_ticktick.dialogs.router.handle_show_checklist",
        new_callable=AsyncMock,
        return_value=MagicMock(text="Чеклист"),
    ) as mock_handler:
        await on_list_tasks(message, intent_data, event_update)
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        fake_intent = call_args[1]
        assert fake_intent["slots"]["task_name"]["value"] == "купить хлеб"


@pytest.mark.asyncio
async def test_list_tasks_not_redirected_when_no_checklist_keyword() -> None:
    """on_list_tasks should NOT redirect for normal list queries."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_list_tasks

    message = _make_message(command="покажи задачи на сегодня")
    message.nlu = MagicMock()
    message.nlu.tokens = ["покажи", "задачи", "на", "сегодня"]
    message.nlu.intents = {"list_tasks": {"slots": {}}}
    message.nlu.entities = []

    intent_data: dict[str, Any] = {"slots": {}}
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    with patch(
        "alice_ticktick.dialogs.router.handle_list_tasks",
        new_callable=AsyncMock,
        return_value=MagicMock(text="На сегодня"),
    ) as mock_handler:
        await on_list_tasks(message, intent_data, event_update)
        mock_handler.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_list_tasks_redirects_to_show_checklist -v`
Expected: FAIL

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/router.py`, add regex and modify `on_list_tasks`:

```python
# Near top, after other regexes:
_SHOW_CHECKLIST_RE = re.compile(
    r"(?:покажи|какой|что)\s+(?:чеклист|список|пункты)\s+(?:у|для|в)?\s*(?:задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_SHOW_CHECKLIST_ALT_RE = re.compile(
    r"что\s+(?:в|из)\s+(?:чеклисте|списке)\s+(?:задачи?)?\s*(.+)",
    re.IGNORECASE,
)

# Modify on_list_tasks:
@router.message(IntentFilter(LIST_TASKS))
async def on_list_tasks(
    message: Message,
    intent_data: dict[str, Any],
    event_update: Update,
) -> Response:
    """Handle list_tasks intent."""
    utterance = (message.original_utterance or message.command or "").lower()
    if "чеклист" in utterance or "пункты" in utterance:
        raw = message.original_utterance or message.command or ""
        m = _SHOW_CHECKLIST_RE.search(raw) or _SHOW_CHECKLIST_ALT_RE.search(raw)
        if m:
            task_name = m.group(1).strip()
            fake_intent_data: dict[str, Any] = {
                "slots": {"task_name": {"value": task_name}}
            }
            return await handle_show_checklist(
                message, fake_intent_data, event_update=event_update
            )
    return await handle_list_tasks(message, intent_data, event_update=event_update)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers.py::test_list_tasks_redirects_to_show_checklist tests/test_handlers.py::test_list_tasks_not_redirected_when_no_checklist_keyword -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: redirect list_tasks → show_checklist when 'чеклист' in utterance"
```

---

### Task 3: Fix #5 — Delete FSM state persistence

**Files:**
- Modify: `alice_ticktick/main.py:16` (Dispatcher init)
- Modify: `tests/test_main.py` (update test)

**Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_dispatcher_uses_api_storage() -> None:
    """Dispatcher must use Alice API storage to persist FSM state across CF invocations."""
    from alice_ticktick.main import dp

    # Check that the use_api_storage middleware is registered
    from aliceio.fsm.middlewares.api_storage import FSMApiStorageMiddleware

    has_api_middleware = any(
        isinstance(m, FSMApiStorageMiddleware)
        for m in dp.update.middleware
    )
    assert has_api_middleware, "Dispatcher must use use_api_storage=True for serverless FSM"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py::test_dispatcher_uses_api_storage -v`
Expected: FAIL (default Dispatcher uses MemoryStorage)

**Step 3: Implement the fix**

In `alice_ticktick/main.py`, change line 16:

```python
# Before:
dp = Dispatcher()

# After:
dp = Dispatcher(use_api_storage=True)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS (existing tests should still pass)

**Step 5: Commit**

```bash
git add alice_ticktick/main.py tests/test_main.py
git commit -m "fix: enable API storage for FSM to persist state across CF invocations"
```

---

### Task 4: Fix #4 — create_task project slot extraction

**Files:**
- Modify: `alice_ticktick/dialogs/handlers/tasks.py:155-373` (handle_create_task)
- Test: `tests/test_handlers.py` (add new test)

**Step 1: Write the failing test**

Add to `tests/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_create_task_extracts_project_from_utterance() -> None:
    """When NLU .+ consumes 'в проекте X', handler should extract it from utterance."""
    task = _make_task(task_id="t1", title="Ревью кода", project_id="proj-inbox")
    project = Project(id="proj-inbox", name="Inbox")
    client = _make_mock_client(tasks=[task], projects=[project])

    message = _make_message(
        command="создай задачу кктест ревью кода в проекте Inbox"
    )
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "кктест", "ревью", "кода", "в", "проекте", "inbox"]
    message.nlu.intents = {}
    message.nlu.entities = []

    # NLU didn't extract project_name — .+ consumed it into task_name
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "кктест ревью кода в проекте Inbox"},
        }
    }
    event_update = MagicMock()
    event_update.meta.timezone = "Europe/Moscow"
    event_update.meta.interfaces.account_linking = None

    response = await handle_create_task(
        message, intent_data, type(client), event_update=event_update
    )
    assert "Готово" in response.text
    assert "кктест ревью кода" in response.text.lower().replace("ё", "е")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_create_task_extracts_project_from_utterance -v`
Expected: FAIL (task created with name including "в проекте Inbox")

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/handlers/tasks.py`, add regex near top (after imports):

```python
import re as _re

_PROJECT_FROM_UTTERANCE_RE = _re.compile(
    r"\s+в\s+(?:проект|список|папку)\s+(.+?)(?:\s+на\s+|\s+с\s+|$)",
    _re.IGNORECASE,
)
```

Then in `handle_create_task`, after `slots = extract_create_task_slots(intent_data)` (line 168) and before the task_name check (line 170), add:

```python
    # Fallback: extract 'в проекте X' from utterance if NLU missed it
    if not slots.project_name and slots.task_name:
        _proj_m = _PROJECT_FROM_UTTERANCE_RE.search(slots.task_name)
        if _proj_m:
            _extracted_project = _proj_m.group(1).strip()
            _cleaned_name = slots.task_name[: _proj_m.start()].strip()
            if _cleaned_name:
                slots = dataclasses.replace(
                    slots,
                    project_name=_extracted_project,
                    task_name=_cleaned_name,
                )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers.py -v -k create`
Expected: All create tests PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers/tasks.py tests/test_handlers.py
git commit -m "fix: extract 'в проекте X' from task_name when NLU misses project slot"
```

---

### Task 5: Fix #3 — search_task fallback for "поиск"

**Files:**
- Modify: `alice_ticktick/dialogs/router.py:483-488` (on_unknown, extend)
- Modify: `docs/grammars/search_task.grammar`
- Test: `tests/test_handlers.py` (add new test)

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_unknown_handler_catches_search_keywords() -> None:
    """on_unknown should detect 'поиск' and redirect to search."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поиск задачи молоко")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поиск", "задачи", "молоко"]
    message.nlu.intents = {}

    with patch(
        "alice_ticktick.dialogs.router.handle_search_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="Найдено"),
    ) as mock_handler:
        await on_unknown(message)
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        fake_intent = call_args[1]
        assert fake_intent["slots"]["query"]["value"] == "молоко"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_unknown_handler_catches_search_keywords -v`
Expected: FAIL

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/router.py`, extend `on_unknown`. Also add `event_update: Update` to the signature since `handle_search_task` needs it:

```python
_SEARCH_FALLBACK_RE = re.compile(
    r"(?:поиск|ищи)\s+(?:задачи?|задач)?\s*(.+)",
    re.IGNORECASE,
)

@router.message()
async def on_unknown(message: Message, event_update: Update) -> Response:
    """Fallback for unrecognized commands."""
    command_lower = (message.command or "").lower().strip()
    if command_lower in _GOODBYE_KEYWORDS:
        return await handle_goodbye(message)

    # Search fallback: "поиск задачи X"
    raw = message.original_utterance or message.command or ""
    m = _SEARCH_FALLBACK_RE.search(raw)
    if m:
        query = m.group(1).strip()
        if query:
            fake_intent_data: dict[str, Any] = {
                "slots": {"query": {"value": query}}
            }
            return await handle_search_task(message, fake_intent_data, event_update=event_update)

    return await handle_unknown(message)
```

Also update `docs/grammars/search_task.grammar`:

```
root:
    %lemma
    (найди | поищи | где | ищи) (задачу)? $Query
    поиск (задачи | задач)? $Query

slots:
    query:
        source: $Query
        type: YANDEX.STRING

$Query:
    .+
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers.py::test_unknown_handler_catches_search_keywords tests/test_handlers.py::test_unknown_handler_catches_goodbye_in_text_mode tests/test_handlers.py::test_unknown_handler_still_returns_unknown_for_normal_input -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py docs/grammars/search_task.grammar
git commit -m "fix: search fallback for 'поиск' in on_unknown + grammar update"
```

---

### Task 6: Fix #6 — recurring "каждый день" token extraction

**Files:**
- Modify: `alice_ticktick/dialogs/handlers/_helpers.py:85-107` (_infer_rec_freq_from_tokens)
- Test: `tests/test_handlers.py` (add new test)

**Step 1: Write the failing test**

```python
from alice_ticktick.dialogs.handlers._helpers import _infer_rec_freq_from_tokens


def test_infer_rec_freq_detects_kazhdy_den() -> None:
    """_infer_rec_freq should detect 'каждый день' in tokens."""
    tokens = ["напоминай", "каждый", "день", "пить", "воду"]
    result = _infer_rec_freq_from_tokens(None, tokens)
    assert result == "день"


def test_infer_rec_freq_detects_kazhduyu_nedelyu() -> None:
    """_infer_rec_freq should detect 'каждую неделю' in tokens."""
    tokens = ["напоминай", "каждую", "неделю", "проверить"]
    result = _infer_rec_freq_from_tokens(None, tokens)
    assert result == "неделю"


def test_infer_rec_freq_preserves_existing() -> None:
    """Should not override existing rec_freq."""
    tokens = ["каждый", "день"]
    result = _infer_rec_freq_from_tokens("понедельник", tokens)
    assert result == "понедельник"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_infer_rec_freq_detects_kazhdy_den -v`
Expected: FAIL (returns None)

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/handlers/_helpers.py`, replace `_infer_rec_freq_from_tokens`:

```python
_FIXED_RECURRENCE_TOKENS = frozenset(
    {
        "ежедневно",
        "еженедельно",
        "ежемесячно",
        "ежегодно",
    }
)

_KAZH_PREFIXES = frozenset({"каждый", "каждую", "каждое", "каждые"})
_FREQ_WORDS = frozenset(
    {
        "день", "дня", "дней",
        "неделю", "недели",
        "месяц", "месяца", "месяцев",
        "год", "года", "лет",
        "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
    }
)


def _infer_rec_freq_from_tokens(
    rec_freq: str | None,
    tokens: list[str] | None,
) -> str | None:
    """Если rec_freq не извлечён NLU, попробовать найти в токенах."""
    if rec_freq is not None:
        return rec_freq
    if not tokens:
        return None
    # Check for fixed recurrence tokens (ежедневно etc.)
    for token in tokens:
        if token.lower() in _FIXED_RECURRENCE_TOKENS:
            return token.lower()
    # Check for "каждый <freq>" pattern
    lower_tokens = [t.lower() for t in tokens]
    for i, token in enumerate(lower_tokens):
        if token in _KAZH_PREFIXES and i + 1 < len(lower_tokens):
            next_token = lower_tokens[i + 1]
            if next_token in _FREQ_WORDS:
                return next_token
    return None
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers.py -v -k "infer_rec_freq"`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers/_helpers.py tests/test_handlers.py
git commit -m "fix: detect 'каждый день' recurrence pattern from tokens"
```

---

### Task 7: Fix #1 — edit_task router fallback (16 tests)

This is the most complex fix. When NLU fails to recognize `edit_task` intent, utterances like "перенеси задачу X на завтра" fall to `on_unknown`. We add regex-based detection to redirect to `handle_edit_task`.

**Files:**
- Modify: `alice_ticktick/dialogs/router.py` (on_unknown, add edit fallback)
- Test: `tests/test_handlers.py` (add new tests)

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_unknown_catches_edit_date() -> None:
    """on_unknown detects 'перенеси задачу X на завтра' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="перенеси задачу тестовую на завтра")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перенеси", "задачу", "тестовую", "на", "завтра"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_catches_edit_priority() -> None:
    """on_unknown detects 'поменяй приоритет задачи X на высокий' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поменяй приоритет задачи тестовой на высокий")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поменяй", "приоритет", "задачи", "тестовой", "на", "высокий"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_catches_rename() -> None:
    """on_unknown detects 'переименуй задачу X в Y' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="переименуй задачу старое имя в новое имя")
    message.nlu = MagicMock()
    message.nlu.tokens = ["переименуй", "задачу", "старое", "имя", "в", "новое", "имя"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="обновлена"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["new_name"]["value"] == "новое имя"


@pytest.mark.asyncio
async def test_unknown_catches_move_project() -> None:
    """on_unknown detects 'перемести задачу X в проект Y' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="перемести задачу тестовую в проект Inbox")
    message.nlu = MagicMock()
    message.nlu.tokens = ["перемести", "задачу", "тестовую", "в", "проект", "inbox"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="перемещена"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["new_project"]["value"] == "Inbox"


@pytest.mark.asyncio
async def test_unknown_catches_remove_recurrence() -> None:
    """on_unknown detects 'убери повторение задачи X' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="убери повторение задачи тестовой")
    message.nlu = MagicMock()
    message.nlu.tokens = ["убери", "повторение", "задачи", "тестовой"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="убрано"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()
        fake_intent = mock_handler.call_args[0][1]
        assert fake_intent["slots"]["remove_recurrence"]["value"] is True


@pytest.mark.asyncio
async def test_unknown_catches_change_reminder() -> None:
    """on_unknown detects 'поменяй напоминание задачи X за 30 минут' as edit."""
    from unittest.mock import patch

    from alice_ticktick.dialogs.router import on_unknown

    message = _make_message(command="поменяй напоминание задачи тестовой за 30 минут")
    message.nlu = MagicMock()
    message.nlu.tokens = ["поменяй", "напоминание", "задачи", "тестовой", "за", "30", "минут"]
    message.nlu.intents = {}
    message.nlu.entities = []

    with patch(
        "alice_ticktick.dialogs.router.handle_edit_task",
        new_callable=AsyncMock,
        return_value=MagicMock(text="изменено"),
    ) as mock_handler:
        event_update = MagicMock()
        await on_unknown(message, event_update)
        mock_handler.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers.py -v -k "unknown_catches_edit"`
Expected: FAIL

**Step 3: Implement the fix**

In `alice_ticktick/dialogs/router.py`, add regex patterns and extend `on_unknown`:

```python
# --- Edit fallback regexes ---
_EDIT_RENAME_RE = re.compile(
    r"переименуй\s+(?:задачу\s+)?(.+?)\s+в\s+(.+)",
    re.IGNORECASE,
)
_EDIT_MOVE_RE = re.compile(
    r"(?:перемести|переложи|перекинь|отправь)\s+(?:задачу?\s+)?(.+?)\s+в\s+(?:проект|список|папку)\s+(.+)",
    re.IGNORECASE,
)
_EDIT_REMOVE_RECURRENCE_RE = re.compile(
    r"(?:убери|отмени|удали)\s+(?:повторение|повтор)\s+(?:у|для|задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_EDIT_REMOVE_REMINDER_RE = re.compile(
    r"(?:убери|отмени|удали)\s+напоминание\s+(?:у|для|задачи?)?\s*(.+)",
    re.IGNORECASE,
)
_EDIT_CHANGE_RECURRENCE_RE = re.compile(
    r"(?:поменяй|измени)\s+(?:повторение|повтор)\s+(?:у|для|задачи?)?\s*(.+?)\s+на\s+(.+)",
    re.IGNORECASE,
)
_EDIT_CHANGE_REMINDER_RE = re.compile(
    r"(?:поменяй|измени|поставь)\s+напоминание\s+(?:у|для|задачи?)?\s*(.+?)\s+за\s+(.+)",
    re.IGNORECASE,
)
_EDIT_GENERIC_RE = re.compile(
    r"(?:перенеси|поменяй|измени|сдвинь|обнови)\s+(?:задачу?\s+)?(.+)",
    re.IGNORECASE,
)
_EDIT_PRIORITY_RE = re.compile(
    r"(?:поменяй|измени)\s+приоритет\s+(?:задачи?)?\s*(.+?)\s+(?:на|в)\s+(низкий|средний|высокий)",
    re.IGNORECASE,
)

def _try_parse_edit_command(raw: str) -> dict[str, Any] | None:
    """Try to parse an edit command from raw utterance. Returns fake intent_data or None."""
    slots: dict[str, Any] = {}

    # Rename: "переименуй задачу X в Y"
    m = _EDIT_RENAME_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["new_name"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Move: "перемести задачу X в проект Y"
    m = _EDIT_MOVE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["new_project"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Remove recurrence: "убери повторение задачи X"
    m = _EDIT_REMOVE_RECURRENCE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["remove_recurrence"] = {"value": True}
        return {"slots": slots}

    # Remove reminder: "убери напоминание задачи X"
    m = _EDIT_REMOVE_REMINDER_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["remove_reminder"] = {"value": True}
        return {"slots": slots}

    # Change recurrence: "поменяй повторение задачи X на Y"
    m = _EDIT_CHANGE_RECURRENCE_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["rec_freq"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Change reminder: "поменяй напоминание задачи X за Y"
    m = _EDIT_CHANGE_REMINDER_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        slots["reminder_unit"] = {"value": m.group(2).strip()}
        return {"slots": slots}

    # Edit priority: "поменяй приоритет задачи X на высокий"
    m = _EDIT_PRIORITY_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        # new_priority isn't a grammar slot; handler reads from tokens
        return {"slots": slots}

    # Generic edit: "перенеси задачу X на завтра"
    m = _EDIT_GENERIC_RE.search(raw)
    if m:
        slots["task_name"] = {"value": m.group(1).strip()}
        return {"slots": slots}

    return None
```

Then extend `on_unknown` (note: now needs `state` and `event_update`):

```python
@router.message()
async def on_unknown(message: Message, state: FSMContext, event_update: Update) -> Response:
    """Fallback for unrecognized commands."""
    command_lower = (message.command or "").lower().strip()
    if command_lower in _GOODBYE_KEYWORDS:
        return await handle_goodbye(message)

    raw = message.original_utterance or message.command or ""

    # Search fallback
    m = _SEARCH_FALLBACK_RE.search(raw)
    if m:
        query = m.group(1).strip()
        if query:
            fake_intent_data: dict[str, Any] = {
                "slots": {"query": {"value": query}}
            }
            return await handle_search_task(message, fake_intent_data, event_update=event_update)

    # Edit fallback
    edit_intent = _try_parse_edit_command(raw)
    if edit_intent is not None:
        return await handle_edit_task(message, edit_intent, state, event_update=event_update)

    return await handle_unknown(message)
```

Add `FSMContext` import if missing (it's already imported via TYPE_CHECKING).

**Step 4: Run tests**

Run: `uv run pytest tests/test_handlers.py -v -k "unknown_catches"`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: edit_task fallback in on_unknown for 16 NLU grammar failures"
```

---

### Task 8: Update xfail markers on e2e tests

After deploying code fixes, update the e2e tests to remove `xfail` markers for bugs that are now fixed via code-level fallbacks.

**Files:**
- Modify: `tests/e2e/test_e2e_edit.py` — remove `_XFAIL` from all 16 tests
- Modify: `tests/e2e/test_e2e_checklists.py` — remove xfail from test_show_checklist, test_show_checklist_alt
- Modify: `tests/e2e/test_e2e_search.py` — remove `_SEARCH_XFAIL` from test_search_milk
- Modify: `tests/e2e/test_e2e_delete.py` — remove xfail from 2 delete confirm tests
- Modify: `tests/e2e/test_e2e_recurring.py` — remove xfail from test_recurring_every_day
- Modify: `tests/e2e/test_e2e_regression.py` — remove xfail from test_goodbye_text_mode
- Modify: `tests/e2e/test_e2e_create.py` — remove xfail from test_create_with_project

**Step 1: Remove all xfail markers**

In each file, remove the `@pytest.mark.xfail(...)` decorator and any unused `_XFAIL` / `_SEARCH_XFAIL` variables.

**Step 2: Run unit tests to confirm nothing breaks**

Run: `uv run pytest tests/ -v --ignore=tests/e2e`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/e2e/
git commit -m "test: remove xfail markers for bugs fixed by code-level fallbacks"
```

---

### Task 9: Final verification

**Step 1: Run full CI locally**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy alice_ticktick/
uv run pytest tests/ -v --ignore=tests/e2e
```

All must pass.

**Step 2: Run e2e tests (if deployed)**

```bash
uv run pytest tests/e2e/ -v --timeout=60
```

Note: e2e tests require deployed skill. The code-level fixes work locally but e2e tests run against the live skill in Yandex Cloud. Deploy first, then run e2e.

---

## Notes

- **Grammar files** (`docs/grammars/search_task.grammar`) are updated locally. They must be manually deployed to Yandex Dialogs via the browser console.
- **FSM `use_api_storage=True`** requires Alice to send `state` field in requests. This works in production but may need mock adjustments in unit tests.
- **Edit fallback** (`_try_parse_edit_command`) is a workaround — the proper fix is updating the `edit_task` grammar in Yandex Dialogs. The code fallback provides resilience when NLU fails.
