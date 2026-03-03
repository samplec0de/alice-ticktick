# FR-17 Управление проектами + фикс welcome TTS — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the welcome TTS bug (infinite loading) and implement FR-17 project management (list/view/create projects) via TickTick API v1.

**Architecture:** Three new handlers + one new API method. Reuse existing `get_projects()`, `get_tasks()`, add `create_project()`. New NLU intents: `list_projects`, `project_tasks`, `create_project`. TDD throughout.

**Tech Stack:** Python 3.12+, aliceio, httpx, rapidfuzz, pytest + pytest-asyncio

---

### Task 1: Fix welcome TTS bug

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py:4-7`
- Modify: `tests/test_handlers.py:132-136`

**Step 1: Update the test to verify TTS contains speech text**

In `tests/test_handlers.py`, update `test_handle_welcome`:

```python
async def test_handle_welcome() -> None:
    message = _make_message(new=True)
    response = await handle_welcome(message)
    assert response.text == txt.WELCOME
    assert response.tts == txt.WELCOME_TTS
    assert "Слушаю" in response.tts
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handlers.py::test_handle_welcome -v`
Expected: FAIL — current TTS is only a `<speaker>` tag without "Слушаю"

**Step 3: Fix WELCOME_TTS and WELCOME_BACK_TTS**

In `alice_ticktick/dialogs/responses.py`, change:

```python
WELCOME = "Слушаю!"
WELCOME_TTS = '<speaker audio="alice-sounds-things-bell-1"> Слушаю!'
WELCOME_BACK = "С возвращением!"
WELCOME_BACK_TTS = '<speaker audio="alice-sounds-things-bell-1"> С возвращением!'
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_handlers.py::test_handle_welcome -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/responses.py tests/test_handlers.py
git commit -m "fix: welcome TTS — добавлен голосовой текст после звукового эффекта"
```

---

### Task 2: Add `create_project` to TickTick client

**Files:**
- Modify: `alice_ticktick/ticktick/client.py` (add method)
- Modify: `tests/test_ticktick_client.py` (add test)

**Step 1: Write the failing test**

In `tests/test_ticktick_client.py`, add:

```python
async def test_create_project(mock_response: MockResponse) -> None:
    mock_response.json_data = {"id": "proj-new", "name": "Travel"}
    mock_response.status_code = 200

    client = TickTickClient("token")
    project = await client.create_project("Travel")

    assert project.id == "proj-new"
    assert project.name == "Travel"
```

Follow the existing test patterns in this file for mock setup.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ticktick_client.py::test_create_project -v`
Expected: FAIL — `create_project` method not found

**Step 3: Implement `create_project`**

In `alice_ticktick/ticktick/client.py`, add after the `get_projects` method:

```python
async def create_project(self, name: str) -> Project:
    """Create a new project."""
    response = await self._client.post("/project", json={"name": name})
    _raise_for_status(response)
    return Project.model_validate(response.json())
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ticktick_client.py::test_create_project -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/ticktick/client.py tests/test_ticktick_client.py
git commit -m "feat: метод create_project в TickTick клиенте"
```

---

### Task 3: Add project intents and slot extractors

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py` (add constants, dataclasses, extractors)
- Modify: `tests/test_intents.py` (add tests)

**Step 1: Write the failing tests**

In `tests/test_intents.py`, add tests for new extractors:

```python
from alice_ticktick.dialogs.intents import (
    LIST_PROJECTS,
    PROJECT_TASKS,
    CREATE_PROJECT,
    extract_project_tasks_slots,
    extract_create_project_slots,
    ProjectTasksSlots,
    CreateProjectSlots,
)


def test_list_projects_intent_id() -> None:
    assert LIST_PROJECTS == "list_projects"


def test_project_tasks_intent_id() -> None:
    assert PROJECT_TASKS == "project_tasks"


def test_create_project_intent_id() -> None:
    assert CREATE_PROJECT == "create_project"


def test_extract_project_tasks_slots() -> None:
    data = {"slots": {"project_name": {"value": "Работа"}}}
    slots = extract_project_tasks_slots(data)
    assert slots.project_name == "Работа"


