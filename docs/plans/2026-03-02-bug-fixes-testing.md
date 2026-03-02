# Bug Fixes After Voice Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Исправить 6 багов, найденных в ходе голосового тестирования навыка 2026-03-02.

**Architecture:** Все исправления — в Python-коде (`handlers.py`, `router.py`), изменения NLU-грамматик не требуются. Новая логика добавляется в виде вспомогательных функций; существующие публичные сигнатуры не меняются. TDD: сначала падающий тест, потом минимальный фикс.

**Tech Stack:** Python 3.13, pytest, pytest-asyncio, unittest.mock, aliceio, alice_ticktick

---

## Контекст багов

| # | Баг | Симптом | Root cause |
|---|-----|---------|-----------|
| 1 | `create_task` без названия | Задача создаётся с именем "задачу" | `$TaskName: .+` захватывает слово "задачу" |
| 2 | Название с суффиксом напоминания | "встреча с напоминанием за 30 минут" → имя задачи содержит суффикс | Жадный `.+` захватывает "с напоминанием за..." в task_name |
| 2b | Напоминание сохраняется как 30 дней вместо 30 минут | TickTick показывает 30 дней | Нужно проверить формат TRIGGER; возможно TickTick не поддерживает PT-нотацию |
| 3 | `create_task` с "ежедневно" — повторение не создаётся | Задача без RRULE | "ежедневно" не захватывается в слот `$RecFreq` |
| 4 | `delete_task` — ответ "нет" → "Не поняла команду" | FSM-состояние теряется | MemoryStorage не переживает между инвокациями Lambda |
| 5 | `add_checklist_item` перехватывается `create_task` | Создаётся задача "пункт молоко в чеклист задачи покупки" | NLU не распознаёт `add_checklist_item`, файрится `create_task` |
| 6 | `create_recurring_task` "напоминай ежедневно" — без повторения | То же, что баг 3 | Тот же root cause |

---

## Task 1: БАГ 1 — task_name = "задачу" при `create_task` без названия

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py` (~строка 290)
- Test: `tests/test_handlers.py`

**Step 1: Write failing test**

Добавить в `tests/test_handlers.py` (в секцию create_task):

```python
async def test_create_task_name_is_stopword_asks_for_name() -> None:
    """Если task_name — это только слово 'задачу', переспросить название."""
    message = _make_message(command="создай задачу")
    message.nlu = None
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задачу"}}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED


async def test_create_task_name_is_zadacha_variant_asks_for_name() -> None:
    """'задача', 'задачи' тоже стоп-слова."""
    message = _make_message(command="новая задача")
    message.nlu = None
    intent_data: dict[str, Any] = {"slots": {"task_name": {"value": "задача"}}}
    response = await handle_create_task(message, intent_data)
    assert response.text == txt.TASK_NAME_REQUIRED
```

**Step 2: Run, verify FAIL**

```bash
uv run pytest tests/test_handlers.py::test_create_task_name_is_stopword_asks_for_name -v
```
Expected: FAIL — тест упадёт, так как сейчас код создаёт задачу.

**Step 3: Implement fix**

В `alice_ticktick/dialogs/handlers.py`, после строки 290 (`if not slots.task_name:`), добавить:

```python
# Стоп-слова: NLU захватывает слово "задачу" как task_name при "создай задачу"
_TASK_NAME_STOPWORDS = frozenset({
    "задачу", "задача", "задачи", "задаче",
    "напоминание", "напоминания",
})

async def handle_create_task(...) -> Response:
    ...
    slots = extract_create_task_slots(intent_data)

    if not slots.task_name:
        return Response(text=txt.TASK_NAME_REQUIRED)

    # NEW: если task_name — это только стоп-слово, переспросить
    if slots.task_name.lower().strip() in _TASK_NAME_STOPWORDS:
        return Response(text=txt.TASK_NAME_REQUIRED)
```

Константу `_TASK_NAME_STOPWORDS` добавить на уровне модуля (перед функцией `handle_create_task`).

**Step 4: Run, verify PASS**

```bash
uv run pytest tests/test_handlers.py::test_create_task_name_is_stopword_asks_for_name tests/test_handlers.py::test_create_task_name_is_zadacha_variant_asks_for_name -v
```
Expected: PASS

**Step 5: Run full suite, verify no regression**

```bash
uv run pytest -v
```
Expected: все тесты зелёные.

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "fix: create_task без названия — переспрашивать вместо создания задачи 'задачу'"
```

