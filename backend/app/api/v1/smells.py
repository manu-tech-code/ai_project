"""
Smells endpoints — list, detail, dismiss, and aggregated summary.

GET  /smells/{job_id}                    — list all smells (filterable)
GET  /smells/{job_id}/summary            — aggregated statistics
GET  /smells/{job_id}/{smell_id}         — single smell detail
POST /smells/{job_id}/{smell_id}/dismiss — dismiss a smell with reason
"""

from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.cache import cache_get, cache_invalidate, cache_set
from app.models.job import Job
from app.models.smell import Smell
from app.models.ucg import UCGNode
from app.schemas.job import PaginationMeta
from app.schemas.smell import (
    SmellAffectedNode,
    SmellDismissRequest,
    SmellDismissResponse,
    SmellListResponse,
    SmellResponse,
    SmellSummaryResponse,
)

router = APIRouter()

# TTL for completed-job smell data — never changes after job completes.
_SMELL_TTL = 300  # 5 minutes
# TTL for in-progress or mutable smell data (active dismissals possible).
_SMELL_ACTIVE_TTL = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_job_or_404(job_id: UUID, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "message": f"No job found with ID {job_id}"},
        )
    return job


async def _batch_load_nodes(node_ids: list, db: AsyncSession) -> dict:
    """Load UCGNode rows for a list of IDs in a single query. Returns id -> node map."""
    if not node_ids:
        return {}
    nodes_result = await db.execute(
        select(UCGNode).where(UCGNode.id.in_(node_ids))
    )
    return {n.id: n for n in nodes_result.scalars().all()}


def _build_smell_response_from_nodes(smell: Smell, nodes_by_id: dict) -> SmellResponse:
    """Build SmellResponse using a pre-fetched node map (avoids per-smell DB calls)."""
    affected_nodes: list[SmellAffectedNode] = []
    if smell.affected_node_ids:
        for node_id in smell.affected_node_ids:
            node = nodes_by_id.get(node_id)
            if node is not None:
                affected_nodes.append(
                    SmellAffectedNode(
                        node_id=node.id,
                        node_type=node.node_type,
                        qualified_name=node.qualified_name,
                    )
                )
    return SmellResponse(
        smell_id=smell.id,
        job_id=smell.job_id,
        smell_type=smell.smell_type,
        severity=smell.severity,
        description=smell.description,
        confidence=smell.confidence,
        dismissed=smell.dismissed,
        dismissed_at=smell.dismissed_at,
        dismissed_by=smell.dismissed_by,
        dismissed_reason=smell.dismissed_reason,
        affected_nodes=affected_nodes,
        evidence=smell.evidence or {},
        llm_rationale=smell.llm_rationale,
        created_at=smell.created_at,
    )


async def _build_smell_response(smell: Smell, db: AsyncSession) -> SmellResponse:
    """Populate SmellResponse including affected UCGNode details (single-item path)."""
    node_ids = list(smell.affected_node_ids) if smell.affected_node_ids else []
    nodes_by_id = await _batch_load_nodes(node_ids, db)
    return _build_smell_response_from_nodes(smell, nodes_by_id)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


