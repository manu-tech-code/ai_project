"""
Patches endpoints — list, detail, apply, revert, and ZIP export.

GET  /patches/{job_id}                    — list patches (filterable)
GET  /patches/{job_id}/export             — export as ZIP archive
GET  /patches/{job_id}/{patch_id}         — single patch with full diff
POST /patches/{job_id}/{patch_id}/apply   — mark patch as applied
POST /patches/{job_id}/{patch_id}/revert  — mark patch as reverted
"""

import io
import zipfile
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.job import Job
from app.models.patch import Patch, ValidationResult
from app.schemas.job import PaginationMeta
from app.schemas.patch import (
    ApplyPatchRequest,
    ApplyPatchResponse,
    PatchDetailResponse,
    PatchListResponse,
    PatchSummaryResponse,
    RevertPatchRequest,
    RevertPatchResponse,
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


async def _get_patch_or_404(job_id: UUID, patch_id: UUID, db: AsyncSession) -> Patch:
    result = await db.execute(
        select(Patch).where(Patch.id == patch_id, Patch.job_id == job_id)
    )
    patch = result.scalar_one_or_none()
    if patch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "patch_not_found", "message": f"No patch {patch_id} in job {job_id}"},
        )
    return patch


async def _get_validation_passed(patch_id: UUID, db: AsyncSession) -> bool | None:
    """Return the validation result for a patch, or None if not yet validated."""
    result = await db.execute(
        select(ValidationResult.passed)
        .where(ValidationResult.patch_id == patch_id)
        .order_by(ValidationResult.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


def _patch_to_summary(patch: Patch, validation_passed: bool | None) -> PatchSummaryResponse:
    return PatchSummaryResponse(
        patch_id=patch.id,
        task_id=patch.task_id,
        file_path=patch.file_path,
        patch_type=patch.patch_type,
        language=patch.language,
        status=patch.status,
        validation_passed=validation_passed,
        tokens_used=patch.tokens_used,
        model_used=patch.model_used,
        created_at=patch.created_at,
    )


def _patch_to_detail(patch: Patch, validation_passed: bool | None) -> PatchDetailResponse:
    return PatchDetailResponse(
        patch_id=patch.id,
        task_id=patch.task_id,
        file_path=patch.file_path,
        patch_type=patch.patch_type,
        language=patch.language,
        status=patch.status,
        diff=patch.diff,
        original_content=patch.original_content,
        patched_content=patch.patched_content,
        validation_passed=validation_passed,
        tokens_used=patch.tokens_used,
        model_used=patch.model_used,
        created_at=patch.created_at,
        applied_at=patch.applied_at,
        applied_by=patch.applied_by,
        reverted_at=patch.reverted_at,
        reverted_reason=patch.reverted_reason,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


# NOTE: /export must be registered BEFORE /{patch_id} to avoid routing conflict.
@router.get("/{job_id}/export")
async def export_patches(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> StreamingResponse:
    """
    Export all pending and applied patches for a job as a ZIP archive.

    Each patch is included as a .patch file (unified diff format).
    Returns a streaming binary response with Content-Type application/zip.
    """
    await _get_job_or_404(job_id, db)

    patches_result = await db.execute(
        select(Patch).where(
            Patch.job_id == job_id,
            Patch.status.in_(["pending", "applied"]),
        ).order_by(Patch.created_at)
    )
    patches = patches_result.scalars().all()

    # Build ZIP in memory.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for patch in patches:
            # Safe filename from file path.
            safe_name = patch.file_path.replace("/", "_").replace("\\", "_")
            archive_name = f"patches/{patch.id}_{safe_name}.patch"
            zf.writestr(archive_name, patch.diff)

    buffer.seek(0)

    return StreamingResponse(
        content=iter([buffer.read()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="alm-patches-{job_id}.zip"'
        },
    )


@router.get("/{job_id}", response_model=PatchListResponse)
async def list_patches(
    job_id: UUID,
    patch_status: str | None = None,
    language: str | None = None,
    task_id: UUID | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PatchListResponse:
    """List all patches for a job with optional status, language, and task filters."""
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    await _get_job_or_404(job_id, db)

    query = select(Patch).where(Patch.job_id == job_id)
    count_query = select(func.count()).select_from(Patch).where(Patch.job_id == job_id)

    if patch_status:
        query = query.where(Patch.status == patch_status.lower())
        count_query = count_query.where(Patch.status == patch_status.lower())
    if language:
        query = query.where(Patch.language == language.lower())
        count_query = count_query.where(Patch.language == language.lower())
    if task_id:
        query = query.where(Patch.task_id == task_id)
        count_query = count_query.where(Patch.task_id == task_id)

    total_items = (await db.execute(count_query)).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    patches_result = await db.execute(
        query.order_by(Patch.created_at).offset(offset).limit(page_size)
    )
    patches = patches_result.scalars().all()

    summaries = []
    for patch in patches:
        vp = await _get_validation_passed(patch.id, db)
        summaries.append(_patch_to_summary(patch, vp))

    return PatchListResponse(
        data=summaries,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{job_id}/{patch_id}", response_model=PatchDetailResponse)
async def get_patch(
    job_id: UUID,
    patch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PatchDetailResponse:
    """Get a single patch with full diff and file contents."""
    await _get_job_or_404(job_id, db)
    patch = await _get_patch_or_404(job_id, patch_id, db)
    vp = await _get_validation_passed(patch.id, db)
    return _patch_to_detail(patch, vp)


@router.post("/{job_id}/{patch_id}/apply", response_model=ApplyPatchResponse)
async def apply_patch(
    job_id: UUID,
    patch_id: UUID,
    body: ApplyPatchRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> ApplyPatchResponse:
    """Mark a patch as applied (user confirms they applied it to their codebase)."""
    await _get_job_or_404(job_id, db)
    patch = await _get_patch_or_404(job_id, patch_id, db)

    if patch.status not in ("pending", "reverted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_status_transition",
                "message": f"Cannot apply patch with status '{patch.status}'.",
            },
        )

    now = datetime.now(UTC)
    patch.status = "applied"
    patch.applied_at = now
    patch.applied_by = body.applied_by
    patch.updated_at = now
    await db.flush()

    return ApplyPatchResponse(
        patch_id=patch.id,
        status="applied",
        applied_at=now,
        applied_by=body.applied_by,
    )


@router.post("/{job_id}/{patch_id}/revert", response_model=RevertPatchResponse)
async def revert_patch(
    job_id: UUID,
    patch_id: UUID,
    body: RevertPatchRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> RevertPatchResponse:
    """Mark a patch as reverted with a required reason string."""
    await _get_job_or_404(job_id, db)
    patch = await _get_patch_or_404(job_id, patch_id, db)

    if patch.status not in ("applied", "pending"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_status_transition",
                "message": f"Cannot revert patch with status '{patch.status}'.",
            },
        )

    now = datetime.now(UTC)
    patch.status = "reverted"
    patch.reverted_at = now
    patch.reverted_reason = body.reason
    patch.updated_at = now
    await db.flush()

    return RevertPatchResponse(
        patch_id=patch.id,
        status="reverted",
        reverted_at=now,
        reason=body.reason,
    )
