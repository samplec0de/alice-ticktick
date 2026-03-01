# CD + NLU Intents + Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the skill to Yandex Cloud Functions via CI/CD, configure 3 missing NLU intents, and implement Phase 3 (subtasks + checklists).

**Architecture:** CD adds a `deploy` job to GitHub Actions that packages code + deps into a zip and uploads via `yc` CLI. NLU intents are configured in Yandex Dialogs console via browser. Phase 3 extends the TickTick client with checklist item and subtask support (V1 API has both `items[]` and `parentId`), adds new intent handlers and NLP, and follows existing patterns from Phase 2.

**Tech Stack:** GitHub Actions, yc CLI, Yandex Dialogs NLU, TickTick API v1, aliceio, pytest

---

## Part 1: Continuous Deployment

### Task 1: Create deployment packaging script

**Files:**
- Create: `scripts/package.sh`

**Step 1: Create the packaging script**

```bash
#!/usr/bin/env bash
# Package alice-ticktick for Yandex Cloud Functions deployment.
# Output: deploy.zip in project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/.build"

rm -rf "$BUILD_DIR" "$PROJECT_DIR/deploy.zip"
mkdir -p "$BUILD_DIR"

# Install production dependencies into build dir
pip install --target "$BUILD_DIR" --quiet \
    aliceio aiohttp httpx pydantic pydantic-settings rapidfuzz

# Copy application code
cp -r "$PROJECT_DIR/alice_ticktick" "$BUILD_DIR/"

# Create zip
cd "$BUILD_DIR"
zip -r "$PROJECT_DIR/deploy.zip" . -q

echo "Created deploy.zip ($(du -h "$PROJECT_DIR/deploy.zip" | cut -f1))"
```

**Step 2: Make executable and test locally**

Run: `chmod +x scripts/package.sh && bash scripts/package.sh`
Expected: `deploy.zip` created in project root

**Step 3: Add deploy.zip and .build to .gitignore**

Append to `.gitignore`:
```
deploy.zip
.build/
```

**Step 4: Commit**

```bash
git add scripts/package.sh .gitignore
git commit -m "feat: add deployment packaging script for YC Functions"
```

---

### Task 2: Add CD job to GitHub Actions

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Add deploy job after existing jobs**

Add a `deploy` job that runs only on `push` to `main` (not PRs), depends on lint+typecheck+test passing:

```yaml
  deploy:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: [lint, typecheck, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Package function
        run: bash scripts/package.sh

      - name: Install Yandex Cloud CLI
        run: |
          curl -sSL https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash -s -- -n
          echo "$HOME/yandex-cloud/bin" >> "$GITHUB_PATH"

      - name: Authenticate with YC
        run: |
          echo '${{ secrets.YC_SA_KEY_JSON }}' > sa-key.json
          yc config set service-account-key sa-key.json
          yc config set folder-id ${{ vars.YC_FOLDER_ID }}
          rm sa-key.json

      - name: Deploy to Yandex Cloud Functions
        run: |
          yc serverless function version create \
            --function-id ${{ vars.YC_FUNCTION_ID }} \
            --runtime python313 \
            --entrypoint alice_ticktick.main.handler \
            --memory 128m \
            --execution-timeout 3s \
            --source-path deploy.zip \
            --environment ALICE_SKILL_ID=${{ vars.ALICE_SKILL_ID }}
```

**Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No error

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add CD pipeline deploying to Yandex Cloud Functions on push to main"
```

---

### Task 3: Configure GitHub repository secrets and variables

This is a manual step. The user needs to configure:

**Secrets** (Settings → Secrets and variables → Actions → Secrets):
- `YC_SA_KEY_JSON` — contents of `sa-key.json` (service account key JSON)

**Variables** (Settings → Secrets and variables → Actions → Variables):
- `YC_FOLDER_ID` = `b1gkit770gfgtli2le1v`
- `YC_FUNCTION_ID` = `d4ealdoi08s3bog626lk`
- `ALICE_SKILL_ID` = `d3f073db-dece-42b8-9447-87511df30c83`

**Note:** These values are from MEMORY.md. The SA key is already in `sa-key.json` locally.

---

## Part 2: Configure 3 NLU Intents in Yandex Dialogs

### Task 4: Configure search_task intent

**URL:** https://dialogs.yandex.ru/developer/skills/d3f073db-dece-42b8-9447-87511df30c83/draft/settings/intents

**Intent ID:** `search_task`
**Name:** Поиск задачи

**Grammar:**
```
root:
    %lemma
    (найди|найти|поищи|искать|поиск|где) (задачу|задача|задание)? $Query

slots:
    query:
        source: $Query
        type: YANDEX.STRING

$Query:
    $YANDEX.STRING
```

**Positive tests:**
```
найди задачу купить молоко
поищи задачу отчёт
где задача про презентацию
найти молоко
поиск задачи позвонить маме
```

**Negative tests:**
```
создай задачу купить хлеб
покажи задачи на сегодня
удали задачу
```

Configure via browser automation (Yandex Dialogs console) or manually by the user.

---

### Task 5: Configure edit_task intent

**Intent ID:** `edit_task`
**Name:** Редактирование задачи

**Grammar:**
```
root:
    %lemma
    (перенеси|перенести|поменяй|поменять|измени|изменить|переименуй|переименовать|сдвинь|обнови) (задачу|задача|задание)? $TaskName (на $NewDate)? (в $NewName)? ((с|на|приоритет|приоритетом) (низкий|средний|высокий))?

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING
    new_date:
        source: $NewDate
        type: YANDEX.DATETIME
    new_name:
        source: $NewName
        type: YANDEX.STRING