---

## Task 2: БАГ 2 — Название задачи поглощает "с напоминанием за N минут"

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Test: `tests/test_handlers.py`

**Context:**
NLU-слот `$TaskName: .+` жадно захватывает "с напоминанием за 30 минут" как часть имени задачи.
Фикс: после извлечения task_name обрезать trailing-паттерн `с напоминанием за ...` через regex.

**Step 1: Write failing test**

```python
async def test_create_task_strips_reminder_suffix_from_name() -> None:
    """task_name 'встреча с напоминанием за 30 минут' → должно стать 'встреча'."""
    message = _make_message(command="создай задачу встреча с напоминанием за 30 минут")
    message.nlu = None
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "встреча с напоминанием за 30 минут"},
            "reminder_value": {"value": 30},
            "reminder_unit": {"value": "минут"},
        }
    }
    response = await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    created_payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert created_payload.title == "встреча"


async def test_create_task_strips_reminder_suffix_without_value() -> None:
    """'позвонить врачу с напоминанием за час' → 'позвонить врачу'."""
    message = _make_message(command="создай задачу позвонить врачу с напоминанием за час")
    message.nlu = None
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "позвонить врачу с напоминанием за час"},
            "reminder_unit": {"value": "час"},
        }
    }
    response = await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    created_payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert created_payload.title == "позвонить врачу"
```

**Step 2: Run, verify FAIL**

```bash
uv run pytest tests/test_handlers.py::test_create_task_strips_reminder_suffix_from_name -v
```
Expected: FAIL — `created_payload.title` будет `"встреча с напоминанием за 30 минут"`.

**Step 3: Implement fix**

Добавить в `handlers.py` на уровне модуля:

```python
import re

_REMINDER_SUFFIX_RE = re.compile(
    r"\s+с\s+напоминанием\s+за\s+(?:\d+\s+)?(?:минуту|минуты|минут|час|часа|часов|день|дня|дней)\s*$",
    re.IGNORECASE,
)
```

В `handle_create_task`, сразу после проверки на стоп-слово (Task 1 fix), добавить:

```python
task_name = slots.task_name
# NEW: обрезать суффикс "с напоминанием за N единиц" из названия задачи
if slots.reminder_unit is not None:
    task_name = _REMINDER_SUFFIX_RE.sub("", task_name).strip()
    if not task_name:
        return Response(text=txt.TASK_NAME_REQUIRED)
```

**Step 4: Run, verify PASS**

```bash
uv run pytest tests/test_handlers.py::test_create_task_strips_reminder_suffix_from_name tests/test_handlers.py::test_create_task_strips_reminder_suffix_without_value -v
```
Expected: PASS

**Step 5: Run full suite**

```bash
uv run pytest -v
```

**Step 6: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "fix: обрезать суффикс 'с напоминанием за...' из названия задачи"
```

---

## Task 3: БАГ 2b — Проверить формат TRIGGER для TickTick API (30 минут vs 30 дней)

**Files:**
- Read: `alice_ticktick/dialogs/nlp/reminder_parser.py`
- Test: `tests/test_reminder_parser.py`

**Context:**
`build_trigger(30, "минут")` возвращает `"TRIGGER:-PT30M"`. Пользователь видит в TickTick "30 дней".
Нужно проверить, правильно ли TickTick интерпретирует TRIGGER:-PT30M.

**Step 1: Изучить существующие тесты reminder_parser**

```bash
uv run pytest tests/test_reminder_parser.py -v
```

**Step 2: Проверить формат через unit-тест**

Добавить в `tests/test_reminder_parser.py`:

```python
def test_build_trigger_minutes_uses_T_notation() -> None:
    """TRIGGER:-PT30M — минуты требуют T-нотацию (time duration)."""
    result = build_trigger(30, "минут")
    assert result == "TRIGGER:-PT30M"
    # Не P30M (что было бы 30 месяцев!) и не P30D (30 дней)
    assert "PT" in result


