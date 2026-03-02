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


from alice_ticktick.dialogs.intents import extract_create_task_slots


class TestCreateTaskSlotsExtraction:
    def test_duration_slots_extracted(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "совещание"},
                "date": {"value": {"day": 1, "day_is_relative": True}},
                "duration_value": {"value": 2},
                "duration_unit": {"value": "часа"},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.task_name == "совещание"
        assert slots.duration_value == 2
        assert slots.duration_unit == "часа"

    def test_duration_unit_only(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "ланч"},
                "duration_unit": {"value": "час"},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.duration_value is None
        assert slots.duration_unit == "час"

    def test_range_slots_extracted(self) -> None:
        intent_data = {
            "slots": {
                "task_name": {"value": "митинг"},
                "range_start": {"value": {"hour": 14}},
                "range_end": {"value": {"hour": 16}},
            }
        }
        slots = extract_create_task_slots(intent_data)
        assert slots.range_start == {"hour": 14}
        assert slots.range_end == {"hour": 16}

    def test_no_duration_fields_default_none(self) -> None:
        intent_data = {"slots": {"task_name": {"value": "тест"}}}
        slots = extract_create_task_slots(intent_data)
        assert slots.duration_value is None
        assert slots.duration_unit is None
        assert slots.range_start is None
        assert slots.range_end is None
