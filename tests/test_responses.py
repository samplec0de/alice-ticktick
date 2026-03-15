"""Tests for alice_ticktick.dialogs.responses utility functions."""

from alice_ticktick.dialogs.responses import api_error_detail
from alice_ticktick.ticktick.client import (
    TickTickRateLimitError,
    TickTickServerError,
)


class TestApiErrorDetail:
    """Test api_error_detail() produces safe user-facing messages."""

    def test_generic_exception(self) -> None:
        result = api_error_detail(Exception("some error"))
        assert "Exception" in result
        assert "some error" not in result
        assert "Произошла ошибка при обращении к TickTick" in result

    def test_generic_exception_empty_message(self) -> None:
        result = api_error_detail(Exception(""))
        assert "Exception" in result
        assert "Произошла ошибка при обращении к TickTick" in result

    def test_rate_limit_error_shows_status_code(self) -> None:
        exc = TickTickRateLimitError(429, "Rate Limited")
        result = api_error_detail(exc)
        assert "TickTickRateLimitError" in result
        assert "код 429" in result
        assert "Rate Limited" not in result
        assert "Попробуйте позже" in result

    def test_server_error_shows_status_code(self) -> None:
        exc = TickTickServerError(500, "Internal")
        result = api_error_detail(exc)
        assert "TickTickServerError" in result
        assert "код 500" in result
        assert "Internal" not in result
        assert "Попробуйте позже" in result
