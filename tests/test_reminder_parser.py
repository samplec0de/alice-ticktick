"""Tests for reminder NLU slot → TRIGGER parser."""

import pytest

from alice_ticktick.dialogs.nlp.reminder_parser import build_trigger, format_reminder


class TestBuildTrigger:
    """Tests for build_trigger: NLU slots → iCal TRIGGER string."""

    @pytest.mark.parametrize(
        "value, unit, expected",
        [
            (30, "минут", "TRIGGER:-PT30M"),
            (15, "минуты", "TRIGGER:-PT15M"),
            (1, "минуту", "TRIGGER:-PT1M"),
            (1, "час", "TRIGGER:-PT1H"),
            (2, "часа", "TRIGGER:-PT2H"),
            (24, "часов", "TRIGGER:-PT24H"),
            (1, "день", "TRIGGER:-P1D"),
            (3, "дня", "TRIGGER:-P3D"),
            (7, "дней", "TRIGGER:-P7D"),
        ],
    )
    def test_trigger(self, value: int, unit: str, expected: str) -> None:
        assert build_trigger(value, unit) == expected

    def test_zero_value(self) -> None:
        """value=0 means 'at the time of the task'."""
        assert build_trigger(0, "минут") == "TRIGGER:PT0S"

    def test_none_value(self) -> None:
        assert build_trigger(None, "минут") is None

    def test_none_unit(self) -> None:
        assert build_trigger(30, None) is None

    def test_unknown_unit(self) -> None:
        assert build_trigger(5, "секунд") is None

    def test_case_insensitive(self) -> None:
        assert build_trigger(10, "Минут") == "TRIGGER:-PT10M"


class TestFormatReminder:
    """Tests for format_reminder: TRIGGER → human-readable Russian."""

    @pytest.mark.parametrize(
        "trigger, expected",
        [
            ("TRIGGER:-PT30M", "за 30 минут"),
            ("TRIGGER:-PT1M", "за 1 минуту"),
            ("TRIGGER:-PT5M", "за 5 минут"),
            ("TRIGGER:-PT1H", "за 1 час"),
            ("TRIGGER:-PT2H", "за 2 часа"),
            ("TRIGGER:-PT5H", "за 5 часов"),
            ("TRIGGER:-P1D", "за 1 день"),
            ("TRIGGER:-P3D", "за 3 дня"),
            ("TRIGGER:-P7D", "за 7 дней"),
            ("TRIGGER:PT0S", "в момент задачи"),
        ],
    )
    def test_format(self, trigger: str, expected: str) -> None:
        assert format_reminder(trigger) == expected

    def test_unknown_trigger(self) -> None:
        assert format_reminder("TRIGGER:UNKNOWN") == "напоминание"

    def test_none(self) -> None:
        assert format_reminder(None) is None