$TaskName:
    $YANDEX.STRING

$NewDate:
    $YANDEX.DATETIME

$NewName:
    $YANDEX.STRING
```

**Positive tests:**
```
перенеси задачу купить молоко на завтра
поменяй приоритет задачи отчёт на высокий
переименуй задачу купить хлеб в купить батон
измени задачу презентация на понедельник
```

**Negative tests:**
```
создай задачу купить хлеб
удали задачу
найди задачу молоко
```

---

### Task 6: Configure delete_task intent

**Intent ID:** `delete_task`
**Name:** Удаление задачи

**Grammar:**
```
root:
    %lemma
    (удали|удалить|убери|убрать|сотри|стереть) (задачу|задача|задание)? $TaskName

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

**Positive tests:**
```
удали задачу купить молоко
убери задачу написать отчёт
удалить задачу позвонить маме
сотри задачу оплатить счёт
```

**Negative tests:**
```
создай задачу купить хлеб
покажи задачи на сегодня
найди задачу молоко
```

---

### Task 7: Publish intents and test

After configuring all 3 intents, click "Опубликовать" (Publish) to apply changes to the draft. Test each intent in the testing console to verify slot extraction works.

---

## Part 3: Phase 3 — Subtasks and Checklists

### Task 8: Extend Task model with items (checklist) and parentId

**Files:**
- Modify: `alice_ticktick/ticktick/models.py`
- Create: `tests/test_models.py`

**Step 1: Write failing tests**

```python
# tests/test_models.py
from alice_ticktick.ticktick.models import ChecklistItem, Task, TaskCreate


def test_task_with_items():
    data = {
        "id": "t1",
        "projectId": "p1",
        "title": "Shopping",
        "items": [
            {"id": "i1", "title": "Milk", "status": 0, "sortOrder": 0},
            {"id": "i2", "title": "Bread", "status": 1, "sortOrder": 1},
        ],
    }
    task = Task.model_validate(data)
    assert len(task.items) == 2
    assert task.items[0].title == "Milk"
    assert task.items[0].status == 0
    assert task.items[1].status == 1


def test_task_with_parent_id():
    data = {
        "id": "t2",
        "projectId": "p1",
        "title": "Sub task",
        "parentId": "t1",
    }
    task = Task.model_validate(data)
    assert task.parent_id == "t1"


def test_task_without_items():
    data = {"id": "t1", "projectId": "p1", "title": "Simple task"}
    task = Task.model_validate(data)
    assert task.items == []
    assert task.parent_id is None


def test_checklist_item_model():
    item = ChecklistItem(id="i1", title="Buy eggs", status=0, sort_order=0)
    assert item.title == "Buy eggs"
    assert item.status == 0


def test_task_create_with_items():
    payload = TaskCreate(
        title="Shopping",
        items=[
            {"title": "Milk", "status": 0},
            {"title": "Bread", "status": 0},
        ],
    )
    dumped = payload.model_dump(by_alias=True, exclude_none=True)
    assert len(dumped["items"]) == 2


def test_task_create_with_parent_id():
    payload = TaskCreate(title="Subtask", projectId="p1", parentId="t1")
    dumped = payload.model_dump(by_alias=True, exclude_none=True)
    assert dumped["parentId"] == "t1"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ChecklistItem` not defined, `items` not a field on Task

**Step 3: Implement model changes**

Add to `alice_ticktick/ticktick/models.py`:

```python
class ChecklistItem(BaseModel):
    """A single checklist item within a task."""

    id: str = ""
    title: str
    status: int = 0  # 0 = incomplete, 1 = completed
    sort_order: int = Field(default=0, alias="sortOrder")

    model_config = {"populate_by_name": True}
```

Extend `Task`:
```python
class Task(BaseModel):
    # ... existing fields ...
    items: list[ChecklistItem] = Field(default_factory=list)
    parent_id: str | None = Field(default=None, alias="parentId")
```

Extend `TaskCreate`:
```python
class TaskCreate(BaseModel):
    # ... existing fields ...
    items: list[dict[str, Any]] | None = None
    parent_id: str | None = Field(default=None, alias="parentId")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add alice_ticktick/ticktick/models.py tests/test_models.py
git commit -m "feat: extend Task model with checklist items and parentId"
```

---

### Task 9: Add checklist and subtask methods to TickTickClient

**Files:**
- Modify: `alice_ticktick/ticktick/client.py`
- Modify: `tests/test_ticktick_client.py`

**Step 1: Write failing tests**

Add tests to `tests/test_ticktick_client.py`:

```python
async def test_create_subtask(mock_client):
    """Test creating a subtask (task with parentId)."""
    payload = TaskCreate(title="Subtask", projectId="p1", parentId="parent1")
    mock_client._client.post = AsyncMock(return_value=httpx.Response(
        200, json={"id": "s1", "projectId": "p1", "title": "Subtask", "parentId": "parent1"},
    ))
    result = await mock_client.create_task(payload)
    assert result.parent_id == "parent1"


async def test_get_task_with_items(mock_client):
    """Test getting a task that has checklist items."""
    mock_client._client.get = AsyncMock(return_value=httpx.Response(
        200,
        json={
            "id": "t1", "projectId": "p1", "title": "Shopping",
            "items": [
                {"id": "i1", "title": "Milk", "status": 0, "sortOrder": 0},
            ],
        },
    ))
    task = await mock_client.get_task("t1", "p1")
    assert len(task.items) == 1
    assert task.items[0].title == "Milk"


async def test_update_task_items(mock_client):
    """Test updating a task's checklist items."""
    mock_client._client.post = AsyncMock(return_value=httpx.Response(
        200,
        json={
            "id": "t1", "projectId": "p1", "title": "Shopping",
            "items": [
                {"id": "i1", "title": "Milk", "status": 0, "sortOrder": 0},
                {"id": "i2", "title": "Bread", "status": 0, "sortOrder": 1},
            ],
        },
    ))
    payload = TaskUpdate(id="t1", projectId="p1")
    result = await mock_client.update_task(payload)
    assert len(result.items) == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ticktick_client.py -v -k "subtask or items"`
Expected: FAIL (initially, until model changes from Task 8 are in place; if Task 8 is done, they should pass since create_task already works)

**Step 3: Verify tests pass (after Task 8)**

Run: `uv run pytest tests/test_ticktick_client.py -v`
Expected: All PASS — no client method changes needed; existing `create_task` and `update_task` already handle arbitrary payloads via model serialization

**Step 4: Commit**

```bash
git add tests/test_ticktick_client.py
git commit -m "test: add tests for subtask and checklist item support in client"
```

---

### Task 10: Add TaskUpdate.items support for checklist modifications

**Files:**
- Modify: `alice_ticktick/ticktick/models.py`
- Modify: `tests/test_models.py`

**Step 1: Write failing test**

```python
def test_task_update_with_items():
    payload = TaskUpdate(
        id="t1",
        projectId="p1",
        items=[
            {"id": "i1", "title": "Milk", "status": 1, "sortOrder": 0},
            {"title": "Eggs", "status": 0, "sortOrder": 1},
        ],
    )
    dumped = payload.model_dump(by_alias=True, exclude_none=True)
    assert "items" in dumped
    assert len(dumped["items"]) == 2
```

**Step 2: Run test — verify fail**

Run: `uv run pytest tests/test_models.py::test_task_update_with_items -v`

**Step 3: Add items field to TaskUpdate**

```python
class TaskUpdate(BaseModel):
    # ... existing fields ...
    items: list[dict[str, Any]] | None = None
```

**Step 4: Run test — verify pass**

Run: `uv run pytest tests/test_models.py -v`

**Step 5: Commit**

```bash
git add alice_ticktick/ticktick/models.py tests/test_models.py
git commit -m "feat: add items support to TaskUpdate for checklist modifications"
```

---

### Task 11: Define Phase 3 intents and slot extraction

**Files:**
- Modify: `alice_ticktick/dialogs/intents.py`
- Modify: `tests/test_intents.py`

**Step 1: Write failing tests**

```python
# In tests/test_intents.py — add tests for new intents

def test_extract_add_subtask_slots():
    intent_data = {
        "slots": {
            "subtask_name": {"type": "YANDEX.STRING", "value": "Write intro"},
            "parent_name": {"type": "YANDEX.STRING", "value": "Report"},
        }
    }
    slots = extract_add_subtask_slots(intent_data)
    assert slots.subtask_name == "Write intro"
    assert slots.parent_name == "Report"


def test_extract_list_subtasks_slots():
    intent_data = {
        "slots": {
            "task_name": {"type": "YANDEX.STRING", "value": "Report"},
        }
    }
    slots = extract_list_subtasks_slots(intent_data)
    assert slots.task_name == "Report"


def test_extract_add_checklist_item_slots():
    intent_data = {
        "slots": {
            "item_name": {"type": "YANDEX.STRING", "value": "Milk"},
            "task_name": {"type": "YANDEX.STRING", "value": "Shopping"},
        }
    }
    slots = extract_add_checklist_item_slots(intent_data)
    assert slots.item_name == "Milk"
    assert slots.task_name == "Shopping"


def test_extract_show_checklist_slots():
    intent_data = {
        "slots": {
            "task_name": {"type": "YANDEX.STRING", "value": "Shopping"},
        }
    }
    slots = extract_show_checklist_slots(intent_data)
    assert slots.task_name == "Shopping"


def test_extract_check_item_slots():
    intent_data = {
        "slots": {
            "item_name": {"type": "YANDEX.STRING", "value": "Milk"},
            "task_name": {"type": "YANDEX.STRING", "value": "Shopping"},
        }
    }
    slots = extract_check_item_slots(intent_data)
    assert slots.item_name == "Milk"
    assert slots.task_name == "Shopping"


def test_extract_delete_checklist_item_slots():
    intent_data = {
        "slots": {
            "item_name": {"type": "YANDEX.STRING", "value": "Milk"},
            "task_name": {"type": "YANDEX.STRING", "value": "Shopping"},
        }
    }
    slots = extract_delete_checklist_item_slots(intent_data)
    assert slots.item_name == "Milk"
    assert slots.task_name == "Shopping"
```