def test_build_trigger_days_uses_D_notation() -> None:
    """TRIGGER:-P1D — дни используют date-нотацию без T."""
    result = build_trigger(1, "день")
    assert result == "TRIGGER:-P1D"
    assert "PT" not in result
```

**Step 3: Run**

```bash
uv run pytest tests/test_reminder_parser.py -v
```
Expected: PASS (формат уже правильный).

**Step 4: Если TickTick хранит неверно — добавить интеграционный тест**

Если после ручной проверки в TickTick подтверждается, что "TRIGGER:-PT30M" интерпретируется как 30 дней, нужно изменить формат. Возможные варианты:
- TickTick может ожидать отрицательные минуты: `"-30"` (integer, минуты)
- Или `"TRIGGER:PT30M"` без знака минуса

В этом случае исправить `build_trigger` и формат строки, обновить тесты.

**Step 5: Commit (если были изменения)**

```bash
git add alice_ticktick/dialogs/nlp/reminder_parser.py tests/test_reminder_parser.py
git commit -m "fix: формат TRIGGER для напоминаний в TickTick API"
```

---

## Task 4: БАГ 3 & 6 — "ежедневно"/"еженедельно"/"ежемесячно" не создают повторение

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Test: `tests/test_handlers.py`

**Context:**
В грамматике `create_task.grammar` и `create_recurring_task.grammar`, `$Recurrence` матчит "ежедневно" как литерал, но `$RecFreq` не заполняется. Значит `slots.rec_freq = None` и `build_rrule(None)` = None.
Фикс: в обработчиках, если `rec_freq is None`, просканировать токены NLU на наличие fixed-recurrence слов.

**Step 1: Write failing test (БАГ 3 — create_task)**

```python
async def test_create_task_ejednevno_creates_daily_rrule() -> None:
    """'создай задачу зарядка ежедневно' → RRULE:FREQ=DAILY."""
    message = _make_message(command="создай задачу зарядка ежедневно")
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "зарядка", "ежедневно"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "зарядка"},
            # rec_freq НЕ заполнен NLU (баг)
        }
    }
    response = await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeatFlag == "RRULE:FREQ=DAILY"


async def test_create_task_ezhenedelno_creates_weekly_rrule() -> None:
    """'создай задачу уборка еженедельно' → RRULE:FREQ=WEEKLY."""
    message = _make_message(command="создай задачу уборка еженедельно")
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "уборка", "еженедельно"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {"task_name": {"value": "уборка"}}
    }
    response = await handle_create_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeatFlag == "RRULE:FREQ=WEEKLY"
```

**Step 2: Write failing test (БАГ 6 — create_recurring_task)**

```python
async def test_create_recurring_task_ejednevno_creates_daily_rrule() -> None:
    """'напоминай ежедневно делать зарядку' → RRULE:FREQ=DAILY."""
    message = _make_message(command="напоминай ежедневно делать зарядку")
    message.nlu = MagicMock()
    message.nlu.tokens = ["напоминай", "ежедневно", "делать", "зарядку"]
    message.nlu.entities = []
    message.nlu.intents = {}
    factory = _make_mock_client()
    intent_data: dict[str, Any] = {
        "slots": {
            "task_name": {"value": "делать зарядку"},
            # rec_freq НЕ заполнен NLU (баг)
        }
    }
    response = await handle_create_recurring_task(message, intent_data, ticktick_client_factory=factory)
    payload = factory.return_value.__aenter__.return_value.create_task.call_args[0][0]
    assert payload.repeatFlag == "RRULE:FREQ=DAILY"
```

**Step 3: Run, verify FAIL**

```bash
uv run pytest tests/test_handlers.py::test_create_task_ejednevno_creates_daily_rrule -v
```
Expected: FAIL — `payload.repeatFlag` будет None.

**Step 4: Implement fix**

Добавить в `handlers.py` на уровне модуля:

```python
_FIXED_RECURRENCE_TOKENS = frozenset({
    "ежедневно", "еженедельно", "ежемесячно", "ежегодно",
})


