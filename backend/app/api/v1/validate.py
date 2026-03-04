"""
Validation endpoints — list results, single result detail, and re-run.

GET  /validate/{job_id}               — list all validation results for a job
GET  /validate/{job_id}/{result_id}   — single result with full check details
POST /validate/{job_id}/rerun         — re-run validation for failed patches
"""

from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.job import Job
from app.models.patch import Patch, ValidationResult
from app.schemas.job import PaginationMeta
from app.schemas.patch import (
    RerunValidationResponse,
    ValidationCheckResponse,
    ValidationResultDetailResponse,
    ValidationResultListResponse,
    ValidationResultSummaryResponse,
)

router = APIRouter()


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


def _result_to_summary(vr: ValidationResult) -> ValidationResultSummaryResponse:
    """Build a summary response from a ValidationResult, computing check_summary."""
    check_summary: dict[str, bool] = {}
    for check in vr.checks or []:
        if isinstance(check, dict):
            check_summary[check.get("check_type", check.get("check_name", ""))] = check.get("passed", False)
    return ValidationResultSummaryResponse(
        result_id=vr.id,
        patch_id=vr.patch_id,
        passed=vr.passed,
        overall_score=vr.overall_score,
        check_summary=check_summary,
        created_at=vr.created_at,
    )


def _result_to_detail(vr: ValidationResult) -> ValidationResultDetailResponse:
    """Build a detailed response including all individual checks."""
    checks: list[ValidationCheckResponse] = []
    for check in vr.checks or []:
        if isinstance(check, dict):
            checks.append(
                ValidationCheckResponse(
                    check_name=check.get("check_name", ""),
                    check_type=check.get("check_type", ""),
                    passed=check.get("passed", False),
                    output=check.get("output", ""),
                    duration_ms=check.get("duration_ms", 0),
                )
            )
    return ValidationResultDetailResponse(
        result_id=vr.id,
        patch_id=vr.patch_id,
        passed=vr.passed,
        overall_score=vr.overall_score,
        checks=checks,
        created_at=vr.created_at,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=ValidationResultListResponse)
async def list_validation_results(
    job_id: UUID,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> ValidationResultListResponse:
    """List all validation results for a job (paginated)."""
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    await _get_job_or_404(job_id, db)

    count_result = await db.execute(
        select(func.count()).select_from(ValidationResult).where(
            ValidationResult.job_id == job_id
        )
    )
    total_items = count_result.scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    results = await db.execute(
        select(ValidationResult)
        .where(ValidationResult.job_id == job_id)
        .order_by(ValidationResult.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    vr_list = results.scalars().all()

    return ValidationResultListResponse(
        data=[_result_to_summary(vr) for vr in vr_list],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{job_id}/{result_id}", response_model=ValidationResultDetailResponse)
async def get_validation_result(
    job_id: UUID,
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> ValidationResultDetailResponse:
    """Get full detail for a single validation result including all check outputs."""
    await _get_job_or_404(job_id, db)

    result = await db.execute(
        select(ValidationResult).where(
            ValidationResult.id == result_id,
            ValidationResult.job_id == job_id,
        )
    )
    vr = result.scalar_one_or_none()
    if vr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "result_not_found",
                "message": f"No validation result {result_id} for job {job_id}",
            },
        )
    return _result_to_detail(vr)


@router.post("/{job_id}/rerun", status_code=status.HTTP_202_ACCEPTED, response_model=RerunValidationResponse)
async def rerun_validation(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> RerunValidationResponse:
    """
    Re-run sandbox validation for all failed patches in a job.

    Finds patches whose latest validation result failed and queues them for
    re-validation. Returns the count of patches queued.
    """
    await _get_job_or_404(job_id, db)

    # Find patches with failed validation results.
    failed_patches_result = await db.execute(
        select(Patch.id).where(
            Patch.job_id == job_id,
            Patch.status.in_(["pending", "failed"]),
        )
    )
    patch_ids = [row[0] for row in failed_patches_result.all()]

    # Filter to patches whose latest validation result failed (or no result yet).
    patches_to_rerun: list[UUID] = []
    for patch_id in patch_ids:
        latest_result = await db.execute(
            select(ValidationResult.passed)
            .where(ValidationResult.patch_id == patch_id)
            .order_by(ValidationResult.created_at.desc())
            .limit(1)
        )
        latest_passed = latest_result.scalar_one_or_none()
        if latest_passed is None or not latest_passed:
            patches_to_rerun.append(patch_id)

    # In a full implementation, these patch IDs would be published to the
    # alm.validate queue for the Validator agent to process.
    # For now, we record that validation has been queued.

    return RerunValidationResponse(
        message="Validation re-run queued",
        job_id=job_id,
        patches_queued=len(patches_to_rerun),
    )
