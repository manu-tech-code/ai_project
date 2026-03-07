"""
Pydantic v2 schemas for patch and validation result request/response serialization.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import PaginationMeta


class GeneratePatchesRequest(BaseModel):
    """Request body for POST /patches/{job_id}/generate."""

    task_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Subset of task IDs to generate patches for. "
            "Omit to generate for all pending automated tasks."
        ),
    )


class GeneratePatchesResponse(BaseModel):
    """Response returned by POST /patches/{job_id}/generate."""

    patches_created: int
    patch_ids: list[str]


class PatchSummaryResponse(BaseModel):
    """Abbreviated patch info for list responses (no diff content)."""

    model_config = ConfigDict(from_attributes=True)

    patch_id: UUID
    task_id: UUID
    file_path: str
    patch_type: str
    language: str
    status: str
    validation_passed: bool | None = None
    tokens_used: int | None
    model_used: str | None
    created_at: datetime


class PatchDetailResponse(BaseModel):
    """Full patch detail response including diff and file contents."""

    model_config = ConfigDict(from_attributes=True)

    patch_id: UUID
    task_id: UUID
    file_path: str
    patch_type: str
    language: str
    status: str
    diff: str
    original_content: str
    patched_content: str
    validation_passed: bool | None = None
    tokens_used: int | None
    model_used: str | None
    created_at: datetime
    applied_at: datetime | None
    applied_by: str | None
    reverted_at: datetime | None
    reverted_reason: str | None


class PatchListResponse(BaseModel):
    """Paginated list of patch summaries."""

    data: list[PatchSummaryResponse]
    pagination: PaginationMeta


class ApplyPatchRequest(BaseModel):
    """Request body for POST /patches/{job_id}/{patch_id}/apply."""

    applied_by: str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ApplyPatchResponse(BaseModel):
    """Response after marking a patch as applied."""

    patch_id: UUID
    status: str
    applied_at: datetime
    applied_by: str | None


class RevertPatchRequest(BaseModel):
    """Request body for POST /patches/{job_id}/{patch_id}/revert."""

    reason: str = Field(..., min_length=5, max_length=1000)


class RevertPatchResponse(BaseModel):
    """Response after marking a patch as reverted."""

    patch_id: UUID
    status: str
    reverted_at: datetime
    reason: str


class ValidationCheckResponse(BaseModel):
    """Result of a single validation check within a validation run."""

    check_name: str
    check_type: str
    passed: bool
    output: str
    duration_ms: int


class ValidationResultSummaryResponse(BaseModel):
    """Abbreviated validation result for list responses."""

    model_config = ConfigDict(from_attributes=True)

    result_id: UUID
    patch_id: UUID
    passed: bool
    overall_score: float
    check_summary: dict[str, bool]
    created_at: datetime


class ValidationResultDetailResponse(BaseModel):
    """Full validation result with all check details."""

    model_config = ConfigDict(from_attributes=True)

    result_id: UUID
    patch_id: UUID
    passed: bool
    overall_score: float
    checks: list[ValidationCheckResponse]
    created_at: datetime


class ValidationResultListResponse(BaseModel):
    """Paginated list of validation result summaries."""

    data: list[ValidationResultSummaryResponse]
    pagination: PaginationMeta


class RerunValidationResponse(BaseModel):
    """Response after queuing a validation re-run."""

    message: str
    job_id: UUID
    patches_queued: int