def test_extract_project_tasks_slots_empty() -> None:
    slots = extract_project_tasks_slots({"slots": {}})
    assert slots.project_name is None


def test_extract_create_project_slots() -> None:
    data = {"slots": {"project_name": {"value": "Travel"}}}
    slots = extract_create_project_slots(data)
    assert slots.project_name == "Travel"


def test_extract_create_project_slots_empty() -> None:
    slots = extract_create_project_slots({"slots": {}})
    assert slots.project_name is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_intents.py -k "project" -v`
Expected: FAIL — import errors

**Step 3: Implement intents**

In `alice_ticktick/dialogs/intents.py`:

Add intent constants (after `ADD_REMINDER`):
```python
LIST_PROJECTS = "list_projects"
PROJECT_TASKS = "project_tasks"
CREATE_PROJECT = "create_project"
```

Add to `ALL_INTENTS` frozenset: `LIST_PROJECTS`, `PROJECT_TASKS`, `CREATE_PROJECT`.

Add dataclasses:
```python
@dataclass(frozen=True, slots=True)
class ProjectTasksSlots:
    """Extracted slots for project_tasks intent."""
    project_name: str | None = None


@dataclass(frozen=True, slots=True)
class CreateProjectSlots:
    """Extracted slots for create_project intent."""
    project_name: str | None = None
```

Add extractors:
```python
def extract_project_tasks_slots(intent_data: dict[str, Any]) -> ProjectTasksSlots:
    return ProjectTasksSlots(project_name=_get_slot_value(intent_data, "project_name"))


def extract_create_project_slots(intent_data: dict[str, Any]) -> CreateProjectSlots:
    return CreateProjectSlots(project_name=_get_slot_value(intent_data, "project_name"))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_intents.py -k "project" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/intents.py tests/test_intents.py
git commit -m "feat: интенты list_projects, project_tasks, create_project"
```

---

### Task 4: Add response text constants for projects

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py`

**Step 1: Add response constants**

In `alice_ticktick/dialogs/responses.py`, add before `# Unknown`:

```python
# Projects
PROJECTS_LIST = "Ваши проекты ({count}):\n{projects}"
NO_PROJECTS = "У вас пока нет проектов."
PROJECT_TASKS_HEADER = "Задачи проекта «{project}» ({count}):\n{tasks}"
PROJECT_NO_TASKS = "В проекте «{project}» задач нет."
PROJECT_CREATED = "Проект «{name}» создан."
PROJECT_NAME_REQUIRED = "Как назвать проект? Скажите название."
PROJECT_CREATE_ERROR = "Не удалось создать проект. Попробуйте ещё раз."
PROJECT_TASKS_NAME_REQUIRED = "Какой проект показать? Скажите название."
```

**Step 2: Update HELP text**

Add a line to HELP:
```python
"- Проекты: «какие у меня проекты?», «задачи проекта Работа», «создай проект»\n"
```

Insert it before the last line (чеклист).

