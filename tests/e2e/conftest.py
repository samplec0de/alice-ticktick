"""E2E test fixtures: auth, client, cleanup.

IMPORTANT: E2E tests run against a REAL TickTick account (not a test/sandbox one),
because a separate TickTick Premium subscription for testing would be wasteful.
All test task names use the unique prefix "кктест" to avoid collisions with real
tasks, and a cleanup fixture deletes them after the test session.
"""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from pathlib import Path

import pytest
from dotenv import dotenv_values

from alice_ticktick.ticktick.client import (
    TickTickClient,
    TickTickRateLimitError,
    TickTickUnauthorizedError,
)

from .ticktick_auth import _run_oauth_flow, _save_tokens, get_access_token
from .yandex_dialogs_client import YandexDialogsClient

_DOTENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_DOTENV: dict[str, str | None] = dotenv_values(_DOTENV_PATH)

SKILL_ID = "d3f073db-dece-42b8-9447-87511df30c83"
AUTH_DIR = Path(__file__).resolve().parent.parent.parent / ".yandex_auth"
COOKIES_FILE = AUTH_DIR / "cookies.json"
TEST_TASK_PREFIX = "кктест"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--setup-yandex-auth",
        action="store_true",
        default=False,
        help="Open browser for Yandex login and save cookies",
    )
    parser.addoption(
        "--setup-ticktick-auth",
        action="store_true",
        default=False,
        help="Open browser for TickTick OAuth login and save tokens",
    )


def _get_ticktick_test_creds() -> tuple[str, str]:
    """Get TICKTICK_TEST_CLIENT_ID/SECRET from env or .env file."""
    client_id = (
        os.environ.get("TICKTICK_TEST_CLIENT_ID") or _DOTENV.get("TICKTICK_TEST_CLIENT_ID") or ""
    )
    client_secret = (
        os.environ.get("TICKTICK_TEST_CLIENT_SECRET")
        or _DOTENV.get("TICKTICK_TEST_CLIENT_SECRET")
        or ""
    )
    return client_id, client_secret


def pytest_sessionstart(session: pytest.Session) -> None:
    """If --setup-ticktick-auth is passed, run TickTick OAuth setup early.

    Runs before any fixtures or tests so it works even without Yandex auth.
    """
    try:
        setup_auth = session.config.getoption("--setup-ticktick-auth")
    except ValueError:
        return
    if not setup_auth:
        return
    client_id, client_secret = _get_ticktick_test_creds()
    if not client_id or not client_secret:
        pytest.exit(
            "TICKTICK_TEST_CLIENT_ID and TICKTICK_TEST_CLIENT_SECRET "
            "must be set in environment or .env for --setup-ticktick-auth",
            returncode=1,
        )
    tokens = _run_oauth_flow(client_id, client_secret)
    _save_tokens(tokens)
    print("\nTickTick tokens saved to ~/.ticktick_auth/tokens.json")


def _load_cookies() -> dict[str, str]:
    """Load saved Yandex cookies from disk."""
    if not COOKIES_FILE.exists():
        pytest.skip(
            f"No saved auth at {COOKIES_FILE}. "
            "Run `uv run pytest tests/e2e/ --setup-yandex-auth` first."
        )
    try:
        data = json.loads(COOKIES_FILE.read_text())
    except json.JSONDecodeError:
        pytest.skip("Corrupted cookies file. Re-run with --setup-yandex-auth.")
    if not data:
        pytest.skip("Empty cookies file. Re-run with --setup-yandex-auth.")
    return data


@pytest.fixture(scope="session")
def yandex_cookies(request: pytest.FixtureRequest) -> dict[str, str]:
    """Get Yandex cookies — either by interactive login or from saved file."""
    if request.config.getoption("--setup-yandex-auth"):
        cookies = _interactive_login()
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
        return cookies
    return _load_cookies()


@pytest.fixture(scope="session")
async def yandex_client(yandex_cookies: dict[str, str]) -> YandexDialogsClient:
    """Create a YandexDialogsClient for the session."""
    client = await YandexDialogsClient.create(
        skill_id=SKILL_ID,
        cookies=yandex_cookies,
    )
    yield client  # type: ignore[misc]
    await client.close()