**Step 2: Run tests — verify fail**

Run: `uv run pytest tests/test_intents.py -v -k "subtask or checklist"`

**Step 3: Implement intent definitions**

Add to `alice_ticktick/dialogs/intents.py`:

```python
# New intent IDs
ADD_SUBTASK = "add_subtask"
LIST_SUBTASKS = "list_subtasks"
ADD_CHECKLIST_ITEM = "add_checklist_item"
SHOW_CHECKLIST = "show_checklist"
CHECK_ITEM = "check_item"
DELETE_CHECKLIST_ITEM = "delete_checklist_item"


@dataclass(frozen=True, slots=True)
class AddSubtaskSlots:
    subtask_name: str | None = None
    parent_name: str | None = None


@dataclass(frozen=True, slots=True)
class ListSubtasksSlots:
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class AddChecklistItemSlots:
    item_name: str | None = None
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class ShowChecklistSlots:
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class CheckItemSlots:
    item_name: str | None = None
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteChecklistItemSlots:
    item_name: str | None = None
    task_name: str | None = None


def extract_add_subtask_slots(intent_data: dict[str, Any]) -> AddSubtaskSlots:
    return AddSubtaskSlots(
        subtask_name=_get_slot_value(intent_data, "subtask_name"),
        parent_name=_get_slot_value(intent_data, "parent_name"),
    )


def extract_list_subtasks_slots(intent_data: dict[str, Any]) -> ListSubtasksSlots:
    return ListSubtasksSlots(task_name=_get_slot_value(intent_data, "task_name"))


def extract_add_checklist_item_slots(intent_data: dict[str, Any]) -> AddChecklistItemSlots:
    return AddChecklistItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_show_checklist_slots(intent_data: dict[str, Any]) -> ShowChecklistSlots:
    return ShowChecklistSlots(task_name=_get_slot_value(intent_data, "task_name"))


def extract_check_item_slots(intent_data: dict[str, Any]) -> CheckItemSlots:
    return CheckItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )


def extract_delete_checklist_item_slots(intent_data: dict[str, Any]) -> DeleteChecklistItemSlots:
    return DeleteChecklistItemSlots(
        item_name=_get_slot_value(intent_data, "item_name"),
        task_name=_get_slot_value(intent_data, "task_name"),
    )
```

Update `ALL_INTENTS` to include new intent IDs.

**Step 4: Run tests — verify pass**

Run: `uv run pytest tests/test_intents.py -v`

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/intents.py tests/test_intents.py
git commit -m "feat: add Phase 3 intent definitions for subtasks and checklists"
```

---

### Task 12: Add Phase 3 response strings

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py`

**Step 1: Add response strings**

```python
# Subtasks
SUBTASK_PARENT_REQUIRED = "Назовите задачу, к которой нужно добавить подзадачу."
SUBTASK_NAME_REQUIRED = "Как назвать подзадачу?"
SUBTASK_CREATED = "Подзадача «{name}» добавлена к задаче «{parent}»."
SUBTASK_ERROR = "Не удалось создать подзадачу. Попробуйте ещё раз."
NO_SUBTASKS = "У задачи «{name}» нет подзадач."
SUBTASKS_HEADER = "Подзадачи «{name}» ({count}):\n{tasks}"
LIST_SUBTASKS_NAME_REQUIRED = "Назовите задачу, подзадачи которой показать."

# Checklists
CHECKLIST_TASK_REQUIRED = "Назовите задачу для чеклиста."
CHECKLIST_ITEM_REQUIRED = "Что добавить в чеклист?"
CHECKLIST_ITEM_ADDED = "Добавила «{item}» в чеклист задачи «{task}». Всего пунктов: {count}."
CHECKLIST_ITEM_ERROR = "Не удалось добавить пункт в чеклист."
CHECKLIST_EMPTY = "Чеклист задачи «{name}» пуст."
CHECKLIST_HEADER = "Чеклист задачи «{name}»:\n{items}"
CHECKLIST_ITEM_CHECKED = "Пункт «{item}» отмечен выполненным."
CHECKLIST_ITEM_NOT_FOUND = "Пункт «{item}» не найден в чеклисте задачи «{task}»."
CHECKLIST_ITEM_DELETED = "Пункт «{item}» удалён из чеклиста задачи «{task}»."
CHECKLIST_ITEM_DELETE_ERROR = "Не удалось удалить пункт из чеклиста."
CHECKLIST_CHECK_ERROR = "Не удалось отметить пункт."
SHOW_CHECKLIST_NAME_REQUIRED = "Назовите задачу, чеклист которой показать."
```

**Step 2: Commit**

```bash
git add alice_ticktick/dialogs/responses.py
git commit -m "feat: add Phase 3 response strings for subtasks and checklists"
```

---

### Task 13: Implement subtask handlers

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Create: `tests/test_handlers_subtasks.py`

