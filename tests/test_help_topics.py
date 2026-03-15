"""Tests for topic-based help detection and text."""

from __future__ import annotations

import pytest

from alice_ticktick.dialogs.help_topics import (
    _TOPIC_KEYWORDS,
    HELP_TOPICS,
    TOPIC_HELP_RE,
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


def test_topic_keywords_match_help_topics() -> None:
    """Every key in _TOPIC_KEYWORDS must have a corresponding HELP_TOPICS entry and vice versa."""
    keyword_keys = {k for k, _ in _TOPIC_KEYWORDS}
    assert keyword_keys == set(HELP_TOPICS)


def test_no_match_for_irrelevant_phrases() -> None:
    """Phrases without topic stems should return None."""
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


@pytest.mark.parametrize(
    ("utterance", "expected_group"),
    [
        ("как удалить задачу", "удалить задачу"),
        ("расскажи про проекты", "проекты"),
        ("расскажи о брифингах", "брифингах"),
        ("что такое чеклист", "чеклист"),
        ("объясни подзадачи", "подзадачи"),
        ("помощь с созданием", "созданием"),
        ("помощь по удалению", "удалению"),
    ],
)
def test_topic_help_re_matches(utterance: str, expected_group: str) -> None:
    """TOPIC_HELP_RE should match all help-like phrase patterns."""
    m = TOPIC_HELP_RE.search(utterance)
    assert m is not None, f"TOPIC_HELP_RE did not match: {utterance}"
    assert m.group(1).strip() == expected_group
