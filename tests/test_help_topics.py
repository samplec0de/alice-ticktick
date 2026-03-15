"""Tests for topic-based help detection and text."""

from __future__ import annotations

import pytest

from alice_ticktick.dialogs.help_topics import (
    HELP_TOPICS,
    detect_help_topic,
    get_topic_help,
)


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("помощь с созданием", "create"),
        ("помощь по удалению", "complete"),
        ("помоги с чеклистами", "subtasks"),
        ("помощь с поиском", "search"),
        ("помощь с изменением", "edit"),
        ("помощь с проектами", "projects"),
        ("помощь с брифингами", "briefings"),
        ("помощь с просмотром", "list"),
        ("помощь", None),
    ],
)
def test_detect_topic_from_help_utterance(utterance: str, expected: str | None) -> None:
    assert detect_help_topic(utterance) == expected


def test_detect_topic_case_insensitive() -> None:
    assert detect_help_topic("ПОМОЩЬ С СОЗДАНИЕМ") == "create"
    assert detect_help_topic("Помощь С Удалением") == "complete"


@pytest.mark.parametrize("topic_key", list(HELP_TOPICS))
def test_get_topic_help_returns_text(topic_key: str) -> None:
    text = get_topic_help(topic_key)
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.parametrize("topic_key", list(HELP_TOPICS))
def test_all_topics_have_back_reference(topic_key: str) -> None:
    text = get_topic_help(topic_key)
    assert "Скажите «помощь»" in text


def test_no_false_positives() -> None:
    """Actual commands should not be detected as help topic requests."""
    assert detect_help_topic("создай задачу") == "create"
    # But bare non-help phrases without topic stems → None
    assert detect_help_topic("привет") is None
    assert detect_help_topic("как дела") is None
    assert detect_help_topic("") is None


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("помощь с чек-листом", "subtasks"),
        ("помощь с чекистом", "subtasks"),
        ("помощь с чек листом", "subtasks"),
    ],
)
def test_asr_variants(utterance: str, expected: str) -> None:
    assert detect_help_topic(utterance) == expected


@pytest.mark.parametrize("topic_key", list(HELP_TOPICS))
def test_topic_help_fits_alice_limit(topic_key: str) -> None:
    text = get_topic_help(topic_key)
    assert len(text) <= 1024, f"Topic '{topic_key}' text is {len(text)} chars (max 1024)"
