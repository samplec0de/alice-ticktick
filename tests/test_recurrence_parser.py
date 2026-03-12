"""Tests for recurrence NLU slot → RRULE parser."""

import pytest

from alice_ticktick.dialogs.nlp.recurrence_parser import build_rrule, format_recurrence


class TestBuildRrule:
    """Tests for build_rrule: NLU slots → RRULE string."""

    # --- Basic frequencies ---
    @pytest.mark.parametrize(
        "freq, expected",
        [
            ("день", "RRULE:FREQ=DAILY"),
            ("дня", "RRULE:FREQ=DAILY"),
            ("дней", "RRULE:FREQ=DAILY"),
            ("ежедневно", "RRULE:FREQ=DAILY"),
            ("неделю", "RRULE:FREQ=WEEKLY"),
            ("недели", "RRULE:FREQ=WEEKLY"),
            ("недель", "RRULE:FREQ=WEEKLY"),
            ("еженедельно", "RRULE:FREQ=WEEKLY"),
            ("месяц", "RRULE:FREQ=MONTHLY"),
            ("месяца", "RRULE:FREQ=MONTHLY"),
            ("месяцев", "RRULE:FREQ=MONTHLY"),
            ("ежемесячно", "RRULE:FREQ=MONTHLY"),
            ("год", "RRULE:FREQ=YEARLY"),
            ("года", "RRULE:FREQ=YEARLY"),
            ("лет", "RRULE:FREQ=YEARLY"),
            ("ежегодно", "RRULE:FREQ=YEARLY"),
        ],
    )
    def test_basic_freq(self, freq: str, expected: str) -> None:
        assert build_rrule(rec_freq=freq) == expected

    # --- Days of week ---
    @pytest.mark.parametrize(
        "freq, byday",
        [
            ("понедельник", "MO"),
            ("вторник", "TU"),
            ("среду", "WE"),
            ("среда", "WE"),
            ("четверг", "TH"),
            ("пятницу", "FR"),
            ("пятница", "FR"),
            ("субботу", "SA"),
            ("суббота", "SA"),
            ("воскресенье", "SU"),
        ],
    )
    def test_weekday(self, freq: str, byday: str) -> None:
        assert build_rrule(rec_freq=freq) == f"RRULE:FREQ=WEEKLY;BYDAY={byday}"

    def test_weekdays(self) -> None:
        assert build_rrule(rec_freq="будни") == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_weekdays_alt(self) -> None:
        assert build_rrule(rec_freq="будням") == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

    def test_weekends(self) -> None:
        assert build_rrule(rec_freq="выходные") == "RRULE:FREQ=WEEKLY;BYDAY=SA,SU"

    def test_weekends_alt(self) -> None:
        assert build_rrule(rec_freq="выходным") == "RRULE:FREQ=WEEKLY;BYDAY=SA,SU"

    # --- Interval ---
    def test_interval_days(self) -> None:
        assert build_rrule(rec_freq="дня", rec_interval=3) == "RRULE:FREQ=DAILY;INTERVAL=3"

    def test_interval_weeks(self) -> None:
        assert build_rrule(rec_freq="недели", rec_interval=2) == "RRULE:FREQ=WEEKLY;INTERVAL=2"

    def test_interval_months(self) -> None:
        assert build_rrule(rec_freq="месяца", rec_interval=6) == "RRULE:FREQ=MONTHLY;INTERVAL=6"

    # --- By monthday ---
    def test_monthday(self) -> None:
        assert build_rrule(rec_monthday=15) == "RRULE:FREQ=MONTHLY;BYMONTHDAY=15"

    def test_monthday_1st(self) -> None:
        assert build_rrule(rec_monthday=1) == "RRULE:FREQ=MONTHLY;BYMONTHDAY=1"

    # --- None / unknown ---
    def test_none_freq(self) -> None:
        assert build_rrule() is None

    def test_unknown_freq(self) -> None:
        assert build_rrule(rec_freq="кварталу") is None

    # --- Case insensitive ---
    def test_case_insensitive(self) -> None:
        assert build_rrule(rec_freq="День") == "RRULE:FREQ=DAILY"


class TestFormatRecurrence:
    """Tests for format_recurrence: RRULE → human-readable Russian."""

    @pytest.mark.parametrize(
        "rrule, expected",
        [
            ("RRULE:FREQ=DAILY", "каждый день"),
            ("RRULE:FREQ=WEEKLY", "каждую неделю"),
            ("RRULE:FREQ=MONTHLY", "каждый месяц"),
            ("RRULE:FREQ=YEARLY", "каждый год"),
            ("RRULE:FREQ=DAILY;INTERVAL=3", "каждые 3 дня"),
            ("RRULE:FREQ=DAILY;INTERVAL=5", "каждые 5 дней"),
            ("RRULE:FREQ=DAILY;INTERVAL=21", "каждые 21 день"),
            ("RRULE:FREQ=WEEKLY;INTERVAL=2", "каждые 2 недели"),
            ("RRULE:FREQ=WEEKLY;INTERVAL=5", "каждые 5 недель"),
            ("RRULE:FREQ=MONTHLY;INTERVAL=6", "каждые 6 месяцев"),
            ("RRULE:FREQ=WEEKLY;BYDAY=MO", "каждый понедельник"),
            ("RRULE:FREQ=WEEKLY;BYDAY=FR", "каждую пятницу"),
            ("RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "по будням"),
            ("RRULE:FREQ=WEEKLY;BYDAY=SA,SU", "по выходным"),
            ("RRULE:FREQ=MONTHLY;BYMONTHDAY=15", "каждое 15 число"),
        ],
    )
    def test_format(self, rrule: str, expected: str) -> None:
        assert format_recurrence(rrule) == expected

    def test_unknown_rrule(self) -> None:
        assert format_recurrence("RRULE:FREQ=SECONDLY") == "повторяется"

    def test_none_returns_none(self) -> None:
        assert format_recurrence(None) is None


class TestBuildRruleFirstWordFallback:
    """Tests for build_rrule first-word extraction from greedy NLU values."""

    def test_multiword_day_extracts_daily(self) -> None:
        """'день пить воду' → RRULE with FREQ=DAILY."""
        assert build_rrule(rec_freq="день пить воду") == "RRULE:FREQ=DAILY"

    def test_multiword_monday_extracts_weekly(self) -> None:
        """'понедельник проверить отчёт' → RRULE with FREQ=WEEKLY;BYDAY=MO."""
        assert build_rrule(rec_freq="понедельник проверить отчёт") == "RRULE:FREQ=WEEKLY;BYDAY=MO"

    def test_unrecognized_multiword_returns_none(self) -> None:
        """Completely unrecognized multi-word → None."""
        assert build_rrule(rec_freq="кварталу платить налоги") is None

    def test_single_recognized_word_works(self) -> None:
        """Single recognized word still works."""
        assert build_rrule(rec_freq="ежедневно") == "RRULE:FREQ=DAILY"
