"""Miscellaneous intent handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aliceio.types import Response

from alice_ticktick.dialogs import responses as txt
from alice_ticktick.dialogs.help_topics import detect_help_topic, get_topic_help

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aliceio.types import Message


async def handle_welcome(message: Message) -> Response:
    """Handle new session greeting."""
    return Response(text=txt.WELCOME, tts=txt.WELCOME_TTS)


async def handle_help(message: Message) -> Response:
    """Handle help request. Detect topic from utterance if present."""
    utterance = (message.original_utterance or message.command or "").lower()
    topic = detect_help_topic(utterance)
    if topic is not None:
        return Response(text=get_topic_help(topic))
    return Response(text=txt.HELP)


async def handle_help_topic(topic_key: str) -> Response:
    """Return detailed help for a specific topic key. Falls back to general help."""
    try:
        return Response(text=get_topic_help(topic_key))
    except KeyError:
        logger.error("Unknown help topic key: %r", topic_key)
        return Response(text=txt.HELP)


async def handle_goodbye(message: Message) -> Response:
    """Handle goodbye / session end."""
    return Response(text=txt.GOODBYE, end_session=True)


async def handle_unknown(message: Message) -> Response:
    """Handle unrecognized commands."""
    return Response(text=txt.UNKNOWN)
