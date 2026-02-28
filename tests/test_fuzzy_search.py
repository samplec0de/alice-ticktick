"""Tests for fuzzy search utilities."""

from alice_ticktick.dialogs.nlp.fuzzy_search import find_best_match, find_matches


class TestFindBestMatch:
    def test_exact_match(self) -> None:
        candidates = ["Купить молоко", "Позвонить врачу", "Отправить отчёт"]
        result = find_best_match("Купить молоко", candidates)
        assert result == "Купить молоко"

    def test_typo_match(self) -> None:
        candidates = ["Подготовить отчёт", "Купить продукты"]
        result = find_best_match("Подготовить отчот", candidates)
        assert result == "Подготовить отчёт"

    def test_word_reorder(self) -> None:
        candidates = ["Купить молоко и хлеб"]
        result = find_best_match("хлеб и молоко купить", candidates)
        assert result == "Купить молоко и хлеб"

    def test_english_match(self) -> None:
        candidates = ["Buy groceries", "Call doctor", "Send report"]
        result = find_best_match("buy groceries", candidates)
        assert result == "Buy groceries"

    def test_mixed_language(self) -> None:
        candidates = ["Deploy на staging", "Фикс бага login"]
        result = find_best_match("deploy staging", candidates)
        assert result == "Deploy на staging"

    def test_no_match_below_threshold(self) -> None:
        candidates = ["Купить молоко", "Позвонить врачу"]
        result = find_best_match("абсолютно другое", candidates)
        assert result is None

    def test_custom_threshold(self) -> None:
        candidates = ["Купить молоко"]
        # With a very high threshold, partial match should fail
        result = find_best_match("молок", candidates, threshold=95)
        assert result is None

    def test_empty_query(self) -> None:
        assert find_best_match("", ["задача"]) is None

    def test_empty_candidates(self) -> None:
        assert find_best_match("запрос", []) is None

    def test_both_empty(self) -> None:
        assert find_best_match("", []) is None


class TestFindMatches:
    def test_returns_multiple(self) -> None:
        candidates = ["Купить молоко", "Купить хлеб", "Купить воду", "Позвонить"]
        results = find_matches("купить", candidates)
        assert len(results) >= 2
        titles = [title for title, _score in results]
        assert all("Купить" in t for t in titles)

    def test_scores_are_floats(self) -> None:
        candidates = ["Купить молоко"]
        results = find_matches("Купить молоко", candidates)
        assert len(results) == 1
        _title, score = results[0]
        assert isinstance(score, float)
        assert score > 0

    def test_limit(self) -> None:
        candidates = [f"Задача {i}" for i in range(20)]
        results = find_matches("задача", candidates, limit=3)
        assert len(results) <= 3

    def test_empty_query(self) -> None:
        assert find_matches("", ["задача"]) == []

    def test_empty_candidates(self) -> None:
        assert find_matches("запрос", []) == []
