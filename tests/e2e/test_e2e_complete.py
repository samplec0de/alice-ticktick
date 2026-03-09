"""E2E tests: Section 3.6 — Complete (mark done) tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_complete_mark(yandex_client: YandexDialogsClient) -> None:
    """Complete a task using 'отметь задачу'."""
    response = await yandex_client.send("отметь задачу кктест купить хлеб")
    assert response != UNKNOWN
    assert (
        "выполненной" in response.lower()
        or "не найдена" in response.lower()
        or "завершить" in response.lower()
    )


async def test_complete_finish(yandex_client: YandexDialogsClient) -> None:
    """Complete a task using 'завершить задачу'."""
    response = await yandex_client.send("завершить задачу кктест позвонить маме")
    assert response != UNKNOWN
    assert (
        "выполненной" in response.lower()
        or "не найдена" in response.lower()
        or "завершить" in response.lower()
    )


async def test_complete_done(yandex_client: YandexDialogsClient) -> None:
    """Complete a task using 'готово'."""
    response = await yandex_client.send("готово кктест отправить отчёт")
    assert response != UNKNOWN
    assert (
        "выполненной" in response.lower()
        or "не найдена" in response.lower()
        or "завершить" in response.lower()
    )


async def test_complete_done_alt(yandex_client: YandexDialogsClient) -> None:
    """Complete a task using 'сделал'."""
    response = await yandex_client.send("сделал кктест подготовить презентацию")
    assert response != UNKNOWN
    assert (
        "выполненной" in response.lower()
        or "не найдена" in response.lower()
        or "завершить" in response.lower()
    )


async def test_complete_close(yandex_client: YandexDialogsClient) -> None:
    """Complete a task using 'закрой задачу'."""
    response = await yandex_client.send("закрой задачу кктест забрать посылку")
    assert response != UNKNOWN
    assert (
        "выполненной" in response.lower()
        or "не найдена" in response.lower()
        or "завершить" in response.lower()
    )