**Step 1: Write failing tests**

```python
# tests/test_handlers_subtasks.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs.handlers import handle_add_subtask, handle_list_subtasks
from alice_ticktick.dialogs import responses as txt
from alice_ticktick.ticktick.models import Task, Project, TaskCreate


def _make_message(access_token="test-token"):
    msg = MagicMock()
    msg.user = MagicMock()
    msg.user.access_token = access_token
    return msg


def _make_client_factory(projects, tasks_by_project, created_task=None):
    """Create a mock TickTickClient factory."""
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(side_effect=lambda pid: tasks_by_project.get(pid, []))
    if created_task:
        client.create_task = AsyncMock(return_value=created_task)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=client)
    return factory


@pytest.fixture
def projects():
    return [Project(id="p1", name="Inbox")]


@pytest.fixture
def parent_task():
    return Task(id="t1", projectId="p1", title="Prepare report", status=0)


@pytest.fixture
def subtask():
    return Task(id="t2", projectId="p1", title="Write intro", status=0, parentId="t1")


async def test_add_subtask_success(projects, parent_task, subtask):
    factory = _make_client_factory(
        projects, {"p1": [parent_task]}, created_task=subtask,
    )
    msg = _make_message()
    intent_data = {
        "slots": {
            "subtask_name": {"value": "Write intro"},
            "parent_name": {"value": "Prepare report"},
        }
    }
    resp = await handle_add_subtask(msg, intent_data, factory)
    assert "Write intro" in resp.text
    assert "Prepare report" in resp.text


async def test_add_subtask_parent_not_found(projects, parent_task):
    factory = _make_client_factory(projects, {"p1": [parent_task]})
    msg = _make_message()
    intent_data = {
        "slots": {
            "subtask_name": {"value": "Write intro"},
            "parent_name": {"value": "Nonexistent task"},
        }
    }
    resp = await handle_add_subtask(msg, intent_data, factory)
    assert resp.text == txt.TASK_NOT_FOUND.format(name="Nonexistent task")


async def test_add_subtask_no_auth():
    msg = _make_message(access_token=None)
    msg.user.access_token = None
    resp = await handle_add_subtask(msg, {"slots": {}})
    assert resp.text == txt.AUTH_REQUIRED


async def test_list_subtasks_success(projects, parent_task, subtask):
    factory = _make_client_factory(projects, {"p1": [parent_task, subtask]})
    msg = _make_message()
    intent_data = {"slots": {"task_name": {"value": "Prepare report"}}}
    resp = await handle_list_subtasks(msg, intent_data, factory)
    assert "Write intro" in resp.text


async def test_list_subtasks_empty(projects, parent_task):
    factory = _make_client_factory(projects, {"p1": [parent_task]})
    msg = _make_message()
    intent_data = {"slots": {"task_name": {"value": "Prepare report"}}}
    resp = await handle_list_subtasks(msg, intent_data, factory)
    assert resp.text == txt.NO_SUBTASKS.format(name="Prepare report")
```

**Step 2: Run tests — verify fail**

Run: `uv run pytest tests/test_handlers_subtasks.py -v`

**Step 3: Implement handlers**

Add to `alice_ticktick/dialogs/handlers.py`:

```python
async def handle_add_subtask(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_add_subtask_slots(intent_data)
    if not slots.subtask_name:
        return Response(text=txt.SUBTASK_NAME_REQUIRED)
    if not slots.parent_name:
        return Response(text=txt.SUBTASK_PARENT_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
            active = [t for t in all_tasks if t.status == 0]
            titles = [t.title for t in active]
            match = find_best_match(slots.parent_name, titles)
            if match is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.parent_name))

            parent_title, parent_idx = match
            parent = active[parent_idx]

            payload = TaskCreate(
                title=slots.subtask_name,
                projectId=parent.project_id,
                parentId=parent.id,
            )
            await client.create_task(payload)
    except Exception:
        logger.exception("Failed to create subtask")
        return Response(text=txt.SUBTASK_ERROR)

    return Response(
        text=txt.SUBTASK_CREATED.format(name=slots.subtask_name, parent=parent_title)
    )


async def handle_list_subtasks(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_list_subtasks_slots(intent_data)
    if not slots.task_name:
        return Response(text=txt.LIST_SUBTASKS_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to list subtasks")
        return Response(text=txt.API_ERROR)

    active = [t for t in all_tasks if t.status == 0]
    titles = [t.title for t in active]
    match = find_best_match(slots.task_name, titles)
    if match is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    parent_title, parent_idx = match
    parent = active[parent_idx]
    subtasks = [t for t in all_tasks if t.parent_id == parent.id and t.status == 0]

    if not subtasks:
        return Response(text=txt.NO_SUBTASKS.format(name=parent_title))

    count_str = txt.pluralize_tasks(len(subtasks))
    lines = [_format_task_line(i + 1, t) for i, t in enumerate(subtasks[:5])]
    return Response(
        text=_truncate_response(
            txt.SUBTASKS_HEADER.format(name=parent_title, count=count_str, tasks="\n".join(lines))
        )
    )
```

**Step 4: Run tests — verify pass**

