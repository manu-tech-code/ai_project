"""
Pydantic v2 schemas for job request/response serialization.

All response schemas use ``from_attributes=True`` (ORM mode) so they can be
constructed directly from SQLAlchemy model instances.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobConfig(BaseModel):
    """User-supplied configuration overrides for an analysis job."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(
        default=None,
        description="LLM model override for this job (uses server default if not set)",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Restrict analysis to specific languages (empty = auto-detect all)",
    )
    skip_patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns to exclude from analysis (e.g. **/test/**, **/vendor/**)",
    )
    smell_severity_threshold: str = Field(
        default="low",
        description="Minimum severity to report: critical | high | medium | low",
    )
    max_patches_per_task: int = Field(default=5, ge=1, le=20)
    enable_extended_thinking: bool = Field(
        default=False,
        description="Use extended thinking mode for Transformer agent (slower, more thorough)",
    )


class AnalyzeRequest(BaseModel):
    """
    Request body for POST /analyze when submitting via JSON (non-multipart).

    For multipart uploads the ``repo_path`` is inferred from the uploaded archive.
    """

    repo_path: str = Field(..., description="Path to the repository on the server filesystem")
    label: str | None = Field(None, max_length=200)
    config: JobConfig = Field(default_factory=JobConfig)


class JobCreate(BaseModel):
    """Internal schema for creating a job record in the database."""

    label: str | None = None
    config: JobConfig = Field(default_factory=JobConfig)
    archive_filename: str | None = None
    archive_size_bytes: int | None = None
    archive_checksum: str | None = None


class JobSubmitResponse(BaseModel):
    """
    Response returned immediately after a job is accepted (HTTP 202).

    Includes hypermedia links for subsequent polling.
    """

    job_id: UUID
    status: str
    label: str | None
    created_at: datetime
    estimated_duration_seconds: int = 300
    links: dict[str, str]


class JobResponse(BaseModel):
    """Full job detail response including stage progress and statistics."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    status: str
    label: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    languages: list[str]
    file_count: int | None
    total_lines: int | None
    archive_size_bytes: int | None
    config: dict
    current_stage: str | None
    stage_progress: dict
    error: str | None
    ucg_stats: dict | None
    smell_count: int | None
    patch_count: int | None
    repo_url: str | None = None
    fix_branch: str | None = None
    fix_pr_url: str | None = None
    deferred_stages: list[str] = []


class JobSummaryResponse(BaseModel):
    """Abbreviated job info used in paginated list responses."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    status: str
    label: str | None
    created_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    languages: list[str]
    file_count: int | None
    smell_count: int | None
    patch_count: int | None
    repo_url: str | None = None


class PaginationMeta(BaseModel):
    """Pagination envelope metadata included in all list responses."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class JobListResponse(BaseModel):
    """Paginated list of job summaries."""

    data: list[JobSummaryResponse]
    pagination: PaginationMeta


class JobLogEntry(BaseModel):
    """A single agent progress log entry."""

    seq: int
    stage: str
    message: str
    percent: int
    created_at: datetime


class JobLogsResponse(BaseModel):
    """Incremental log response for a job."""

    job_id: UUID
    total: int
    logs: list[JobLogEntry]