def _infer_rec_freq_from_tokens(
    rec_freq: str | None,
    tokens: list[str] | None,
) -> str | None:
    """Если rec_freq не извлечён NLU, попробовать найти в токенах."""
    if rec_freq is not None:
        return rec_freq
    if not tokens:
        return None
    for token in tokens:
        if token.lower() in _FIXED_RECURRENCE_TOKENS:
            return token.lower()
    return None
```

В `handle_create_task`, заменить:
```python
# Parse recurrence
repeat_flag = build_rrule(
    rec_freq=slots.rec_freq,
    ...
)
```
На:
```python
# Parse recurrence — fallback: проверить токены, если NLU не заполнил rec_freq
_tokens = message.nlu.tokens if message.nlu else None
effective_rec_freq = _infer_rec_freq_from_tokens(slots.rec_freq, _tokens)
repeat_flag = build_rrule(
    rec_freq=effective_rec_freq,
    rec_interval=slots.rec_interval,
    rec_monthday=slots.rec_monthday,
)
```

**Step 5: Run, verify PASS**

```bash
uv run pytest tests/test_handlers.py::test_create_task_ejednevno_creates_daily_rrule tests/test_handlers.py::test_create_task_ezhenedelno_creates_weekly_rrule tests/test_handlers.py::test_create_recurring_task_ejednevno_creates_daily_rrule -v
```

**Step 6: Run full suite**

```bash
uv run pytest -v
```

**Step 7: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers.py
git commit -m "fix: 'ежедневно'/'еженедельно' в create_task и create_recurring_task создают RRULE"
```

---

## Task 5: БАГ 4 — FSM delete confirmation не переживает между инвокациями

**Files:**
- Modify: `alice_ticktick/main.py`
- Test: `tests/test_handlers.py` (проверить что on_delete_other работает)

**Context:**
`Dispatcher()` по умолчанию использует `MemoryStorage`. Каждая инвокация Yandex Cloud Functions — новый процесс. FSM-состояние `DeleteTaskStates.confirm` теряется.

Aliceio поддерживает хранение FSM-состояния в сессии Алисы через `session_state`. Нужно использовать `AliceMemoryStorage` (или аналог из aliceio).

**Step 1: Найти правильный класс storage в aliceio**

```bash
python -c "import aliceio; print(dir(aliceio))"
python -c "from aliceio.fsm.storage import memory; print(dir(memory))"
# Или:
python -c "import aliceio.fsm.storage.memory as m; print(dir(m))"
```

Ожидается найти класс типа `AliceMemoryStorage` или `SessionStorage`.

**Step 2: Write failing test**

В `tests/test_handlers.py`, убедиться, что при FSM-состоянии REJECT обрабатывается:

```python
async def test_delete_reject_returns_cancel_message() -> None:
    """handle_delete_reject должен вернуть DELETE_CANCELLED."""
    from unittest.mock import AsyncMock
    from alice_ticktick.dialogs.states import DeleteTaskStates

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"task_id": "t1", "task_name": "купить хлеб", "project_id": "p1"})
    state.clear = AsyncMock()

    message = _make_message()
    response = await handle_delete_reject(message, state)
    assert response.text == txt.DELETE_CANCELLED
    state.clear.assert_called_once()
```

**Step 3: Run existing reject test to understand current state**

```bash
uv run pytest tests/test_handlers.py -k "delete" -v
```

**Step 4: Configure persistent FSM storage in main.py**

Проверить какой storage доступен в aliceio и настроить в `main.py`:

```python
# Если aliceio предоставляет сессионное хранилище:
from aliceio.fsm.storage.memory import MemoryStorage
# ИЛИ session-based:
# from aliceio.fsm.storage.alice import AliceMemoryStorage

# Вариант A: если есть AliceMemoryStorage (хранит в session.state Алисы)
dp = Dispatcher(storage=AliceMemoryStorage())

# Вариант B: если нет — добавить токен-матчинг в on_delete_other
```

**Вариант B (fallback если нет session storage):**

Если в aliceio нет сессионного хранилища, добавить ручной матчинг в `router.py` в `on_delete_other`:

