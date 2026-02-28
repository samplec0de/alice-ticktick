"""Tests for TickTick API v1 client."""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from alice_ticktick.ticktick.client import BASE_URL, TIMEOUT, TickTickClient
from alice_ticktick.ticktick.models import TaskCreate, TaskPriority


def _make_response(
    status_code: int = 200,
    json_data: Any = None,
    text: str = "",
) -> httpx.Response:
    """Create a mock httpx.Response."""
    content = json.dumps(json_data).encode() if json_data is not None else text.encode()
    return httpx.Response(
        status_code=status_code,
        content=content,
        request=httpx.Request("GET", f"{BASE_URL}/test"),
    )


SAMPLE_PROJECT = {"id": "proj1", "name": "Inbox"}
SAMPLE_TASK = {
    "id": "task1",
    "projectId": "proj1",
    "title": "Buy milk",
    "content": "",
    "priority": 0,
    "status": 0,
}


class TestTickTickClientInit:
    """Test client initialization."""

    def test_creates_client_with_token(self) -> None:
        client = TickTickClient(access_token="test-token")
        assert client._client.headers["Authorization"] == "Bearer test-token"
        assert str(client._client.base_url) == f"{BASE_URL}/"

    def test_timeout_is_set(self) -> None:
        client = TickTickClient(access_token="t")
        assert client._client.timeout == httpx.Timeout(TIMEOUT)


class TestGetProjects:
    """Test get_projects method."""

    @pytest.mark.asyncio
    async def test_returns_projects(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=[SAMPLE_PROJECT]))
            with patch.object(client._client, "get", mock):
                projects = await client.get_projects()

            assert len(projects) == 1
            assert projects[0].id == "proj1"
            assert projects[0].name == "Inbox"
            mock.assert_called_once_with("/project")

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=[]))
            with patch.object(client._client, "get", mock):
                projects = await client.get_projects()

            assert projects == []


class TestGetTasks:
    """Test get_tasks method."""

    @pytest.mark.asyncio
    async def test_returns_tasks(self) -> None:
        data = {"tasks": [SAMPLE_TASK]}
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=data))
            with patch.object(client._client, "get", mock):
                tasks = await client.get_tasks("proj1")

            assert len(tasks) == 1
            assert tasks[0].id == "task1"
            assert tasks[0].title == "Buy milk"
            mock.assert_called_once_with("/project/proj1/data")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tasks(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data={}))
            with patch.object(client._client, "get", mock):
                tasks = await client.get_tasks("proj1")

            assert tasks == []


class TestGetTask:
    """Test get_task method."""

    @pytest.mark.asyncio
    async def test_returns_task(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=SAMPLE_TASK))
            with patch.object(client._client, "get", mock):
                task = await client.get_task("task1", "proj1")

            assert task.id == "task1"
            assert task.project_id == "proj1"
            mock.assert_called_once_with("/project/proj1/task/task1")


class TestCreateTask:
    """Test create_task method."""

    @pytest.mark.asyncio
    async def test_creates_task(self) -> None:
        payload = TaskCreate(title="New task", project_id="proj1")
        response_data = {
            "id": "new1",
            "projectId": "proj1",
            "title": "New task",
            "content": "",
            "priority": 0,
            "status": 0,
        }
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=response_data))
            with patch.object(client._client, "post", mock):
                task = await client.create_task(payload)

            assert task.id == "new1"
            assert task.title == "New task"
            mock.assert_called_once_with(
                "/task",
                json={"title": "New task", "projectId": "proj1", "content": "", "priority": 0},
            )

    @pytest.mark.asyncio
    async def test_creates_task_with_priority(self) -> None:
        payload = TaskCreate(
            title="Urgent",
            project_id="proj1",
            priority=TaskPriority.HIGH,
        )
        response_data = {
            "id": "u1",
            "projectId": "proj1",
            "title": "Urgent",
            "content": "",
            "priority": 5,
            "status": 0,
        }
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=response_data))
            with patch.object(client._client, "post", mock):
                task = await client.create_task(payload)

            assert task.priority == TaskPriority.HIGH


class TestCompleteTask:
    """Test complete_task method."""

    @pytest.mark.asyncio
    async def test_completes_task(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(json_data=None, text=""))
            with patch.object(client._client, "post", mock):
                await client.complete_task("task1", "proj1")

            mock.assert_called_once_with("/project/proj1/task/task1/complete")


class TestErrorHandling:
    """Test error handling for various HTTP status codes."""

    @pytest.mark.asyncio
    async def test_unauthorized(self) -> None:
        from alice_ticktick.ticktick.client import TickTickUnauthorizedError

        async with TickTickClient(access_token="bad") as client:
            mock = AsyncMock(return_value=_make_response(status_code=401, text="Unauthorized"))
            with (
                patch.object(client._client, "get", mock),
                pytest.raises(TickTickUnauthorizedError) as exc_info,
            ):
                await client.get_projects()

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        from alice_ticktick.ticktick.client import TickTickNotFoundError

        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(status_code=404, text="Not Found"))
            with (
                patch.object(client._client, "get", mock),
                pytest.raises(TickTickNotFoundError) as exc_info,
            ):
                await client.get_task("no", "proj1")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_rate_limit(self) -> None:
        from alice_ticktick.ticktick.client import TickTickRateLimitError

        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(status_code=429, text="Rate Limited"))
            with (
                patch.object(client._client, "get", mock),
                pytest.raises(TickTickRateLimitError) as exc_info,
            ):
                await client.get_projects()

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_server_error(self) -> None:
        from alice_ticktick.ticktick.client import TickTickServerError

        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(
                return_value=_make_response(status_code=500, text="Internal Server Error")
            )
            with (
                patch.object(client._client, "get", mock),
                pytest.raises(TickTickServerError) as exc_info,
            ):
                await client.get_projects()

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_generic_error(self) -> None:
        from alice_ticktick.ticktick.client import TickTickError

        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(return_value=_make_response(status_code=418, text="I'm a teapot"))
            with (
                patch.object(client._client, "get", mock),
                pytest.raises(TickTickError) as exc_info,
            ):
                await client.get_projects()

            assert exc_info.value.status_code == 418

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        async with TickTickClient(access_token="t") as client:
            mock = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            with patch.object(client._client, "get", mock), pytest.raises(httpx.TimeoutException):
                await client.get_projects()


class TestContextManager:
    """Test async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self) -> None:
        client = TickTickClient(access_token="t")
        mock_close = AsyncMock()
        with patch.object(client._client, "aclose", mock_close):
            async with client:
                pass
        mock_close.assert_called_once()
