"""Tests for Russian priority word parser."""

import pytest

from alice_ticktick.dialogs.nlp.priority_parser import parse_priority


class TestKnownPriorities:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("высокий", 5),
            ("высокая", 5),
            ("высокие", 5),
            ("высоким", 5),
            ("срочно", 5),
            ("срочный", 5),
            ("срочные", 5),
            ("срочным", 5),
            ("важно", 5),
            ("важные", 5),
            ("важным", 5),
            ("критический", 5),
            ("критичный", 5),
            ("средний", 3),
            ("средняя", 3),
            ("средние", 3),
            ("средним", 3),
            ("нормальный", 3),
            ("низкий", 1),
            ("низкая", 1),
            ("низкие", 1),
            ("низким", 1),
            ("неважный", 1),
            ("неважные", 1),
            ("обычный", 0),
            ("обычные", 0),
            ("без приоритета", 0),
            ("нет", 0),
        ],
    )
    def test_known_word(self, text: str, expected: int) -> None:
        assert parse_priority(text) == expected


class TestNormalization:
    def test_leading_trailing_whitespace(self) -> None:
        assert parse_priority("  высокий  ") == 5

    def test_uppercase(self) -> None:
        assert parse_priority("ВЫСОКИЙ") == 5

    def test_mixed_case(self) -> None:
        assert parse_priority("Средний") == 3


class TestEdgeCases:
    def test_none_returns_none(self) -> None:
        assert parse_priority(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_priority("") is None

    def test_unknown_word_returns_none(self) -> None:
        assert parse_priority("суперважно") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert parse_priority("   ") is None
