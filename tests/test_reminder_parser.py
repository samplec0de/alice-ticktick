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

    def test_none_value_defaults_to_one(self) -> None:
        """'за час' without explicit number defaults to 1."""
        assert build_trigger(None, "час") == "TRIGGER:-PT1H"
        assert build_trigger(None, "день") == "TRIGGER:-P1D"
        assert build_trigger(None, "минуту") == "TRIGGER:-PT1M"

    def test_none_unit(self) -> None:
        assert build_trigger(30, None) is None

    def test_unknown_unit(self) -> None:
        assert build_trigger(5, "секунд") is None

    def test_case_insensitive(self) -> None:
        assert build_trigger(10, "Минут") == "TRIGGER:-PT10M"

    def test_build_trigger_minutes_uses_T_notation(self) -> None:
        """TRIGGER:-PT30M — минуты требуют T-нотацию (time duration)."""
        result = build_trigger(30, "минут")
        assert result == "TRIGGER:-PT30M"
        # Не P30M (что было бы 30 месяцев!) и не P30D (30 дней)
        assert "PT" in result

    def test_build_trigger_hours_uses_T_notation(self) -> None:
        """TRIGGER:-PT2H — часы тоже требуют T-нотацию."""
        result = build_trigger(2, "часа")
        assert result == "TRIGGER:-PT2H"
        assert "PT" in result

    def test_build_trigger_days_uses_D_notation(self) -> None:
        """TRIGGER:-P1D — дни используют date-нотацию без T."""
        result = build_trigger(1, "день")
        assert result == "TRIGGER:-P1D"
        assert "PT" not in result


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
