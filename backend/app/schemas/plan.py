"""
Pydantic v2 schemas for plan and plan task request/response serialization.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import PaginationMeta


class PlanTaskResponse(BaseModel):
    """Full plan task response."""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    title: str
    description: str
    smell_ids: list[UUID]
    affected_files: list[str]
    refactor_pattern: str
    dependencies: list[UUID]
    estimated_hours: float | None
    automated: bool
    status: str
    priority_override: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PlanTaskSummaryResponse(BaseModel):
    """Abbreviated task info for embedding inside PlanResponse."""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    title: str
    description: str
    smell_ids: list[UUID]
    affected_files: list[str]
    refactor_pattern: str
    dependencies: list[UUID]
    estimated_hours: float | None
    automated: bool
    status: str


class PlanResponse(BaseModel):
    """Full plan response including all tasks."""

    plan_id: UUID
    job_id: UUID
    status: str = "draft"
    estimated_effort_hours: float | None
    risk_level: str | None
    task_count: int
    automated_task_count: int
    priority_order: list[UUID]
    created_at: datetime
    tasks: list[PlanTaskSummaryResponse]


class PlanTaskListResponse(BaseModel):
    """Paginated list of plan tasks."""

    data: list[PlanTaskResponse]
    pagination: PaginationMeta


class PlanTaskUpdateRequest(BaseModel):
    """Request body for PATCH /plan/{job_id}/tasks/{task_id}."""

    status: str | None = Field(
        default=None,
        description="New status: approved | rejected",
    )
    priority_override: int | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RegeneratePlanRequest(BaseModel):
    """Request body for POST /plan/{job_id}/regenerate."""

    focus_smell_types: list[str] | None = Field(
        default=None,
        description="Restrict regeneration to these smell types",
    )
    exclude_task_ids: list[UUID] | None = Field(
        default=None,
        description="Task IDs to exclude from the new plan",
    )
    max_tasks: int | None = Field(default=None, ge=1, le=50)


class RegeneratePlanResponse(BaseModel):
    """Response after queuing a plan regeneration."""

    message: str
    job_id: UUID
    new_plan_id: UUID
