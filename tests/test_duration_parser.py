"""Tests for duration parser."""

import datetime

from alice_ticktick.dialogs.nlp.duration_parser import parse_duration


class TestParseDuration:
    def test_hours_with_value(self) -> None:
        assert parse_duration(2, "час") == datetime.timedelta(hours=2)

    def test_hours_without_value(self) -> None:
        assert parse_duration(None, "час") == datetime.timedelta(hours=1)

    def test_minutes_with_value(self) -> None:
        assert parse_duration(30, "минута") == datetime.timedelta(minutes=30)

    def test_minutes_without_value(self) -> None:
        assert parse_duration(None, "минута") == datetime.timedelta(minutes=1)

    def test_half_hour(self) -> None:
        assert parse_duration(None, "полчаса") == datetime.timedelta(minutes=30)

    def test_half_hour_ignores_value(self) -> None:
        assert parse_duration(3, "полчаса") == datetime.timedelta(minutes=30)

    def test_none_unit_returns_none(self) -> None:
        assert parse_duration(2, None) is None

    def test_unknown_unit_returns_none(self) -> None:
        assert parse_duration(1, "неизвестное") is None

    def test_hours_declensions(self) -> None:
        for word in ("час", "часа", "часов"):
            assert parse_duration(3, word) == datetime.timedelta(hours=3)

    def test_minutes_declensions(self) -> None:
        for word in ("минута", "минуту", "минуты", "минут"):
            assert parse_duration(15, word) == datetime.timedelta(minutes=15)