# NOTE: /summary must be registered BEFORE /{smell_id} to avoid routing conflict.
@router.get("/{job_id}/summary", response_model=SmellSummaryResponse)
async def get_smell_summary(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> SmellSummaryResponse:
    """Get aggregated smell statistics by type and severity for a job."""
    job = await _get_job_or_404(job_id, db)

    # Cache summary for completed jobs (no new smells after completion).
    # Use a shorter TTL for non-complete jobs (dismissed count may change).
    cache_key = f"alm:smells:summary:{job_id}"
    cached = await cache_get(cache_key)
    if cached:
        return SmellSummaryResponse(**cached)

    smells_result = await db.execute(
        select(Smell).where(Smell.job_id == job_id)
    )
    all_smells = smells_result.scalars().all()

    total_smells = len(all_smells)
    dismissed_smells = sum(1 for s in all_smells if s.dismissed)
    active_smells = total_smells - dismissed_smells

    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_type: dict[str, int] = {}
    affected_files: set[str] = set()
    estimated_hours = 0.0

    _severity_hours = {"critical": 8.0, "high": 4.0, "medium": 2.0, "low": 0.5}

    for smell in all_smells:
        if not smell.dismissed:
            by_severity[smell.severity] = by_severity.get(smell.severity, 0) + 1
            by_type[smell.smell_type] = by_type.get(smell.smell_type, 0) + 1
            estimated_hours += _severity_hours.get(smell.severity, 1.0)

            # Collect affected files from evidence if available.
            if smell.evidence and "file_path" in smell.evidence:
                affected_files.add(smell.evidence["file_path"])

    # Also gather file paths from affected nodes — single batched query.
    if all_smells:
        all_node_ids = [
            node_id
            for smell in all_smells
            if not smell.dismissed and smell.affected_node_ids
            for node_id in smell.affected_node_ids
        ]
        if all_node_ids:
            nodes_result = await db.execute(
                select(UCGNode.file_path).where(
                    UCGNode.id.in_(all_node_ids),
                    UCGNode.file_path.isnot(None),
                ).distinct()
            )
            for (fp,) in nodes_result.all():
                if fp:
                    affected_files.add(fp)

    response = SmellSummaryResponse(
        job_id=job_id,
        total_smells=total_smells,
        dismissed_smells=dismissed_smells,
        active_smells=active_smells,
        by_severity=by_severity,
        by_type=by_type,
        affected_files=len(affected_files),
        estimated_tech_debt_hours=round(estimated_hours, 1),
    )

    ttl = _SMELL_TTL if job.status == "complete" else _SMELL_ACTIVE_TTL
    await cache_set(cache_key, response.model_dump(), ttl=ttl)
    return response


@router.get("/{job_id}", response_model=SmellListResponse)
async def list_smells(
    job_id: UUID,
    severity: str | None = None,
    smell_type: str | None = None,
    dismissed: bool = False,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> SmellListResponse:
    """List all smells for a job with optional severity, type, and dismissal filters."""
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    job = await _get_job_or_404(job_id, db)

    # Cache key encodes all filter params.
    cache_key = f"alm:smells:list:{job_id}:p{page}:ps{page_size}:sev{severity or ''}:t{smell_type or ''}:d{int(dismissed)}"
    cached = await cache_get(cache_key)
    if cached:
        return SmellListResponse(**cached)

    query = select(Smell).where(Smell.job_id == job_id)
    count_query = select(func.count()).select_from(Smell).where(Smell.job_id == job_id)

    if not dismissed:
        query = query.where(Smell.dismissed.is_(False))
        count_query = count_query.where(Smell.dismissed.is_(False))
    if severity:
        query = query.where(Smell.severity == severity.lower())
        count_query = count_query.where(Smell.severity == severity.lower())
    if smell_type:
        query = query.where(Smell.smell_type == smell_type.lower())
        count_query = count_query.where(Smell.smell_type == smell_type.lower())

    total_items = (await db.execute(count_query)).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    smells_result = await db.execute(
        query.order_by(Smell.severity, Smell.created_at).offset(offset).limit(page_size)
    )
    smells = smells_result.scalars().all()

    # Batch-load all affected UCGNodes for this page in a single query (no N+1).
    all_node_ids = [
        node_id
        for smell in smells
        if smell.affected_node_ids
        for node_id in smell.affected_node_ids
    ]
    nodes_by_id = await _batch_load_nodes(all_node_ids, db)

    smell_responses = [
        _build_smell_response_from_nodes(smell, nodes_by_id)
        for smell in smells
    ]

    response = SmellListResponse(
        data=smell_responses,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )

    ttl = _SMELL_TTL if job.status == "complete" else _SMELL_ACTIVE_TTL
    await cache_set(cache_key, response.model_dump(), ttl=ttl)
    return response


@router.get("/{job_id}/{smell_id}", response_model=SmellResponse)
async def get_smell(
    job_id: UUID,
    smell_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> SmellResponse:
    """Get full detail for a single smell including all evidence and LLM rationale."""
    await _get_job_or_404(job_id, db)

    result = await db.execute(
        select(Smell).where(Smell.id == smell_id, Smell.job_id == job_id)
    )
    smell = result.scalar_one_or_none()
    if smell is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "smell_not_found", "message": f"No smell {smell_id} in job {job_id}"},
        )
    return await _build_smell_response(smell, db)


@router.post("/{job_id}/{smell_id}/dismiss", response_model=SmellDismissResponse)
async def dismiss_smell(
    job_id: UUID,
    smell_id: UUID,
    body: SmellDismissRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> SmellDismissResponse:
    """Dismiss a smell as a known/acceptable issue with a required reason."""
    await _get_job_or_404(job_id, db)

    result = await db.execute(
        select(Smell).where(Smell.id == smell_id, Smell.job_id == job_id)
    )
    smell = result.scalar_one_or_none()
    if smell is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "smell_not_found", "message": f"No smell {smell_id} in job {job_id}"},
        )

    now = datetime.now(UTC)
    smell.dismissed = True
    smell.dismissed_at = now
    smell.dismissed_by = body.dismissed_by
    smell.dismissed_reason = body.reason
    await db.flush()

    # Invalidate all smell caches for this job since dismissal changes summary + lists.
    await cache_invalidate(f"alm:smells:*:{job_id}:*")
    await cache_invalidate(f"alm:smells:summary:{job_id}")

    return SmellDismissResponse(
        smell_id=smell.id,
        dismissed=True,
        dismissed_at=now,
        dismissed_by=body.dismissed_by,
        reason=body.reason,
    )