@pytest.fixture(scope="session")
def ticktick_client() -> TickTickClient | None:
    """Get a TickTickClient for direct API cleanup (optional).

    Requires TICKTICK_TEST_CLIENT_ID and TICKTICK_TEST_CLIENT_SECRET in env or .env.
    Tokens must be set up first via --setup-ticktick-auth.
    Returns None if credentials are not configured or token unavailable.
    """
    client_id, client_secret = _get_ticktick_test_creds()
    if not client_id or not client_secret:
        return None
    try:
        access_token = get_access_token(client_id, client_secret)
    except Exception as exc:
        warnings.warn(
            f"TickTick auth unavailable ({exc}), cleanup will use voice fallback",
            stacklevel=1,
        )
        return None
    return TickTickClient(access_token)


_PREREQUISITE_TASKS = [
    "кктест редактирования",
    "кктест удаления",
]


async def _create_prerequisite_tasks(client: YandexDialogsClient) -> None:
    """Create tasks required by edit/delete tests (via voice commands)."""
    for task_name in _PREREQUISITE_TASKS:
        await asyncio.sleep(3)
        client.reset_session()
        response = await client.send(f"создай задачу {task_name}")
        if "готово" in response.lower():
            print(f"  Created prerequisite task: {task_name}")
        else:
            print(f"  WARNING: Failed to create '{task_name}': {response[:100]}")


@pytest.fixture(scope="session", autouse=True)
async def _warmup_and_cleanup(
    yandex_client: YandexDialogsClient,
    ticktick_client: TickTickClient | None,
) -> None:
    """Warm up before tests and clean up test tasks after.

    Sends a help request to warm up Cloud Functions, then yields for tests.
    After all tests, deletes tasks whose names start with TEST_TASK_PREFIX.
    """
    await yandex_client.send("помощь")
    yandex_client.reset_session()

    # Create prerequisite tasks for edit/delete tests
    await _create_prerequisite_tasks(yandex_client)
    yandex_client.reset_session()

    yield  # type: ignore[misc]

    if ticktick_client is not None:
        await _cleanup_via_api(ticktick_client)
    else:
        await _cleanup_via_voice(yandex_client)


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
    except Exception as exc:
        print(f"  Error listing inbox tasks: {exc}")

    try:
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
        print(f"  Error listing projects: {exc}")

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
        except TickTickUnauthorizedError:
            print(
                "  ERROR: TickTick returned 401 Unauthorized. "
                "Re-run with --setup-ticktick-auth to refresh tokens."
            )
            break
        except TickTickRateLimitError:
            print(f"  Rate limited on '{title}', retrying after 2s...")
            await asyncio.sleep(2)
            try:
                await client.delete_task(task_id, project_id)
                deleted += 1
                print(f"  Deleted (retry): {title}")
            except Exception as retry_exc:
                print(f"  Retry also failed for '{title}': {retry_exc}")
        except Exception as exc:
            print(f"  Failed to delete '{title}': {exc}")

    print(f"Cleanup done: {deleted}/{len(all_tasks)} tasks deleted")
    print("=" * 60)


@pytest.fixture(autouse=True)
async def _reset_session(yandex_client: YandexDialogsClient) -> None:
    """Start a fresh session before each test.

    Sends a new-session message to clear any leftover FSM state (e.g. pending
    confirmation from a previous delete/edit flow).  The 5-second sleep avoids
    TickTick API rate limiting.
    """
    await asyncio.sleep(5)
    response = await yandex_client.send_new_session()
    # If a previous test left FSM in a confirmation state, cancel it and restart
    if "да или нет" in response.lower():
        await yandex_client.send("нет")
        await asyncio.sleep(2)
        await yandex_client.send_new_session()


def _interactive_login() -> dict[str, str]:
    """Open a browser for the user to log in, then extract cookies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.fail(
            "playwright is required for --setup-yandex-auth. "
            "Install: uv pip install playwright && python -m playwright install chromium"
        )

    test_url = f"https://dialogs.yandex.ru/developer/skills/{SKILL_ID}/draft/test"

    cookies: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Go to test page — Yandex will redirect to login if needed
        page.goto(test_url)

        print("\n" + "=" * 60)
        print("Войдите в Яндекс в открывшемся браузере.")
        print("Браузер закроется автоматически после успешного входа.")
        print("(таймаут: 5 минут)")
        print("=" * 60)

        # Wait until we're on the skill test page (not captcha/login)
        page.wait_for_url(
            f"**/developer/skills/{SKILL_ID}/draft/test**",
            timeout=300_000,
        )
        page.wait_for_load_state("networkidle")

        for cookie in context.cookies():
            if cookie["domain"].endswith("yandex.ru"):
                cookies[cookie["name"]] = cookie["value"]

        browser.close()

    if not cookies:
        pytest.fail("No cookies captured. Login may have failed.")
    return cookies