Run: `uv run pytest tests/test_handlers_subtasks.py -v`

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_subtasks.py
git commit -m "feat: implement subtask handlers (add + list)"
```

---

### Task 14: Implement checklist handlers

**Files:**
- Modify: `alice_ticktick/dialogs/handlers.py`
- Create: `tests/test_handlers_checklist.py`

**Step 1: Write failing tests**

```python
# tests/test_handlers_checklist.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from alice_ticktick.dialogs.handlers import (
    handle_add_checklist_item,
    handle_show_checklist,
    handle_check_item,
    handle_delete_checklist_item,
)
from alice_ticktick.dialogs import responses as txt
from alice_ticktick.ticktick.models import ChecklistItem, Task, Project


def _make_message(access_token="test-token"):
    msg = MagicMock()
    msg.user = MagicMock()
    msg.user.access_token = access_token
    return msg


def _make_client_factory(projects, tasks_by_project, updated_task=None):
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=projects)
    client.get_tasks = AsyncMock(side_effect=lambda pid: tasks_by_project.get(pid, []))
    if updated_task:
        client.update_task = AsyncMock(return_value=updated_task)
    else:
        client.update_task = AsyncMock(return_value=None)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=client)


@pytest.fixture
def projects():
    return [Project(id="p1", name="Inbox")]


@pytest.fixture
def task_with_items():
    return Task(
        id="t1", projectId="p1", title="Shopping", status=0,
        items=[
            ChecklistItem(id="i1", title="Bread", status=1, sortOrder=0),
            ChecklistItem(id="i2", title="Eggs", status=0, sortOrder=1),
        ],
    )


@pytest.fixture
def task_no_items():
    return Task(id="t2", projectId="p1", title="Clean house", status=0)


async def test_add_checklist_item_success(projects, task_no_items):
    updated = Task(
        id="t2", projectId="p1", title="Clean house", status=0,
        items=[ChecklistItem(id="i1", title="Kitchen", status=0, sortOrder=0)],
    )
    factory = _make_client_factory(projects, {"p1": [task_no_items]}, updated)
    msg = _make_message()
    intent_data = {
        "slots": {
            "item_name": {"value": "Kitchen"},
            "task_name": {"value": "Clean house"},
        }
    }
    resp = await handle_add_checklist_item(msg, intent_data, factory)
    assert "Kitchen" in resp.text
    assert "Clean house" in resp.text


async def test_show_checklist_with_items(projects, task_with_items):
    factory = _make_client_factory(projects, {"p1": [task_with_items]})
    msg = _make_message()
    intent_data = {"slots": {"task_name": {"value": "Shopping"}}}
    resp = await handle_show_checklist(msg, intent_data, factory)
    assert "Bread" in resp.text
    assert "Eggs" in resp.text


async def test_show_checklist_empty(projects, task_no_items):
    factory = _make_client_factory(projects, {"p1": [task_no_items]})
    msg = _make_message()
    intent_data = {"slots": {"task_name": {"value": "Clean house"}}}
    resp = await handle_show_checklist(msg, intent_data, factory)
    assert resp.text == txt.CHECKLIST_EMPTY.format(name="Clean house")


async def test_check_item_success(projects, task_with_items):
    factory = _make_client_factory(projects, {"p1": [task_with_items]}, task_with_items)
    msg = _make_message()
    intent_data = {
        "slots": {
            "item_name": {"value": "Eggs"},
            "task_name": {"value": "Shopping"},
        }
    }
    resp = await handle_check_item(msg, intent_data, factory)
    assert "Eggs" in resp.text


async def test_check_item_not_found(projects, task_with_items):
    factory = _make_client_factory(projects, {"p1": [task_with_items]})
    msg = _make_message()
    intent_data = {
        "slots": {
            "item_name": {"value": "Butter"},
            "task_name": {"value": "Shopping"},
        }
    }
    resp = await handle_check_item(msg, intent_data, factory)
    assert resp.text == txt.CHECKLIST_ITEM_NOT_FOUND.format(item="Butter", task="Shopping")


async def test_delete_checklist_item_success(projects, task_with_items):
    factory = _make_client_factory(projects, {"p1": [task_with_items]}, task_with_items)
    msg = _make_message()
    intent_data = {
        "slots": {
            "item_name": {"value": "Eggs"},
            "task_name": {"value": "Shopping"},
        }
    }
    resp = await handle_delete_checklist_item(msg, intent_data, factory)
    assert "Eggs" in resp.text
```

**Step 2: Run tests — verify fail**

Run: `uv run pytest tests/test_handlers_checklist.py -v`

**Step 3: Implement checklist handlers**

Add to `alice_ticktick/dialogs/handlers.py`:

```python
async def handle_add_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_add_checklist_item_slots(intent_data)
    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)
    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
            active = [t for t in all_tasks if t.status == 0]
            titles = [t.title for t in active]
            match = find_best_match(slots.task_name, titles)
            if match is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            task_title, task_idx = match
            task = active[task_idx]

            # Build new items list
            existing_items = [
                {"id": item.id, "title": item.title, "status": item.status, "sortOrder": item.sort_order}
                for item in task.items
            ]
            new_sort = max((i.sort_order for i in task.items), default=-1) + 1
            existing_items.append({"title": slots.item_name, "status": 0, "sortOrder": new_sort})

            payload = TaskUpdate(id=task.id, projectId=task.project_id, items=existing_items)
            result = await client.update_task(payload)
    except Exception:
        logger.exception("Failed to add checklist item")
        return Response(text=txt.CHECKLIST_ITEM_ERROR)

    item_count = len(result.items) if result else len(existing_items)
    return Response(
        text=txt.CHECKLIST_ITEM_ADDED.format(item=slots.item_name, task=task_title, count=item_count)
    )


