"""Tests for YANDEX.DATETIME slot parser."""

import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from alice_ticktick.dialogs.nlp.date_parser import (
    extract_dates_from_nlu,
    parse_date_range,
    parse_yandex_datetime,
)

NOW = datetime.datetime(2026, 3, 1, 10, 0, tzinfo=datetime.UTC)


class TestAbsoluteDates:
    def test_full_date(self) -> None:
        slot = {"year": 2026, "month": 6, "day": 15}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 6, 15)

    def test_date_with_time(self) -> None:
        slot = {"year": 2026, "month": 6, "day": 15, "hour": 14, "minute": 30}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.datetime(2026, 6, 15, 14, 30, tzinfo=datetime.UTC)

    def test_only_month_and_day(self) -> None:
        slot = {"month": 12, "day": 25}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 12, 25)

    def test_only_day(self) -> None:
        slot = {"day": 20}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 3, 20)

    def test_hour_only(self) -> None:
        slot = {"hour": 18}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.datetime(2026, 3, 1, 18, 0, tzinfo=datetime.UTC)


class TestRelativeDates:
    def test_tomorrow(self) -> None:
        slot = {"day": 1, "day_is_relative": True}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 3, 2)

    def test_day_after_tomorrow(self) -> None:
        slot = {"day": 2, "day_is_relative": True}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 3, 3)

    def test_today(self) -> None:
        slot = {"day": 0, "day_is_relative": True}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.date(2026, 3, 1)

    def test_relative_month(self) -> None:
        slot = {"month": 1, "month_is_relative": True, "day": 5}
        result = parse_yandex_datetime(slot, now=NOW)
        # month = 3 + 1 = 4, day = 5
        assert result == datetime.date(2026, 4, 5)

    def test_relative_hour(self) -> None:
        slot = {"hour": 2, "hour_is_relative": True}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.datetime(2026, 3, 1, 12, 0, tzinfo=datetime.UTC)


class TestEdgeCases:
    def test_empty_slot_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parse_yandex_datetime({})

    def test_defaults_to_now_when_no_now(self) -> None:
        slot = {"day": 1, "day_is_relative": True}
        result = parse_yandex_datetime(slot)
        utc_today = datetime.datetime.now(tz=datetime.UTC).date()
        expected = utc_today + datetime.timedelta(days=1)
        assert result == expected

    def test_relative_day_with_time(self) -> None:
        slot = {"day": 1, "day_is_relative": True, "hour": 9, "minute": 0}
        result = parse_yandex_datetime(slot, now=NOW)
        assert result == datetime.datetime(2026, 3, 2, 9, 0, tzinfo=datetime.UTC)

    def test_now_with_timezone_affects_relative_date(self) -> None:
        """When now has a non-UTC timezone, relative dates use that timezone."""
        msk = ZoneInfo("Europe/Moscow")
        # 2026-03-01 23:00 UTC = 2026-03-02 02:00 MSK
        now_utc = datetime.datetime(2026, 3, 1, 23, 0, tzinfo=datetime.UTC)
        now_msk = now_utc.astimezone(msk)

        slot = {"day": 1, "day_is_relative": True}

        # With UTC now → March 2
        result_utc = parse_yandex_datetime(slot, now=now_utc)
        assert result_utc == datetime.date(2026, 3, 2)

        # With MSK now → March 3 (because it's already March 2 in MSK)
        result_msk = parse_yandex_datetime(slot, now=now_msk)
        assert result_msk == datetime.date(2026, 3, 3)

    def test_now_with_timezone_affects_absolute_time(self) -> None:
        """Absolute hour preserves the timezone from now."""
        msk = ZoneInfo("Europe/Moscow")
        now_msk = datetime.datetime(2026, 3, 1, 10, 0, tzinfo=msk)

        slot = {"hour": 14, "minute": 30}
        result = parse_yandex_datetime(slot, now=now_msk)
        assert result == datetime.datetime(2026, 3, 1, 14, 30, tzinfo=msk)


class TestExtractDatesFromNlu:
    """Tests for extract_dates_from_nlu (hybrid NLU entity extraction)."""

    def test_time_range_strips_date_words(self) -> None:
        """Yandex NLU: 'завтра' not in entity range but semantics included."""
        from aliceio.types import DateTimeEntity, Entity, TokensEntity

        # "добавь задачу кино на завтра с 19:00 до 21:30"
        nlu = MagicMock()
        nlu.tokens = [
            "добавь",
            "задачу",
            "кино",
            "на",
            "завтра",
            "с",
            "19",
            "00",
            "до",
            "21",
            "30",
        ]
        nlu.entities = [
            Entity(
                type="YANDEX.DATETIME",
                tokens=TokensEntity(start=5, end=8),
                value=DateTimeEntity(day=1, day_is_relative=True, hour=19, minute=0),
            ),
            Entity(
                type="YANDEX.DATETIME",
                tokens=TokensEntity(start=8, end=11),
                value=DateTimeEntity(day=1, day_is_relative=True, hour=21, minute=30),
            ),
        ]

        result = extract_dates_from_nlu(nlu, command_token_count=2)
        assert result.task_name == "кино"
        assert result.start_date is not None
        assert result.end_date is not None

    def test_single_date_no_stripping_needed(self) -> None:
        """Simple case: 'добавь задачу купить молоко на завтра'."""
        from aliceio.types import DateTimeEntity, Entity, TokensEntity

        nlu = MagicMock()
        nlu.tokens = ["добавь", "задачу", "купить", "молоко", "на", "завтра"]
        nlu.entities = [
            Entity(
                type="YANDEX.DATETIME",
                tokens=TokensEntity(start=4, end=6),
                value=DateTimeEntity(day=1, day_is_relative=True),
            ),
        ]

        result = extract_dates_from_nlu(nlu, command_token_count=2)
        assert result.task_name == "купить молоко"
        assert result.start_date is not None
        assert result.end_date is None


MSK = ZoneInfo("Europe/Moscow")


class TestDateRange:
    def test_this_week_monday(self) -> None:
        # 2026-03-02 — понедельник
        now = datetime.date(2026, 3, 2)
        result = parse_date_range("this_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 2)
        assert result.date_to == datetime.date(2026, 3, 8)

    def test_this_week_wednesday(self) -> None:
        # 2026-03-04 — среда, неделя всё равно Пн–Вс
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("this_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 2)
        assert result.date_to == datetime.date(2026, 3, 8)

    def test_this_week_sunday(self) -> None:
        # 2026-03-08 — воскресенье, неделя всё равно Пн–Вс
        now = datetime.date(2026, 3, 8)
        result = parse_date_range("this_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 2)
        assert result.date_to == datetime.date(2026, 3, 8)

    def test_next_week(self) -> None:
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("next_week", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 9)
        assert result.date_to == datetime.date(2026, 3, 15)

    def test_this_month(self) -> None:
        now = datetime.date(2026, 3, 15)
        result = parse_date_range("this_month", now=now, tz=MSK)
        assert result is not None
        assert result.date_from == datetime.date(2026, 3, 1)
        assert result.date_to == datetime.date(2026, 3, 31)

    def test_this_month_february(self) -> None:
        # Февраль 2026 — 28 дней
        now = datetime.date(2026, 2, 10)
        result = parse_date_range("this_month", now=now, tz=MSK)
        assert result is not None
        assert result.date_to == datetime.date(2026, 2, 28)

    def test_unknown_value(self) -> None:
        now = datetime.date(2026, 3, 4)
        result = parse_date_range("unknown_value", now=now, tz=MSK)
        assert result is None
