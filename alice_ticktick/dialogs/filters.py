"""Custom aliceio filters for intent matching."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aliceio.filters.base import Filter

if TYPE_CHECKING:
    from aliceio.types import Message


class IntentFilter(Filter):
    """Match messages that contain a specific NLU intent."""

    def __init__(self, intent_id: str) -> None:
        self.intent_id = intent_id

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        if message.nlu is None:
            return False
        intent_data = message.nlu.intents.get(self.intent_id)
        if intent_data is None:
            return False
        return {"intent_data": intent_data}

    def __repr__(self) -> str:
        return self._signature_to_string(self.intent_id)


class NewSessionFilter(Filter):
    """Match new session messages (session.new is True)."""

    async def __call__(self, message: Message) -> bool:
        return message.session.new

    def __repr__(self) -> str:
        return "NewSessionFilter()"
