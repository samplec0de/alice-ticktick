"""Cloud Function entry point for Alice skill."""

from __future__ import annotations

import logging
from typing import Any

from aliceio import Dispatcher, Skill
from aliceio.types import AliceResponse, Response

from alice_ticktick.config import settings
from alice_ticktick.dialogs.router import router

logger = logging.getLogger(__name__)

dp = Dispatcher()
dp.include_router(router)

skill = Skill(skill_id=settings.alice_skill_id)


async def _process_event(event: dict[str, Any]) -> dict[str, Any]:
    """Process a single Alice request and return a response dict."""
    response = await dp.feed_webhook_update(skill, event)
    if response is not None:
        return response.model_dump(exclude_none=True)

    # Fallback response if no handler matched
    fallback = AliceResponse(
        response=Response(text="Произошла ошибка. Попробуйте ещё раз."),
        version=event.get("version", "1.0"),
    )
    return fallback.model_dump(exclude_none=True)


async def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Yandex Cloud Functions entry point.

    Args:
        event: The HTTP request body parsed as a dict (Alice webhook payload).
        context: Yandex Cloud Functions context (unused).

    Returns:
        Alice response dict.
    """
    logger.info(
        "Incoming request session_id=%s",
        event.get("session", {}).get("session_id", "unknown"),
    )
    try:
        return await _process_event(event)
    except Exception:
        logger.exception("Unhandled error in handler")
        fallback = AliceResponse(
            response=Response(text="Произошла внутренняя ошибка. Попробуйте позже."),
            version=event.get("version", "1.0"),
        )
        return fallback.model_dump(exclude_none=True)
