"""E2E tests: Section 3.2 — Create task (basic, recurring, reminders, duration)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .expected_responses import DURATION_MISSING_START_TIME, TASK_NAME_REQUIRED, UNKNOWN

if TYPE_CHECKING:
    from .yandex_dialogs_client import YandexDialogsClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _norm(text: str) -> str:
    """Normalize for comparison: lowercase + ё→е."""
    return text.lower().replace("ё", "е")


# ---------------------------------------------------------------------------
# 3.2.1  Basic creation (8 tests)
# ---------------------------------------------------------------------------


async def test_create_simple(yandex_client: YandexDialogsClient) -> None:
    """Create a task with no date or priority."""
    response = await yandex_client.send("создай задачу кктест купить хлеб")
    assert "Готово" in response
    assert "кктест купить хлеб" in _norm(response)


async def test_create_with_date_tomorrow(yandex_client: YandexDialogsClient) -> None:
    """Create a task for tomorrow."""
    response = await yandex_client.send("создай задачу кктест позвонить маме на завтра")
    assert "Готово" in response
    assert "кктест позвонить маме" in _norm(response)


async def test_create_with_date_friday(yandex_client: YandexDialogsClient) -> None:
    """Create a task for Friday."""
    response = await yandex_client.send("создай задачу кктест отправить отчёт на пятницу")
    assert "Готово" in response
    assert "кктест отправить отчет" in _norm(response)


async def test_create_with_priority(yandex_client: YandexDialogsClient) -> None:
    """Create a task with high priority."""
    response = await yandex_client.send(
        "создай задачу кктест подготовить презентацию с высоким приоритетом"
    )
    assert "Готово" in response
    assert "кктест подготовить презентацию" in _norm(response)


async def test_create_without_name_reprompt(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create task intent without a name should trigger a reprompt."""
    response = await yandex_client.send("создай задачу")
    assert TASK_NAME_REQUIRED in response


async def test_create_with_project(yandex_client: YandexDialogsClient) -> None:
    """Create a task in a specific project."""
    response = await yandex_client.send("создай задачу кктест ревью кода в проекте Inbox")
    assert "Готово" in response
    assert "кктест ревью кода" in _norm(response)


async def test_create_new_task_variant(yandex_client: YandexDialogsClient) -> None:
    """Create a task using 'новая задача' phrasing."""
    response = await yandex_client.send("новая задача кктест забрать посылку")
    assert "Готово" in response
    assert "кктест забрать посылку" in _norm(response)