async def handle_show_checklist(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_show_checklist_slots(intent_data)
    if not slots.task_name:
        return Response(text=txt.SHOW_CHECKLIST_NAME_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
    except Exception:
        logger.exception("Failed to show checklist")
        return Response(text=txt.API_ERROR)

    active = [t for t in all_tasks if t.status == 0]
    titles = [t.title for t in active]
    match = find_best_match(slots.task_name, titles)
    if match is None:
        return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

    task_title, task_idx = match
    task = active[task_idx]

    if not task.items:
        return Response(text=txt.CHECKLIST_EMPTY.format(name=task_title))

    done = [item.title for item in task.items if item.status == 1]
    not_done = [item.title for item in task.items if item.status == 0]

    parts = []
    if done:
        parts.append(f"Выполнено — {', '.join(done)}.")
    if not_done:
        parts.append(f"Не выполнено — {', '.join(not_done)}.")

    return Response(
        text=_truncate_response(
            txt.CHECKLIST_HEADER.format(name=task_title, items="\n".join(parts))
        )
    )


async def handle_check_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_check_item_slots(intent_data)
    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)
    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
            active = [t for t in all_tasks if t.status == 0]
            titles = [t.title for t in active]
            match = find_best_match(slots.task_name, titles)
            if match is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            task_title, task_idx = match
            task = active[task_idx]

            # Find item by fuzzy match
            item_match = find_best_match(
                slots.item_name, [item.title for item in task.items]
            )
            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=task_title)
                )

            item_title, item_idx = item_match

            # Update items: set matched item status to 1
            updated_items = [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": 1 if i == item_idx else item.status,
                    "sortOrder": item.sort_order,
                }
                for i, item in enumerate(task.items)
            ]
            payload = TaskUpdate(id=task.id, projectId=task.project_id, items=updated_items)
            await client.update_task(payload)
    except Exception:
        logger.exception("Failed to check item")
        return Response(text=txt.CHECKLIST_CHECK_ERROR)

    return Response(text=txt.CHECKLIST_ITEM_CHECKED.format(item=item_title))


async def handle_delete_checklist_item(
    message: Message,
    intent_data: dict[str, Any],
    ticktick_client_factory: type[TickTickClient] | None = None,
) -> Response:
    access_token = _get_access_token(message)
    if access_token is None:
        return Response(text=txt.AUTH_REQUIRED)

    slots = extract_delete_checklist_item_slots(intent_data)
    if not slots.task_name:
        return Response(text=txt.CHECKLIST_TASK_REQUIRED)
    if not slots.item_name:
        return Response(text=txt.CHECKLIST_ITEM_REQUIRED)

    factory = ticktick_client_factory or TickTickClient
    try:
        async with factory(access_token) as client:
            all_tasks = await _gather_all_tasks(client)
            active = [t for t in all_tasks if t.status == 0]
            titles = [t.title for t in active]
            match = find_best_match(slots.task_name, titles)
            if match is None:
                return Response(text=txt.TASK_NOT_FOUND.format(name=slots.task_name))

            task_title, task_idx = match
            task = active[task_idx]

            item_match = find_best_match(
                slots.item_name, [item.title for item in task.items]
            )
            if item_match is None:
                return Response(
                    text=txt.CHECKLIST_ITEM_NOT_FOUND.format(item=slots.item_name, task=task_title)
                )

            item_title, item_idx = item_match

            # Remove the matched item from the list
            updated_items = [
                {"id": item.id, "title": item.title, "status": item.status, "sortOrder": item.sort_order}
                for i, item in enumerate(task.items)
                if i != item_idx
            ]
            payload = TaskUpdate(id=task.id, projectId=task.project_id, items=updated_items)
            await client.update_task(payload)
    except Exception:
        logger.exception("Failed to delete checklist item")
        return Response(text=txt.CHECKLIST_ITEM_DELETE_ERROR)

    return Response(
        text=txt.CHECKLIST_ITEM_DELETED.format(item=item_title, task=task_title)
    )
```

**Step 4: Run tests — verify pass**

Run: `uv run pytest tests/test_handlers_checklist.py -v`

**Step 5: Commit**

```bash
git add alice_ticktick/dialogs/handlers.py tests/test_handlers_checklist.py
git commit -m "feat: implement checklist handlers (add, show, check, delete)"
```

---

### Task 15: Wire Phase 3 handlers into the router

**Files:**
- Modify: `alice_ticktick/dialogs/router.py`
- Modify: `tests/test_router.py` (if exists, or include in handlers tests)

**Step 1: Add routes for new intents**

In `alice_ticktick/dialogs/router.py`, add new intent routes following the same pattern as existing ones:

```python
from alice_ticktick.dialogs.intents import (
    ADD_SUBTASK, LIST_SUBTASKS,
    ADD_CHECKLIST_ITEM, SHOW_CHECKLIST, CHECK_ITEM, DELETE_CHECKLIST_ITEM,
)
from alice_ticktick.dialogs.handlers import (
    handle_add_subtask, handle_list_subtasks,
    handle_add_checklist_item, handle_show_checklist,
    handle_check_item, handle_delete_checklist_item,
)

