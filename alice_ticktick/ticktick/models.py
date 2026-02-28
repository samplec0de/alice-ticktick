"""Pydantic models for TickTick API v1 entities."""

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field, field_serializer


class TaskPriority(IntEnum):
    """TickTick task priority levels."""

    NONE = 0
    LOW = 1
    MEDIUM = 3
    HIGH = 5


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

    model_config = {"populate_by_name": True}


class TaskUpdate(BaseModel):
    """Payload for updating a task."""

    id: str
    project_id: str = Field(alias="projectId")
    title: str | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = Field(default=None, alias="dueDate")

    model_config = {"populate_by_name": True}

    @field_serializer("due_date")
    @classmethod
    def serialize_datetime(cls, value: datetime | None) -> str | None:
        """Format datetime to TickTick API format."""
        if value is None:
            return None
        return value.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
