"""E2E test fixtures: auth, client, cleanup.

IMPORTANT: E2E tests run against a REAL TickTick account (not a test/sandbox one),
because a separate TickTick Premium subscription for testing would be wasteful.
All test task names use the unique prefix "кктест" to avoid collisions with real
tasks, and a cleanup fixture deletes them after the test session.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from .yandex_dialogs_client import YandexDialogsClient

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


def _load_cookies() -> dict[str, str]:
    """Load saved Yandex cookies from disk."""
    if not COOKIES_FILE.exists():
        pytest.skip(
            f"No saved auth at {COOKIES_FILE}. "
            "Run `uv run pytest tests/e2e/ --setup-yandex-auth` first."
        )
    data = json.loads(COOKIES_FILE.read_text())
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


@pytest.fixture(scope="session", autouse=True)
async def _warmup_and_cleanup(yandex_client: YandexDialogsClient) -> None:
    """Warm up before tests and clean up test tasks after.

    Sends a help request to warm up Cloud Functions, then yields for tests.
    After all tests, deletes tasks whose names contain TEST_TASK_PREFIX.
    """
    await yandex_client.send("помощь")
    yandex_client.reset_session()

    yield  # type: ignore[misc]

    # Cleanup: delete all tasks with the test prefix
    print(f"\n{'=' * 60}")
    print(f"Cleaning up tasks with '{TEST_TASK_PREFIX}' prefix...")
    deleted = 0
    for _ in range(200):
        await asyncio.sleep(3)
        await yandex_client.send_new_session()
        response = await yandex_client.send(f"удали задачу {TEST_TASK_PREFIX}")
        r = response.lower()
        if "не найдена" in r or "не распознана" in r:
            break
        if "да или нет" in r or "удалить" in r:
            await asyncio.sleep(3)
            confirm = await yandex_client.send("да")
            if "удалена" in confirm.lower():
                deleted += 1
                print(f"  Deleted task #{deleted}")
    print(f"Cleanup done: {deleted} tasks deleted")
    print("=" * 60)


@pytest.fixture(autouse=True)
async def _reset_session(yandex_client: YandexDialogsClient) -> None:
    """Start a fresh session before each test.

    Sends a new-session message to clear any leftover FSM state (e.g. pending
    confirmation from a previous delete/edit flow).  The 5-second sleep avoids
    TickTick API rate limiting.
    """
    await asyncio.sleep(5)
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
