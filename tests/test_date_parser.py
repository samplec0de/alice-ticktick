"""Tests for YANDEX.DATETIME slot parser."""

import datetime
from unittest.mock import MagicMock

import pytest

from alice_ticktick.dialogs.nlp.date_parser import extract_dates_from_nlu, parse_yandex_datetime

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


class TestExtractDatesFromNlu:
    """Tests for extract_dates_from_nlu (hybrid NLU entity extraction)."""

    def test_time_range_strips_date_words(self) -> None:
        """Yandex NLU: 'завтра' not in entity range but semantics included."""
        from aliceio.types import DateTimeEntity, Entity, TokensEntity

        # "добавь задачу кино на завтра с 19:00 до 21:30"  # noqa: RUF003
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
