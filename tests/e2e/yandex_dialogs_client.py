"""Client for testing Alice skill via Yandex Dialogs internal API."""

from __future__ import annotations

import asyncio
import re
import uuid

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

    async def send(self, text: str) -> str:
        """Send a message and return the skill's text response.

        Retries once on transient TickTick API errors (rate limit, timeout).
        """
        max_retries = 3
        for attempt in range(1 + max_retries):
            self._session_seq += 1
            payload = {
                "text": text,
                "isDraft": True,
                "sessionId": self._session_id,
                "sessionSeq": self._session_seq,
                "surface": "mobile",
                "isAnonymousUser": False,
            }
            response = await self._client.post(
                f"/developer/api/skills/{self.skill_id}/message",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            result = data["result"]

            # Update session from response
            session = result.get("session", {})
            if session.get("id"):
                self._session_id = session["id"]
            if session.get("seq"):
                self._session_seq = session["seq"]

            result_text: str = result["text"]

            # Retry on transient TickTick errors
            if attempt < max_retries and any(err in result_text for err in _TRANSIENT_ERRORS):
                await asyncio.sleep(5)
                continue

            return result_text

        return result_text  # unreachable, satisfies type checker

    async def send_new_session(self) -> str:
        """Start a new session (like page reload) and return the greeting."""
        self._session_id = uuid.uuid4().hex
        self._session_seq = 0
        return await self.send("")

    def reset_session(self) -> None:
        """Reset session state for a fresh conversation."""
        self._session_id = uuid.uuid4().hex
        self._session_seq = 0

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
            resp.raise_for_status()
            match = re.search(r'"secretkey"\s*:\s*"([^"]+)"', resp.text)
            if not match:
                msg = (
                    "Could not extract CSRF token (secretkey) from test page. "
                    "Cookies may be expired — re-run with --setup-yandex-auth"
                )
                raise RuntimeError(msg)
            csrf_token = match.group(1)
        return cls(skill_id=skill_id, cookies=cookies, csrf_token=csrf_token)