```python
_CONFIRM_TOKENS = frozenset({"да", "конечно", "подтверждаю", "ладно", "давай", "удали"})
_REJECT_TOKENS = frozenset({"нет", "отмена", "отменить", "не надо", "не удаляй"})

@router.message(DeleteTaskStates.confirm)
async def on_delete_other(message: Message, state: FSMContext) -> Response:
    tokens = set(message.nlu.tokens or []) if message.nlu else set()
    command_lower = (message.command or "").lower().strip()

    if tokens & _REJECT_TOKENS or command_lower in _REJECT_TOKENS:
        return await handle_delete_reject(message, state)
    if tokens & _CONFIRM_TOKENS or command_lower in _CONFIRM_TOKENS:
        return await handle_delete_confirm(message, state)

    data = await state.get_data()
    retries = data.get("_confirm_retries", 0) + 1
    if retries >= _MAX_CONFIRM_RETRIES:
        await state.clear()
        return Response(text=txt.DELETE_CANCELLED)
    await state.set_data({**data, "_confirm_retries": retries})
    return Response(text=txt.DELETE_CONFIRM_PROMPT)
```

**Step 5: Write test for token-based reject**

```python
async def test_delete_other_handles_net_as_reject() -> None:
    """'нет' в состоянии confirm должен отменять удаление даже без YANDEX.REJECT."""
    from aliceio.fsm.context import FSMContext
    from unittest.mock import AsyncMock

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"task_id": "t1", "task_name": "купить хлеб", "project_id": "p1"})
    state.clear = AsyncMock()

    message = _make_message(command="нет")
    message.nlu = MagicMock()
    message.nlu.tokens = ["нет"]

    response = await on_delete_other(message, state)
    assert response.text == txt.DELETE_CANCELLED
```

**Step 6: Run tests**

```bash
uv run pytest tests/test_handlers.py -k "delete" -v
```

**Step 7: Run full suite**

```bash
uv run pytest -v
```

**Step 8: Commit**

```bash
git add alice_ticktick/main.py alice_ticktick/dialogs/router.py tests/test_handlers.py
git commit -m "fix: delete_task — 'нет' отменяет удаление даже без YANDEX.REJECT"
```

---

## Task 6: БАГ 5 — `add_checklist_item` перехватывается `create_task`

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`
- Test: `tests/test_handlers_phase3.py`

**Context:**
NLU не распознаёт `add_checklist_item` для "добавь пункт X в чеклист задачи Y" — файрится только `create_task`.
Роутер вызывает `on_create_task`, который создаёт задачу с именем "пункт X в чеклист задачи Y".

Фикс: в `on_create_task` добавить проверку токенов и при наличии ключевых слов чеклиста диспетчеризировать в `handle_add_checklist_item` через regex-парсинг.

**Step 1: Write failing integration test**

```python
async def test_on_create_task_dispatches_to_checklist_when_checklist_keywords() -> None:
    """
    Если NLU распознал create_task, но в токенах есть 'пункт' + 'чеклист',
    роутер должен обработать как add_checklist_item.
    """
    from alice_ticktick.dialogs.router import on_create_task
    from alice_ticktick.dialogs.intents import CREATE_TASK

    message = _make_message()
    message.command = "добавь пункт молоко в чеклист задачи покупки"
    message.nlu = MagicMock()
    message.nlu.tokens = ["добавь", "пункт", "молоко", "в", "чеклист", "задачи", "покупки"]
    message.nlu.intents = {
        CREATE_TASK: {"slots": {"task_name": {"value": "пункт молоко в чеклист задачи покупки"}}}
    }

    task = _make_task(title="Список покупок")
    factory = _make_mock_client(tasks=[task])

    intent_data = message.nlu.intents[CREATE_TASK]
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    response = await on_create_task(message, intent_data, event_update)

    # НЕ должно быть создано новой задачи
    factory.return_value.__aenter__.return_value.create_task.assert_not_called()
    # Должно найти задачу "покупки" и попытаться добавить пункт
    assert "молоко" in response.text or "покупки" in response.text.lower()
```

**Step 2: Run, verify FAIL**

```bash
uv run pytest tests/test_handlers_phase3.py::test_on_create_task_dispatches_to_checklist_when_checklist_keywords -v
```

**Step 3: Implement fix in router.py**

Добавить в `router.py` на уровне модуля:

```python
import re