async def test_create_with_date_day_after_tomorrow(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a task for the day after tomorrow (послезавтра)."""
    response = await yandex_client.send("создай задачу кктест записаться к врачу на послезавтра")
    assert "Готово" in response
    assert "кктест записаться к врачу" in _norm(response)


# ---------------------------------------------------------------------------
# 3.2.2  Recurring via create (6 tests)
# ---------------------------------------------------------------------------


async def test_create_recurring_daily(yandex_client: YandexDialogsClient) -> None:
    """Create a recurring daily task."""
    response = await yandex_client.send("создай задачу кктест зарядка каждый день")
    assert "Готово" in response
    assert "кктест зарядка" in _norm(response)
    assert "каждый день" in response.lower()


async def test_create_recurring_monthly_date(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a recurring task on the 15th of each month."""
    response = await yandex_client.send("создай задачу кктест оплатить счёт каждое 15 число")
    assert "Готово" in response
    assert "кктест оплатить счет" in _norm(response)


async def test_create_recurring_every_2_days(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a task recurring every 2 days."""
    response = await yandex_client.send("создай задачу кктест полить цветы каждые 2 дня")
    assert "Готово" in response
    assert "кктест полить цветы" in _norm(response)


async def test_create_recurring_weekly_monday(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a task recurring every Monday."""
    response = await yandex_client.send("создай задачу кктест планёрка каждый понедельник")
    assert "Готово" in response
    assert "кктест планерка" in _norm(response)
    assert "каждый понедельник" in response.lower()


async def test_create_recurring_monthly(yandex_client: YandexDialogsClient) -> None:
    """Create a monthly recurring task."""
    response = await yandex_client.send("создай задачу кктест подвести итоги ежемесячно")
    assert "Готово" in response
    assert "кктест подвести итоги" in _norm(response)
    assert "ежемесячно" in response.lower() or "каждый месяц" in response.lower()


async def test_create_recurring_every_2_weeks(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a task recurring every 2 weeks."""
    response = await yandex_client.send("создай задачу кктест уборка каждые 2 недели")
    assert "Готово" in response
    assert "кктест уборка" in _norm(response)


# ---------------------------------------------------------------------------
# 3.2.3  With reminders (3 tests)
# ---------------------------------------------------------------------------


async def test_create_with_reminder_30min(yandex_client: YandexDialogsClient) -> None:
    """Create a task with a 30-minute reminder."""
    response = await yandex_client.send(
        "создай задачу кктест встреча с клиентом на завтра с напоминанием за 30 минут"
    )
    assert "Готово" in response
    assert "кктест встреча с клиентом" in _norm(response)
    assert "напоминание" in response.lower() or "напоминанием" in response.lower()


async def test_create_with_reminder_1hour(yandex_client: YandexDialogsClient) -> None:
    """Create a task with a 1-hour reminder."""
    response = await yandex_client.send(
        "создай задачу кктест созвон с командой с напоминанием за час"
    )
    assert "Готово" in response
    assert "кктест созвон с командой" in _norm(response)
    assert "напоминание" in response.lower() or "напоминанием" in response.lower()


async def test_create_recurring_with_reminder(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a daily recurring task with a reminder."""
    response = await yandex_client.send(
        "создай задачу кктест приём лекарств каждый день с напоминанием за 30 минут"
    )
    assert "Готово" in response
    assert "кктест прием лекарств" in _norm(response)
    assert "напоминание" in response.lower() or "напоминанием" in response.lower()


# ---------------------------------------------------------------------------
# 3.2.4  Meetings / duration (6 tests)
# ---------------------------------------------------------------------------


async def test_create_meeting_tomorrow_2hours(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a meeting for tomorrow at 10 lasting 2 hours."""
    response = await yandex_client.send("создай задачу кктест совещание завтра в 10 на 2 часа")
    assert "Готово" in response
    assert "кктест совещание" in _norm(response)


async def test_create_meeting_tomorrow_1hour(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a meeting for tomorrow at 12 lasting 1 hour."""
    response = await yandex_client.send("создай задачу кктест обед завтра в 12 на час")
    assert "Готово" in response
    assert "кктест обед" in _norm(response)


async def test_create_meeting_half_hour(yandex_client: YandexDialogsClient) -> None:
    """Create a meeting lasting half an hour."""
    response = await yandex_client.send("создай задачу кктест стендап завтра в 9 на полчаса")
    assert "Готово" in response
    assert "кктест стендап" in _norm(response)


async def test_create_meeting_range(yandex_client: YandexDialogsClient) -> None:
    """Create a meeting with explicit time range (с 14 до 16)."""
    response = await yandex_client.send("создай задачу кктест тренировка завтра с 14 до 16")
    assert "Готово" in response
    assert "кктест тренировка" in _norm(response)


async def test_create_duration_without_time_reprompt(
    yandex_client: YandexDialogsClient,
) -> None:
    """Duration without start time should trigger a reprompt."""
    response = await yandex_client.send("создай задачу кктест ретро на час")
    assert DURATION_MISSING_START_TIME in response or "Готово" in response
    assert response != UNKNOWN


async def test_create_meeting_with_reminder(
    yandex_client: YandexDialogsClient,
) -> None:
    """Create a meeting with duration and a reminder."""
    response = await yandex_client.send(
        "создай задачу кктест демо завтра в 15 на час с напоминанием за 30 минут"
    )
    assert "Готово" in response
    assert "кктест демо" in _norm(response)