**Step 3: Commit**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: response-тексты для управления проектами + обновление HELP"
```

---

### Task 5: Implement `handle_list_projects`

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Create: `tests/test_handlers_projects.py`

**Step 1: Write failing tests**

Create `tests/test_handlers_projects.py`:

```python
"""Tests for project management handlers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.handlers import (
    _reset_project_cache,
    handle_list_projects,
)
from alice_ticktick.ticktick.models import Project


@pytest.fixture(autouse=True)
def _clear_project_cache() -> None:
    _reset_project_cache()


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


def _make_project(*, project_id: str = "proj-1", name: str = "Inbox") -> Project:
    return Project(id=project_id, name=name)


def _make_mock_client(projects: list[Project] | None = None, tasks=None) -> type:
    if projects is None:
        projects = [_make_project()]
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(return_value=tasks or [])
    client.get_inbox_tasks = AsyncMock(return_value=[])
    client.create_project = AsyncMock(return_value=_make_project())
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


# --- handle_list_projects ---


async def test_list_projects_no_auth() -> None:
    message = _make_message(access_token=None)
    response = await handle_list_projects(message, ticktick_client_factory=_make_mock_client())
    assert txt.AUTH_REQUIRED_NO_LINKING in response.text


async def test_list_projects_success() -> None:
    projects = [
        _make_project(project_id="p1", name="Работа"),
        _make_project(project_id="p2", name="Дом"),
        _make_project(project_id="p3", name="Покупки"),
    ]
    message = _make_message()
    response = await handle_list_projects(
        message, ticktick_client_factory=_make_mock_client(projects=projects)
    )
    assert "Работа" in response.text
    assert "Дом" in response.text
    assert "Покупки" in response.text


async def test_list_projects_empty() -> None:
    message = _make_message()
    response = await handle_list_projects(
        message, ticktick_client_factory=_make_mock_client(projects=[])
    )
    assert response.text == txt.NO_PROJECTS


async def test_list_projects_api_error() -> None:
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.get_projects = AsyncMock(
        side_effect=Exception("API error")
    )
    message = _make_message()
    response = await handle_list_projects(message, ticktick_client_factory=factory)
    assert response.text == txt.API_ERROR
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers_projects.py -v`
Expected: FAIL — `handle_list_projects` not importable

**Step 3: Implement handler**

In `alice_ticktick/dialogs/handlers.py`, add:

```python
async def handle_list_projects(
    message: Message,
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle list_projects intent."""
    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            projects = await client.get_projects()
    except Exception:
        logger.exception("Failed to list projects")
        return Response(text=txt.API_ERROR)

    if not projects:
        return Response(text=txt.NO_PROJECTS)

    lines = [f"{i + 1}. {p.name}" for i, p in enumerate(projects)]
    count = txt.pluralize_tasks(len(projects)).replace("задач", "проект")
    # Custom pluralization for projects
    n = len(projects)
    if n % 10 == 1 and n % 100 != 11:
        count_str = f"{n} проект"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        count_str = f"{n} проекта"
    else:
        count_str = f"{n} проектов"
    return Response(text=txt.PROJECTS_LIST.format(count=count_str, projects="\n".join(lines)))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers_projects.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_projects.py
git commit -m "feat: handle_list_projects — просмотр списка проектов"
```

---

### Task 6: Implement `handle_project_tasks`

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `tests/test_handlers_projects.py`

**Step 1: Write failing tests**

Add to `tests/test_handlers_projects.py`:

```python
import datetime
from alice_ticktick.dialogs.handlers import handle_project_tasks
from alice_ticktick.ticktick.models import Task


def _make_task(
    *, task_id: str = "t1", title: str = "Test", project_id: str = "p1",
    priority: int = 0, status: int = 0, due_date=None,
) -> Task:
    return Task(
        id=task_id, title=title, projectId=project_id,
        priority=priority, status=status, dueDate=due_date,
    )


def _make_intent_data(project_name: str | None = None) -> dict:
    data: dict = {"slots": {}}
    if project_name:
        data["slots"]["project_name"] = {"value": project_name}
    return data


# --- handle_project_tasks ---


async def test_project_tasks_no_auth() -> None:
    message = _make_message(access_token=None)
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=_make_mock_client(),
    )
    assert txt.AUTH_REQUIRED_NO_LINKING in response.text


async def test_project_tasks_no_name() -> None:
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data(),
        ticktick_client_factory=_make_mock_client(),
    )
    assert response.text == txt.PROJECT_TASKS_NAME_REQUIRED


async def test_project_tasks_not_found() -> None:
    projects = [_make_project(project_id="p1", name="Дом")]
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Несуществующий"),
        ticktick_client_factory=_make_mock_client(projects=projects),
    )
    assert "не найден" in response.text


async def test_project_tasks_success() -> None:
    projects = [_make_project(project_id="p1", name="Работа")]
    tasks = [
        _make_task(task_id="t1", title="Отчёт", project_id="p1"),
        _make_task(task_id="t2", title="Звонок", project_id="p1"),
    ]
    factory = _make_mock_client(projects=projects, tasks=tasks)
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=factory,
    )
    assert "Отчёт" in response.text
    assert "Звонок" in response.text
    assert "Работа" in response.text


