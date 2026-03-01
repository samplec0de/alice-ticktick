"""Pydantic models for TickTick API v1 entities."""

from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field, field_serializer


class TaskPriority(IntEnum):
    """TickTick task priority levels."""

    NONE = 0
    LOW = 1
    MEDIUM = 3
    HIGH = 5


class ChecklistItem(BaseModel):
    """A single checklist item within a task."""

    id: str = ""
    title: str
    status: int = 0  # 0 = incomplete, 1 = completed
    sort_order: int = Field(default=0, alias="sortOrder")

    model_config = {"populate_by_name": True}


class Task(BaseModel):
    """TickTick task."""

    id: str
    project_id: str = Field(alias="projectId")
    title: str
    content: str = ""
    priority: TaskPriority = TaskPriority.NONE
    status: int = 0
    due_date: datetime | None = Field(default=None, alias="dueDate")
    start_date: datetime | None = Field(default=None, alias="startDate")
    items: list[ChecklistItem] = Field(default_factory=list)
    parent_id: str | None = Field(default=None, alias="parentId")

    model_config = {"populate_by_name": True}


class Project(BaseModel):
    """TickTick project."""

    id: str
    name: str


class TaskCreate(BaseModel):
    """Payload for creating a task."""

    title: str
    project_id: str | None = Field(default=None, alias="projectId")
    content: str = ""
    priority: TaskPriority = TaskPriority.NONE
    due_date: str | None = Field(default=None, alias="dueDate")
    start_date: str | None = Field(default=None, alias="startDate")
    items: list[dict[str, Any]] | None = None
    parent_id: str | None = Field(default=None, alias="parentId")

    model_config = {"populate_by_name": True}


class TaskUpdate(BaseModel):
    """Payload for updating a task."""

    id: str
    project_id: str = Field(alias="projectId")
    title: str | None = None
    priority: TaskPriority | None = None
    start_date: datetime | None = Field(default=None, alias="startDate")
    due_date: datetime | None = Field(default=None, alias="dueDate")
    items: list[dict[str, Any]] | None = None

    model_config = {"populate_by_name": True}

    @field_serializer("start_date", "due_date")
    @classmethod
    def serialize_datetime(cls, value: datetime | None) -> str | None:
        """Format datetime to TickTick API format."""
        if value is None:
            return None
        return value.strftime("%Y-%m-%dT%H:%M:%S.000%z")