_CHECKLIST_KEYWORDS = frozenset({"чеклист", "чеклиста", "чеклисте", "чеклисту"})
_ITEM_KEYWORDS = frozenset({"пункт", "элемент", "пункте", "пункта"})

_CHECKLIST_ITEM_RE = re.compile(
    r"(?:добавь|добавить)\s+(?:пункт|элемент)\s+(.+?)\s+(?:в|к)\s+(?:чеклист|список)\s+(?:задачи?\s+)?(.+)",
    re.IGNORECASE,
)


def _try_parse_checklist_command(command: str) -> tuple[str, str] | None:
    """Попытаться извлечь item_name и task_name из команды чеклиста."""
    m = _CHECKLIST_ITEM_RE.search(command)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None
```

Изменить `on_create_task` в `router.py`:

```python
@router.message(IntentFilter(CREATE_TASK))
async def on_create_task(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_task intent."""
    # Проверка: не является ли это командой add_checklist_item
    if message.nlu:
        tokens = set(message.nlu.tokens or [])
        if tokens & _CHECKLIST_KEYWORDS and tokens & _ITEM_KEYWORDS:
            # NLU не распознал add_checklist_item, пробуем парсить руками
            parsed = _try_parse_checklist_command(message.command or "")
            if parsed:
                item_name, task_name = parsed
                fake_intent_data: dict[str, Any] = {
                    "slots": {
                        "item_name": {"value": item_name},
                        "task_name": {"value": task_name},
                    }
                }
                return await handle_add_checklist_item(
                    message, fake_intent_data, event_update=event_update
                )
    return await handle_create_task(message, intent_data, event_update=event_update)
```

**Step 4: Run, verify PASS**

```bash
uv run pytest tests/test_handlers_phase3.py::test_on_create_task_dispatches_to_checklist_when_checklist_keywords -v
```

**Step 5: Добавить тест отсутствия регрессии (обычная команда create_task не ломается)**

```python
async def test_on_create_task_normal_command_not_affected() -> None:
    """Обычная 'создай задачу купить хлеб' не перехватывается диспетчером чеклиста."""
    from alice_ticktick.dialogs.router import on_create_task
    from alice_ticktick.dialogs.intents import CREATE_TASK

    message = _make_message()
    message.command = "создай задачу купить хлеб"
    message.nlu = MagicMock()
    message.nlu.tokens = ["создай", "задачу", "купить", "хлеб"]
    message.nlu.intents = {
        CREATE_TASK: {"slots": {"task_name": {"value": "купить хлеб"}}}
    }
    factory = _make_mock_client()
    intent_data = message.nlu.intents[CREATE_TASK]
    event_update = MagicMock()
    event_update.meta.interfaces.account_linking = None

    response = await on_create_task(message, intent_data, event_update)
    factory.return_value.__aenter__.return_value.create_task.assert_called_once()
```

**Step 6: Run full suite**

```bash
uv run pytest -v
```

**Step 7: Commit**

```bash
git add alice_ticktick/dialogs/router.py tests/test_handlers_phase3.py
git commit -m "fix: add_checklist_item — диспетчеризация при перехвате create_task через regex"
```

---

## Task 7: Финальная проверка + линтинг

**Step 1: Запустить линтер**

```bash
uv run ruff check .
```

**Step 2: Форматирование**

```bash
uv run ruff format .
```

**Step 3: Проверка типов**

```bash
uv run mypy alice_ticktick/
```

**Step 4: Полный прогон тестов**

```bash
uv run pytest -v
```
Expected: все тесты зелёные.

**Step 5: Финальный коммит если были правки**

```bash
git add -u
git commit -m "style: ruff fixes after bug fixes"
```

---

## Порядок выполнения

1. Task 1 (БАГ 1) → Task 2 (БАГ 2) → Task 4 (БАГ 3&6) — все в `handlers.py`, делать последовательно
2. Task 3 (БАГ 2b) — независимо, можно параллельно или после Task 2
3. Task 5 (БАГ 4) — независимо, в `router.py`
4. Task 6 (БАГ 5) — независимо, в `router.py`
5. Task 7 — финальная проверка

Tasks 3, 5, 6 можно делать параллельно после Tasks 1-2.