async def test_project_tasks_empty() -> None:
    projects = [_make_project(project_id="p1", name="Работа")]
    factory = _make_mock_client(projects=projects, tasks=[])
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("Работа"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.PROJECT_NO_TASKS.format(project="Работа")


async def test_project_tasks_api_error() -> None:
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.get_projects = AsyncMock(
        side_effect=Exception("fail")
    )
    message = _make_message()
    response = await handle_project_tasks(
        message, _make_intent_data("X"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.API_ERROR
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers_projects.py -k "project_tasks" -v`
Expected: FAIL — `handle_project_tasks` not importable

**Step 3: Implement handler**

In `alice_ticktick/dialogs/handlers.py`, add:

```python
async def handle_project_tasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle project_tasks intent — show tasks from a specific project."""
    from alice_ticktick.dialogs.intents import extract_project_tasks_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_project_tasks_slots(intent_data)
    if not slots.project_name:
        return Response(text=txt.PROJECT_TASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            projects = await client.get_projects()
            project = _find_project_by_name(projects, slots.project_name)
            if project is None:
                names = ", ".join(p.name for p in projects) if projects else "—"
                return Response(
                    text=txt.PROJECT_NOT_FOUND.format(name=slots.project_name, projects=names)
                )
            tasks = await client.get_tasks(project.id)
    except Exception:
        logger.exception("Failed to get project tasks")
        return Response(text=txt.API_ERROR)

    active = [t for t in tasks if t.status == 0]
    if not active:
        return Response(text=txt.PROJECT_NO_TASKS.format(project=project.name))

    user_tz = _get_user_tz(event_update)
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

    count = txt.pluralize_tasks(len(active))
    text = txt.PROJECT_TASKS_HEADER.format(
        project=project.name, count=count, tasks="\n".join(lines)
    )
    return _truncate_response(text)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers_projects.py -k "project_tasks" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_projects.py
git commit -m "feat: handle_project_tasks — просмотр задач проекта"
```

---

### Task 7: Implement `handle_create_project`

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Modify: `tests/test_handlers_projects.py`

**Step 1: Write failing tests**

Add to `tests/test_handlers_projects.py`:

```python
from alice_ticktick.dialogs.handlers import handle_create_project


async def test_create_project_no_auth() -> None:
    message = _make_message(access_token=None)
    response = await handle_create_project(
        message, _make_intent_data("Test"),
        ticktick_client_factory=_make_mock_client(),
    )
    assert txt.AUTH_REQUIRED_NO_LINKING in response.text


async def test_create_project_no_name() -> None:
    message = _make_message()
    response = await handle_create_project(
        message, _make_intent_data(),
        ticktick_client_factory=_make_mock_client(),
    )
    assert response.text == txt.PROJECT_NAME_REQUIRED


async def test_create_project_success() -> None:
    created = _make_project(project_id="p-new", name="Travel")
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.create_project = AsyncMock(
        return_value=created
    )
    message = _make_message()
    response = await handle_create_project(
        message, _make_intent_data("Travel"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.PROJECT_CREATED.format(name="Travel")


async def test_create_project_api_error() -> None:
    factory = _make_mock_client()
    factory.return_value.__aenter__.return_value.create_project = AsyncMock(
        side_effect=Exception("fail")
    )
    message = _make_message()
    response = await handle_create_project(
        message, _make_intent_data("X"),
        ticktick_client_factory=factory,
    )
    assert response.text == txt.PROJECT_CREATE_ERROR
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_handlers_projects.py -k "create_project" -v`
Expected: FAIL — `handle_create_project` not importable

**Step 3: Implement handler**

In `alice_ticktick/dialogs/handlers.py`, add:

```python
async def handle_create_project(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
    event_update: Update | None = None,
) -> Response:
    """Handle create_project intent."""
    from alice_ticktick.dialogs.intents import extract_create_project_slots

    access_token = _get_access_token(message)
    if access_token is None:
        return _auth_required_response(event_update)

    slots = extract_create_project_slots(intent_data)
    if not slots.project_name:
        return Response(text=txt.PROJECT_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            await client.create_project(slots.project_name)
            _invalidate_task_cache()
    except Exception:
        logger.exception("Failed to create project")
        return Response(text=txt.PROJECT_CREATE_ERROR)

    return Response(text=txt.PROJECT_CREATED.format(name=slots.project_name))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handlers_projects.py -k "create_project" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_projects.py
git commit -m "feat: handle_create_project — создание проекта"
```

---

### Task 8: Wire up router

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`

**Step 1: Add imports and route handlers**

In `alice_ticktick/dialogs/router.py`:

Add imports:
```python
from alice_ticktick.dialogs.handlers import (
    # ... existing imports ...
    handle_create_project,
    handle_list_projects,
    handle_project_tasks,
)
from alice_ticktick.dialogs.intents import (
    # ... existing imports ...
    CREATE_PROJECT,
    LIST_PROJECTS,
    PROJECT_TASKS,
)
```

Add route handlers BEFORE the `list_tasks` handler (since `project_tasks` is more specific than generic list):

```python
@router.message(IntentFilter(LIST_PROJECTS))
async def on_list_projects(message: Message, event_update: Update) -> Response:
    """Handle list_projects intent."""
    return await handle_list_projects(message, event_update=event_update)


@router.message(IntentFilter(PROJECT_TASKS))
async def on_project_tasks(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle project_tasks intent."""
    return await handle_project_tasks(message, intent_data, event_update=event_update)


@router.message(IntentFilter(CREATE_PROJECT))
async def on_create_project(
    message: Message, intent_data: dict[str, Any], event_update: Update
) -> Response:
    """Handle create_project intent."""
    return await handle_create_project(message, intent_data, event_update=event_update)
```

**Step 2: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add alice_ticktick/dialogs/router.py
git commit -m "feat: роутинг интентов list_projects, project_tasks, create_project"
```

---

### Task 9: Run full verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 2: Run linter**

Run: `uv run ruff check .`
Expected: no errors

**Step 3: Run formatter**

Run: `uv run ruff format .`

**Step 4: Run type checker**

Run: `uv run mypy alice_ticktick/`
Expected: no errors

**Step 5: Final commit if formatting changed anything**

```bash
git add -u
git commit -m "style: форматирование после ruff"
```

---

### Task 10: Configure NLU intents in Yandex Dialogs (manual browser step)

Configure three new intents at Yandex Dialogs console:

**10.1. `list_projects`**

Грамматика:
```
root:
    %lemma
    (покажи|какие|что|мои|список|расскажи) (у меня)? (проекты|проект|списки|список|папки|папка)
```

Положительные тесты:
```
какие у меня проекты
покажи проекты
мои списки
список проектов
какие есть проекты
```

Отрицательные:
```
покажи задачи на сегодня
создай проект путешествие
задачи проекта работа
```

**10.2. `project_tasks`**

Грамматика:
```
root:
    %lemma
    (покажи|какие|что) (задачи|задача|дела|дело) (проекта|проект|списка|список|папки|папка|из проекта|в проекте|из списка|в списке) $ProjectName

slots:
    project_name:
        source: $ProjectName
        type: YANDEX.STRING

$ProjectName:
    .+
```

Положительные тесты:
```
покажи задачи проекта работа
какие задачи в проекте дом
что в списке покупки
покажи дела из проекта учёба
```

Отрицательные:
```
покажи задачи на сегодня
какие у меня проекты
создай проект путешествие
```

**10.3. `create_project`**

Грамматика:
```
root:
    %lemma
    (создай|добавь|новый|сделай) (проект|список|папку|папка) $ProjectName

slots:
    project_name:
        source: $ProjectName
        type: YANDEX.STRING

$ProjectName:
    .+
```

Положительные тесты:
```
создай проект путешествие
добавь список покупки
новый проект работа
сделай папку учёба
```

Отрицательные:
```
какие у меня проекты
покажи задачи проекта работа
создай задачу купить молоко
```

**After configuring each intent:** click "Протестировать" and verify Точность and Полнота are both 100%.
