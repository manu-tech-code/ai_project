"""
Pydantic v2 schemas for smell request/response serialization.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import PaginationMeta


class SmellAffectedNode(BaseModel):
    """Condensed UCG node info for embedding in smell responses."""

    node_id: UUID
    node_type: str
    qualified_name: str


class SmellResponse(BaseModel):
    """Full smell detail response including evidence and LLM rationale."""

    model_config = ConfigDict(from_attributes=True)

    smell_id: UUID
    job_id: UUID
    smell_type: str
    severity: str
    description: str
    confidence: float
    dismissed: bool
    dismissed_at: datetime | None
    dismissed_by: str | None
    dismissed_reason: str | None
    # Note: populated in route handlers by joining UCGNode data.
    affected_nodes: list[SmellAffectedNode]
    evidence: dict
    llm_rationale: str | None
    created_at: datetime


class SmellListResponse(BaseModel):
    """Paginated list of smell responses."""

    data: list[SmellResponse]
    pagination: PaginationMeta


class SmellDismissRequest(BaseModel):
    """Request body for POST /smells/{job_id}/{smell_id}/dismiss."""

    reason: str = Field(..., min_length=10, max_length=1000)
    dismissed_by: str | None = None


class SmellDismissResponse(BaseModel):
    """Response after successfully dismissing a smell."""

    smell_id: UUID
    dismissed: bool
    dismissed_at: datetime
    dismissed_by: str | None
    reason: str


class SmellSeverityBreakdown(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class SmellSummaryResponse(BaseModel):
    """Aggregated smell statistics by type and severity."""

    job_id: UUID
    total_smells: int
    dismissed_smells: int
    active_smells: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    affected_files: int
    estimated_tech_debt_hours: float
