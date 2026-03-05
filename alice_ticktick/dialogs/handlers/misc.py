"""Miscellaneous intent handlers (welcome, help, goodbye, unknown)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aliceio.types import Response

from alice_ticktick.dialogs import responses as txt

if TYPE_CHECKING:
    from aliceio.types import Message


async def handle_welcome(message: Message) -> Response:
    """Handle new session greeting."""
    return Response(text=txt.WELCOME, tts=txt.WELCOME_TTS)


async def handle_help(message: Message) -> Response:
    """Handle help request."""
    return Response(text=txt.HELP)


async def handle_goodbye(message: Message) -> Response:
    """Handle goodbye / session end."""
    return Response(text=txt.GOODBYE, end_session=True)


async def handle_unknown(message: Message) -> Response:
    """Handle unrecognized commands."""
    return Response(text=txt.UNKNOWN)
