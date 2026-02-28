"""TickTick API v1 async client."""

from typing import Any

import httpx

from alice_ticktick.ticktick.models import Project, Task, TaskCreate

BASE_URL = "https://api.ticktick.com/open/v1"
TIMEOUT = 3.0


class TickTickError(Exception):
    """Base exception for TickTick API errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"TickTick API error {status_code}: {message}")


class TickTickUnauthorizedError(TickTickError):
    """401 Unauthorized."""


class TickTickNotFoundError(TickTickError):
    """404 Not Found."""


class TickTickRateLimitError(TickTickError):
    """429 Too Many Requests."""


class TickTickServerError(TickTickError):
    """5xx Server Error."""


def _raise_for_status(response: httpx.Response) -> None:
    """Raise a typed exception for non-2xx responses."""
    if response.is_success:
        return

    code = response.status_code
    text = response.text

    if code == 401:
        raise TickTickUnauthorizedError(code, text)
    if code == 404:
        raise TickTickNotFoundError(code, text)
    if code == 429:
        raise TickTickRateLimitError(code, text)
    if code >= 500:
        raise TickTickServerError(code, text)

    raise TickTickError(code, text)


class TickTickClient:
    """Async client for TickTick Open API v1."""

    def __init__(self, access_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TickTickClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # -- Projects --

    async def get_projects(self) -> list[Project]:
        """Get all user projects."""
        response = await self._client.get("/project")
        _raise_for_status(response)
        return [Project.model_validate(p) for p in response.json()]

    # -- Tasks --

    async def get_tasks(self, project_id: str) -> list[Task]:
        """Get all tasks in a project."""
        response = await self._client.get(
            f"/project/{project_id}/data",
        )
        _raise_for_status(response)
        data: dict[str, Any] = response.json()
        raw_tasks: list[dict[str, Any]] = data.get("tasks", [])
        return [Task.model_validate(t) for t in raw_tasks]

    async def get_task(self, task_id: str, project_id: str) -> Task:
        """Get a single task by id."""
        response = await self._client.get(
            f"/project/{project_id}/task/{task_id}",
        )
        _raise_for_status(response)
        return Task.model_validate(response.json())

    async def create_task(self, payload: TaskCreate) -> Task:
        """Create a new task."""
        response = await self._client.post(
            "/task",
            json=payload.model_dump(by_alias=True, exclude_none=True),
        )
        _raise_for_status(response)
        return Task.model_validate(response.json())

    async def complete_task(self, task_id: str, project_id: str) -> None:
        """Mark a task as completed."""
        response = await self._client.post(
            f"/project/{project_id}/task/{task_id}/complete",
        )
        _raise_for_status(response)
