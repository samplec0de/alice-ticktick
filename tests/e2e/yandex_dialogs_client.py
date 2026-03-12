"""Client for testing Alice skill via Yandex Dialogs internal API."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import httpx

_TRANSIENT_ERRORS = (
    "Произошла ошибка при обращении к TickTick",
    "Не удалось создать задачу",
    "Не удалось завершить задачу",
    "Не удалось удалить задачу",
)


class YandexDialogsClient:
    """Sends messages to an Alice skill draft via the Yandex Dialogs testing API.

    The API mirrors what the browser test page at
    ``dialogs.yandex.ru/.../draft/test`` does under the hood:

    POST /developer/api/skills/{skill_id}/message
    Body: {"text", "isDraft", "sessionId", "sessionSeq", "surface", "isAnonymousUser"}
    Headers: x-csrf-token (extracted from page HTML "secretkey" field)
    Auth: Yandex session cookies
    """

    BASE_URL = "https://dialogs.yandex.ru"

    def __init__(self, skill_id: str, cookies: dict[str, str], csrf_token: str) -> None:
        self.skill_id = skill_id
        self._csrf_token = csrf_token
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            cookies=cookies,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-csrf-token": csrf_token,
            },
            timeout=30.0,
        )
        self._session_id: str = uuid.uuid4().hex
        self._session_seq: int = 0
        self._session_state: dict[str, Any] | None = None

    async def send(self, text: str) -> str:
        """Send a message and return the skill's text response.

        Retries up to 3 times on transient TickTick API errors (rate limit, timeout).
        """
        max_retries = 3
        for attempt in range(1 + max_retries):
            self._session_seq += 1
            payload: dict[str, Any] = {
                "text": text,
                "isDraft": True,
                "sessionId": self._session_id,
                "sessionSeq": self._session_seq,
                "surface": "mobile",
                "isAnonymousUser": False,
            }
            if self._session_state is not None:
                payload["sessionState"] = self._session_state
            response = await self._client.post(
                f"/developer/api/skills/{self.skill_id}/message",
                json=payload,
            )
            response.raise_for_status()
            try:
                data = response.json()
                result = data["result"]
            except Exception as exc:
                raise RuntimeError(
                    f"Unexpected response from Yandex Dialogs API "
                    f"(cookies may be expired — re-run with --setup-yandex-auth): "
                    f"{response.text[:200]!r}"
                ) from exc

            # Update session from response
            session = result.get("session", {})
            if session.get("id"):
                self._session_id = session["id"]
            if session.get("seq"):
                self._session_seq = session["seq"]

            # Capture session_state for FSM multi-turn flows — testing API does not
            # auto-persist state, so we must echo it back in subsequent requests
            self._session_state = result.get("session_state")
            if self._session_state is None:
                self._session_state = result.get("sessionState")

            result_text: str = result["text"]

            # Retry on transient TickTick errors
            if attempt < max_retries and any(err in result_text for err in _TRANSIENT_ERRORS):
                await asyncio.sleep(5)
                continue

            return result_text

        raise RuntimeError("unreachable: loop always returns on the last iteration")

    async def send_new_session(self) -> str:
        """Start a new session (like page reload) and return the greeting."""
        self._session_id = uuid.uuid4().hex
        self._session_seq = 0
        self._session_state = None
        return await self.send("")

    def reset_session(self) -> None:
        """Reset session state for a fresh conversation."""
        self._session_id = uuid.uuid4().hex
        self._session_seq = 0
        self._session_state = None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @classmethod
    async def create(cls, skill_id: str, cookies: dict[str, str]) -> YandexDialogsClient:
        """Create a client by fetching the CSRF token from the test page."""
        async with httpx.AsyncClient(
            base_url=cls.BASE_URL,
            cookies=cookies,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                f"/developer/skills/{skill_id}/draft/test",
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Failed to load Yandex Dialogs test page (HTTP {exc.response.status_code}). "
                    "Cookies may be expired — re-run with --setup-yandex-auth"
                ) from exc
            match = re.search(r'"secretkey"\s*:\s*"([^"]+)"', resp.text)
            if not match:
                msg = (
                    "Could not extract CSRF token (secretkey) from test page. "
                    "Cookies may be expired — re-run with --setup-yandex-auth"
                )
                raise RuntimeError(msg)
            csrf_token = match.group(1)
        return cls(skill_id=skill_id, cookies=cookies, csrf_token=csrf_token)
