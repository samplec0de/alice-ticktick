# TickTick API Direct Cleanup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace slow voice-based e2e test cleanup (50 tasks max, ~5s each) with direct TickTick API cleanup that deletes all "кктест" tasks in seconds.

**Architecture:** New module `tests/e2e/ticktick_auth.py` handles OAuth flow (local HTTP server + browser) and token persistence. Conftest gains a `ticktick_client` fixture that auto-refreshes tokens. Cleanup uses `TickTickClient` directly to scan inbox + all projects and delete matching tasks. Falls back to old voice-based cleanup if no token available.

**Tech Stack:** httpx (existing), `http.server` from stdlib for OAuth callback, `webbrowser` for opening auth URL, TickTickClient (existing).

---

### Task 1: OAuth token acquisition module

**Files:**
- Create: `tests/e2e/ticktick_auth.py`
- Modify: `.env.example` (add test credentials)
- Modify: `.gitignore` (add `.ticktick_auth/`)

**Step 1: Add env vars to `.env.example`**

Add to `.env.example` after the existing TickTick section:

```
# TickTick OAuth for E2E tests (separate app, redirect_uri=http://localhost:8080/callback)
TICKTICK_TEST_CLIENT_ID=
TICKTICK_TEST_CLIENT_SECRET=
```

**Step 2: Add `.ticktick_auth/` to `.gitignore`**

Add after the `.yandex_auth/` line:

```
# TickTick auth for E2E tests
.ticktick_auth/
```

**Step 3: Create `tests/e2e/ticktick_auth.py`**

This module provides:
- `get_access_token(client_id, client_secret) -> str` — main entry point
  - Loads saved tokens from `~/.ticktick_auth/tokens.json`
  - If token exists and refresh_token available → try refresh
  - If no token → run interactive OAuth flow
- `_run_oauth_flow(client_id, client_secret) -> dict` — starts local server on port 8080, opens browser, catches callback, exchanges code for tokens
- `_refresh_token(client_id, client_secret, refresh_token) -> dict` — POST to token endpoint with `grant_type=refresh_token`
- `_save_tokens(tokens: dict) -> None` / `_load_tokens() -> dict | None`

Key details:
- Token URL: `https://ticktick.com/oauth/token`
- Auth URL: `https://ticktick.com/oauth/authorize`
- Scope: `tasks:read tasks:write`
- Redirect URI: `http://localhost:8080/callback`
- Token exchange uses HTTP Basic Auth (client_id:client_secret) per TickTick docs
- Local server uses `http.server.HTTPServer` + `threading.Thread` (daemon) for clean shutdown
- Server waits up to 120 seconds for callback, then raises timeout error

```python
"""TickTick OAuth helper for E2E test cleanup.

Handles the full OAuth2 flow:
1. Start local HTTP server on localhost:8080
2. Open browser → TickTick authorize page
3. Catch redirect with auth code
4. Exchange code for access_token + refresh_token
5. Persist tokens to ~/.ticktick_auth/tokens.json
6. Auto-refresh on subsequent runs
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

TOKEN_URL = "https://ticktick.com/oauth/token"
AUTH_URL = "https://ticktick.com/oauth/authorize"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "tasks:read tasks:write"
TOKEN_DIR = Path.home() / ".ticktick_auth"
TOKEN_FILE = TOKEN_DIR / "tokens.json"
_OAUTH_TIMEOUT = 120  # seconds to wait for browser callback


def get_access_token(client_id: str, client_secret: str) -> str:
    """Get a valid access token, refreshing or re-authorizing as needed."""
    tokens = _load_tokens()

    # Try refresh first
    if tokens and tokens.get("refresh_token"):
        try:
            new_tokens = _refresh_token(client_id, client_secret, tokens["refresh_token"])
            _save_tokens(new_tokens)
            return new_tokens["access_token"]
        except Exception:
            pass  # Refresh failed, fall through to full flow

    # Full OAuth flow
    tokens = _run_oauth_flow(client_id, client_secret)
    _save_tokens(tokens)
    return tokens["access_token"]


def _run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Run interactive OAuth flow: local server + browser."""
    auth_code: str | None = None
    error: str | None = None
    received = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal auth_code, error
            params = parse_qs(urlparse(self.path).query)
            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write("Авторизация прошла успешно! Можно закрыть вкладку.".encode())
            else:
                error = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Ошибка: {error}".encode())
            received.set()

        def log_message(self, format: str, *args: object) -> None:
            pass  # Suppress server logs

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = (
            f"{AUTH_URL}?client_id={client_id}&scope={SCOPE}"
            f"&redirect_uri={REDIRECT_URI}&response_type=code&state=e2e"
        )
        print(f"\nОткрываю браузер для авторизации TickTick...\n{url}\n")
        webbrowser.open(url)

        if not received.wait(timeout=_OAUTH_TIMEOUT):
            raise TimeoutError(
                f"Таймаут {_OAUTH_TIMEOUT}с — авторизация не завершена. "
                "Перезапустите с --setup-ticktick-auth"
            )
    finally:
        server.shutdown()

    if error or not auth_code:
        raise RuntimeError(f"OAuth error: {error}")

    # Exchange code for tokens
    response = httpx.post(
        TOKEN_URL,
        data={
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        auth=(client_id, client_secret),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _refresh_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _save_tokens(tokens: dict) -> None:
    """Persist tokens to disk."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))


def _load_tokens() -> dict | None:
    """Load saved tokens from disk."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
```

