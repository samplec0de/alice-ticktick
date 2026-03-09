"""E2E tests: Section 3.7 — Search tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


_SEARCH_XFAIL = pytest.mark.xfail(
    reason="NLU: search_task intent often intercepted by create_task/edit_task",
    strict=False,
)


def _is_search_response(text: str) -> bool:
    t = text.lower()
    return any(
        w in t for w in ("совпадение", "найдена", "не найдено", "ничего не найдено", "результат")
    )


async def test_search_report(yandex_client: YandexDialogsClient) -> None:
    """Search for a task about a report."""
    response = await yandex_client.send("найди задачу про отчёт")
    assert response != UNKNOWN
    assert _is_search_response(response), f"Expected search response: {response}"


@_SEARCH_XFAIL
async def test_search_milk(yandex_client: YandexDialogsClient) -> None:
    """Search for a task about milk."""
    response = await yandex_client.send("поиск задачи молоко")
    assert response != UNKNOWN
    assert _is_search_response(response), f"Expected search response: {response}"


async def test_search_buy(yandex_client: YandexDialogsClient) -> None:
    """Search for a task with 'купить'."""
    response = await yandex_client.send("найди задачу купить")
    assert response != UNKNOWN
    assert _is_search_response(response), f"Expected search response: {response}"


async def test_search_macbook(yandex_client: YandexDialogsClient) -> None:
    """Search for a task about MacBook — known edge case."""
    response = await yandex_client.send("найди задачу про макбук")
    assert response != UNKNOWN
    assert _is_search_response(response), f"Expected search response: {response}"