# Add routes:
@router.message(IntentFilter(ADD_SUBTASK))
async def on_add_subtask(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_add_subtask(message, intent_data)

@router.message(IntentFilter(LIST_SUBTASKS))
async def on_list_subtasks(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_list_subtasks(message, intent_data)

@router.message(IntentFilter(ADD_CHECKLIST_ITEM))
async def on_add_checklist_item(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_add_checklist_item(message, intent_data)

@router.message(IntentFilter(SHOW_CHECKLIST))
async def on_show_checklist(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_show_checklist(message, intent_data)

@router.message(IntentFilter(CHECK_ITEM))
async def on_check_item(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_check_item(message, intent_data)

@router.message(IntentFilter(DELETE_CHECKLIST_ITEM))
async def on_delete_checklist_item(message: Message, intent_data: dict[str, Any]) -> Response:
    return await handle_delete_checklist_item(message, intent_data)
```

**Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 3: Run linting, formatting, type checking**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy alice_ticktick/`
Expected: All clean

**Step 4: Commit**

```bash
git add alice_ticktick/dialogs/router.py
git commit -m "feat: wire Phase 3 handlers into router"
```

---

### Task 16: Configure Phase 3 NLU intents in Yandex Dialogs

These 6 intents need to be configured in the Yandex Dialogs console.

**URL:** https://dialogs.yandex.ru/developer/skills/d3f073db-dece-42b8-9447-87511df30c83/draft/settings/intents

#### add_subtask
```
root:
    %lemma
    (добавь|добавить|создай|создать) подзадачу $SubtaskName (к|в|для) (задаче|задачу|задача)? $ParentName

slots:
    subtask_name:
        source: $SubtaskName
        type: YANDEX.STRING
    parent_name:
        source: $ParentName
        type: YANDEX.STRING

$SubtaskName:
    $YANDEX.STRING

$ParentName:
    $YANDEX.STRING
```

#### list_subtasks
```
root:
    %lemma
    (покажи|какие|что) (подзадачи|подзадача) (задачи|задача|у)? $TaskName

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

#### add_checklist_item
```
root:
    %lemma
    (добавь|добавить) (пункт|элемент|запись) $ItemName (в|к) (чеклист|чеклисту|список) (задачи|задача|задачу)? $TaskName

slots:
    item_name:
        source: $ItemName
        type: YANDEX.STRING
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$ItemName:
    $YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

#### show_checklist
```
root:
    %lemma
    (покажи|какой|что) (чеклист|список) (задачи|задача|задачу)? $TaskName

slots:
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

#### check_item
```
root:
    %lemma
    (отметь|отметить|выполни|выполнить|готово) (пункт|элемент) $ItemName (в|из) (чеклисте|чеклист|списке|список) (задачи|задача|задачу)? $TaskName

slots:
    item_name:
        source: $ItemName
        type: YANDEX.STRING
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$ItemName:
    $YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

#### delete_checklist_item
```
root:
    %lemma
    (удали|удалить|убери|убрать) (пункт|элемент) $ItemName (из|в) (чеклиста|чеклист|списка|список) (задачи|задача|задачу)? $TaskName

slots:
    item_name:
        source: $ItemName
        type: YANDEX.STRING
    task_name:
        source: $TaskName
        type: YANDEX.STRING

$ItemName:
    $YANDEX.STRING

$TaskName:
    $YANDEX.STRING
```

After configuring, publish the draft.

---

### Task 17: Update HELP text and docs

**Files:**
- Modify: `alice_ticktick/dialogs/responses.py` — update HELP string to mention subtasks and checklists
- Modify: `docs/SETUP.md` — update progress table

**Step 1: Update HELP text**

Add to HELP string:
```
— «Добавь подзадачу [название] к задаче [задача]» — создать подзадачу
— «Покажи подзадачи задачи [название]» — список подзадач
— «Добавь пункт [текст] в чеклист задачи [название]» — добавить в чеклист
— «Покажи чеклист задачи [название]» — показать чеклист
— «Отметь пункт [текст] в чеклисте задачи [название]» — выполнить пункт
— «Удали пункт [текст] из чеклиста задачи [название]» — удалить пункт
```

**Step 2: Update SETUP.md progress table**

Mark Phase 2 intents and Phase 3 with their status.

**Step 3: Commit**

```bash
git add alice_ticktick/dialogs/responses.py docs/SETUP.md
git commit -m "docs: update help text and progress for Phase 3"
```

---

### Task 18: Final verification

**Step 1: Run all checks**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy alice_ticktick/
uv run pytest -v --cov=alice_ticktick
```

Expected: All pass, no regressions

**Step 2: Verify test count increased**

Expected: Test count > 158 (Phase 2 had 158)