**Step 4: Verify module imports cleanly**

Run: `cd /Users/andrewmoskalev/Projects/python/alice-ticktick && python -c "from tests.e2e.ticktick_auth import get_access_token; print('OK')"`
Expected: `OK`

**Step 5: Lint and format**

Run: `uv run ruff check tests/e2e/ticktick_auth.py && uv run ruff format tests/e2e/ticktick_auth.py`
Expected: no errors

**Step 6: Commit**

```bash
git add tests/e2e/ticktick_auth.py .env.example .gitignore
git commit -m "feat: TickTick OAuth helper for direct API cleanup in e2e tests"
```

---

### Task 2: Integrate into conftest — fixtures and cleanup

**Files:**
- Modify: `tests/e2e/conftest.py`

**Step 1: Add imports and constants to conftest.py**

At the top of `conftest.py`, add imports for the new module and TickTickClient:

```python
import os

from alice_ticktick.ticktick.client import TickTickClient

from .ticktick_auth import get_access_token
```

**Step 2: Add `--setup-ticktick-auth` pytest option**

In `pytest_addoption`, add:

```python
parser.addoption(
    "--setup-ticktick-auth",
    action="store_true",
    default=False,
    help="Open browser for TickTick OAuth login and save tokens",
)
```

**Step 3: Add `ticktick_client` session fixture**

After the `yandex_client` fixture:

```python
@pytest.fixture(scope="session")
def ticktick_client(request: pytest.FixtureRequest) -> TickTickClient | None:
    """Get a TickTickClient for direct API cleanup (optional).

    Requires TICKTICK_TEST_CLIENT_ID and TICKTICK_TEST_CLIENT_SECRET in .env.
    If --setup-ticktick-auth is passed, runs interactive OAuth flow.
    Returns None if credentials are not configured.
    """
    client_id = os.environ.get("TICKTICK_TEST_CLIENT_ID", "")
    client_secret = os.environ.get("TICKTICK_TEST_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        if request.config.getoption("--setup-ticktick-auth"):
            pytest.fail(
                "TICKTICK_TEST_CLIENT_ID and TICKTICK_TEST_CLIENT_SECRET "
                "must be set in .env for --setup-ticktick-auth"
            )
        return None

    if request.config.getoption("--setup-ticktick-auth"):
        # Force interactive flow (ignore saved tokens)
        from .ticktick_auth import _run_oauth_flow, _save_tokens

        tokens = _run_oauth_flow(client_id, client_secret)
        _save_tokens(tokens)
        access_token = tokens["access_token"]
    else:
        try:
            access_token = get_access_token(client_id, client_secret)
        except Exception as exc:
            print(f"\nTickTick auth unavailable ({exc}), cleanup will use voice fallback")
            return None

    return TickTickClient(access_token)
```

**Step 4: Replace `_warmup_and_cleanup` with API-based cleanup**

Replace the cleanup section (after `yield`) in `_warmup_and_cleanup`. The fixture now also depends on `ticktick_client`:

```python
@pytest.fixture(scope="session", autouse=True)
async def _warmup_and_cleanup(
    yandex_client: YandexDialogsClient,
    ticktick_client: TickTickClient | None,
) -> None:
    """Warm up before tests and clean up test tasks after."""
    await yandex_client.send("помощь")
    yandex_client.reset_session()

    yield  # type: ignore[misc]

    if ticktick_client is not None:
        await _cleanup_via_api(ticktick_client)
    else:
        await _cleanup_via_voice(yandex_client)
```

**Step 5: Extract old voice cleanup into `_cleanup_via_voice`**

```python
async def _cleanup_via_voice(yandex_client: YandexDialogsClient) -> None:
    """Delete test tasks via the voice interface (slow fallback)."""
    print(f"\n{'=' * 60}")
    print(f"Cleaning up tasks with '{TEST_TASK_PREFIX}' prefix (voice fallback)...")
    deleted = 0
    MAX_CLEANUP = 50
    MAX_ITERATIONS = 200
    SLEEP_BETWEEN = 3
    for _ in range(MAX_ITERATIONS):
        try:
            await asyncio.sleep(SLEEP_BETWEEN)
            await yandex_client.send_new_session()
            response = await yandex_client.send(f"удали задачу {TEST_TASK_PREFIX}")
        except Exception as exc:
            print(f"  Cleanup error (skipping iteration): {exc}")
            break
        r = response.lower()
        if "не найдена" in r or "не распознана" in r:
            break
        if "да или нет" in r or "удалить" in r:
            try:
                await asyncio.sleep(SLEEP_BETWEEN)
                confirm = await yandex_client.send("да")
                if "удалена" in confirm.lower():
                    deleted += 1
                    print(f"  Deleted task #{deleted}")
            except Exception as exc:
                print(f"  Cleanup confirm error (skipping): {exc}")
                break
        if deleted >= MAX_CLEANUP:
            print(f"WARNING: cleaned {deleted} tasks, stopping early")
            break
    print(f"Cleanup done: {deleted} tasks deleted")
    print("=" * 60)
```

**Step 6: Write `_cleanup_via_api`**

```python
async def _cleanup_via_api(client: TickTickClient) -> None:
    """Delete all test tasks directly via TickTick API (fast)."""
    print(f"\n{'=' * 60}")
    print(f"Cleaning up tasks with '{TEST_TASK_PREFIX}' prefix (API)...")

    # Collect all tasks: inbox + all projects
    all_tasks: list[tuple[str, str, str]] = []  # (task_id, project_id, title)

    try:
        inbox_tasks = await client.get_inbox_tasks()
        for t in inbox_tasks:
            if t.title.lower().startswith(TEST_TASK_PREFIX):
                all_tasks.append((t.id, t.project_id, t.title))

        projects = await client.get_projects()
        for proj in projects:
            try:
                proj_tasks = await client.get_tasks(proj.id)
                for t in proj_tasks:
                    if t.title.lower().startswith(TEST_TASK_PREFIX):
                        all_tasks.append((t.id, t.project_id, t.title))
            except Exception as exc:
                print(f"  Warning: failed to list tasks in project '{proj.name}': {exc}")
    except Exception as exc:
        print(f"  Error listing tasks: {exc}")
        print("=" * 60)
        return

    if not all_tasks:
        print("  No test tasks found.")
        print("=" * 60)
        return

    print(f"  Found {len(all_tasks)} test task(s)")

    deleted = 0
    for task_id, project_id, title in all_tasks:
        try:
            await client.delete_task(task_id, project_id)
            deleted += 1
            print(f"  Deleted: {title}")
        except Exception as exc:
            print(f"  Failed to delete '{title}': {exc}")
            # Rate limit — pause and retry once
            if "429" in str(exc):
                await asyncio.sleep(2)
                try:
                    await client.delete_task(task_id, project_id)
                    deleted += 1
                    print(f"  Deleted (retry): {title}")
                except Exception:
                    pass

    print(f"Cleanup done: {deleted}/{len(all_tasks)} tasks deleted")
    print("=" * 60)
```

**Step 7: Load .env in conftest (for TICKTICK_TEST_* vars)**

