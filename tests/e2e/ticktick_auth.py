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