Add at top of conftest.py, after imports:

```python
from dotenv import load_dotenv

load_dotenv()
```

Check if `python-dotenv` is already a dependency. If not, it can be loaded from pydantic-settings (which depends on it), or we can use a simpler approach: read env vars that are already set via `.env` loading in pytest. Actually, check if pytest already loads `.env` via some plugin or if pydantic-settings auto-loads it. If neither, add a `conftest.py` level `load_dotenv()`.

Alternative: use `os.environ` directly — the user might have the vars exported in their shell, or we can add `env_file = ".env"` reading manually. Simplest: just `dotenv` since pydantic-settings already pulls it in as a dependency.

**Step 8: Run linters**

Run: `uv run ruff check tests/e2e/conftest.py && uv run ruff format tests/e2e/conftest.py`

**Step 9: Run mypy**

Run: `uv run mypy alice_ticktick/`
Expected: pass (conftest is outside alice_ticktick/)

**Step 10: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "feat: direct TickTick API cleanup for e2e tests with voice fallback"
```

---

### Task 3: Test the OAuth flow and cleanup

**Step 1: Run the OAuth setup**

```bash
uv run pytest tests/e2e/ --setup-ticktick-auth -v -s -k "test_e2e_greeting"
```

This will:
1. Open browser → TickTick OAuth page
2. User authorizes the test app
3. Tokens saved to `~/.ticktick_auth/tokens.json`
4. Run one lightweight test
5. After test: cleanup via API (should find and delete any leftover "кктест" tasks)

Expected output in cleanup section:
```
============================================================
Cleaning up tasks with 'кктест' prefix (API)...
  Found N test task(s)
  Deleted: кктест ...
  ...
Cleanup done: N/N tasks deleted
============================================================
```

**Step 2: Verify tokens persist**

```bash
cat ~/.ticktick_auth/tokens.json | python -m json.tool
```

Should show `access_token`, `refresh_token`, `token_type`, etc.

**Step 3: Run again without `--setup-ticktick-auth`**

```bash
uv run pytest tests/e2e/ -v -s -k "test_e2e_greeting"
```

Should use saved token (auto-refresh if needed), no browser opened.

**Step 4: Verify cleanup handles empty state**

Run greeting test again — cleanup should say "No test tasks found."

---

### Task 4: Update documentation

**Files:**
- Modify: `docs/SETUP.md` (section 8, add TickTick auth subsection)
- Modify: `.env.example`

**Step 1: Add TickTick auth section to SETUP.md**

After the "Авторизация" subsection in section 8, add a new subsection:

```markdown
### TickTick API авторизация (для быстрой очистки тестов)

Опционально: позволяет очищать тестовые задачи через TickTick API напрямую (секунды вместо минут).

**Создание тестового приложения:**

1. Перейти на https://developer.ticktick.com/manage
2. Создать **второе** OAuth-приложение (отдельное от продового)
3. Указать **Redirect URI**: `http://localhost:8080/callback`
4. Сохранить `client_id` и `client_secret` в `.env`:

\```env
TICKTICK_TEST_CLIENT_ID=...
TICKTICK_TEST_CLIENT_SECRET=...
\```

**Первый запуск:**

\```bash
uv run pytest tests/e2e/ --setup-ticktick-auth -v -s -k "test_e2e_greeting"
\```

Откроется браузер → авторизуйтесь в TickTick → токены сохранятся в `~/.ticktick_auth/tokens.json`.

**Повторная авторизация** (если refresh token протух):

\```bash
uv run pytest tests/e2e/ --setup-ticktick-auth -v -s -k "test_e2e_greeting"
\```

Без этой настройки cleanup использует голосовой fallback (медленнее, лимит 50 задач).
```

**Step 2: Lint and commit**

```bash
git add docs/SETUP.md .env.example
git commit -m "docs: add TickTick test app setup instructions for e2e cleanup"
```

---

### Task 5: Full CI check

**Step 1: Run full linter suite**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy alice_ticktick/
uv run pytest -m "not e2e" -v
```

All must pass.

**Step 2: Run e2e with API cleanup to verify end-to-end**

```bash
uv run pytest tests/e2e/ -v -s -k "test_e2e_greeting"
```

Verify API cleanup runs and completes.
