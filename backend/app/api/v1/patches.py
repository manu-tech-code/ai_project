"""
Patches endpoints — list, detail, apply, revert, and ZIP export.

GET  /patches/{job_id}                    — list patches (filterable)
GET  /patches/{job_id}/export             — export as ZIP archive
GET  /patches/{job_id}/{patch_id}         — single patch with full diff
POST /patches/{job_id}/{patch_id}/apply   — mark patch as applied
POST /patches/{job_id}/{patch_id}/revert  — mark patch as reverted
"""

import asyncio
import io
import zipfile
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.cache import cache_get, cache_invalidate, cache_set
from app.models.job import Job
from app.models.patch import Patch, ValidationResult
from app.schemas.job import PaginationMeta
from app.schemas.patch import (
    ApplyPatchRequest,
    ApplyPatchResponse,
    GeneratePatchesRequest,
    GeneratePatchesResponse,
    PatchDetailResponse,
    PatchListResponse,
    PatchSummaryResponse,
    RevertPatchRequest,
    RevertPatchResponse,
)
from app.models.vcs import VCSProvider
from app.schemas.vcs import VCSPushRequest, VCSPushResponse
from app.services import vcs as _vcs

router = APIRouter()

# TTL for completed-job patch data — immutable once job completes.
_PATCH_TTL = 300  # 5 minutes
# TTL when patches can still change status (apply/revert by users).
_PATCH_ACTIVE_TTL = 30


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


async def _batch_get_validation_passed(patch_ids: list[UUID], db: AsyncSession) -> dict[UUID, bool | None]:
    """
    Fetch the latest validation result for each patch ID in a single query.

    Returns a dict mapping patch_id -> passed (bool) or None if not validated.
    This avoids the N+1 pattern in list_patches.
    """
    if not patch_ids:
        return {}

    # Fetch the most recent ValidationResult.passed per patch_id using a
    # DISTINCT ON (patch_id) ordered by created_at DESC.
    # SQLAlchemy 2.0 doesn't expose DISTINCT ON directly, so we use a
    # correlated subquery approach: select all, then pick max(created_at) per patch.
    from sqlalchemy import and_  # noqa: PLC0415

    # Subquery: latest created_at per patch_id.
    latest_subq = (
        select(
            ValidationResult.patch_id,
            func.max(ValidationResult.created_at).label("max_created_at"),
        )
        .where(ValidationResult.patch_id.in_(patch_ids))
        .group_by(ValidationResult.patch_id)
        .subquery()
    )

    rows_result = await db.execute(
        select(ValidationResult.patch_id, ValidationResult.passed)
        .join(
            latest_subq,
            and_(
                ValidationResult.patch_id == latest_subq.c.patch_id,
                ValidationResult.created_at == latest_subq.c.max_created_at,
            ),
        )
    )
    return {row.patch_id: row.passed for row in rows_result.all()}


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
        prompt=patch.prompt,
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


# NOTE: /{job_id}/generate must be registered BEFORE /{job_id} to avoid routing conflict.
@router.post("/{job_id}/generate", response_model=GeneratePatchesResponse)
async def generate_patches(
    job_id: UUID,
    body: GeneratePatchesRequest = Body(default_factory=GeneratePatchesRequest),
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> GeneratePatchesResponse:
    """Trigger on-demand patch generation for a completed job."""
    from app.agents.transformer import TransformerAgent  # noqa: PLC0415
    from app.agents.base import JobContext  # noqa: PLC0415
    from app.services.llm.base import get_llm_provider  # noqa: PLC0415
    from app.core.config import get_settings  # noqa: PLC0415

    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, detail={"error": "job_not_found"})
    if job.status != "complete":
        raise HTTPException(
            409,
            detail={
                "error": "job_not_complete",
                "message": "Job must be complete before generating patches.",
            },
        )
    if not job.repo_path:
        raise HTTPException(
            409,
            detail={
                "error": "repo_path_missing",
                "message": "No repo path stored for this job.",
            },
        )

    repo = Path(job.repo_path)
    if not repo.exists():
        raise HTTPException(
            409,
            detail={
                "error": "repo_path_not_found",
                "message": "The extracted repository directory no longer exists on disk.",
            },
        )

    settings = get_settings()
    ctx = JobContext(
        job_id=job.id,
        repo_path=repo,
        db_session=db,
        job_config=job.config or {},
        llm_provider=get_llm_provider(settings),
    )
    ctx.languages = job.languages or []

    result = await TransformerAgent().run(ctx, task_ids=body.task_ids)

    count_result = await db.execute(
        select(func.count()).select_from(Patch).where(Patch.job_id == job_id)
    )
    job.patch_count = count_result.scalar_one()
    job.updated_at = datetime.now(UTC)
    await db.commit()

    await cache_invalidate(f"alm:patches:list:{job_id}:*")
    await cache_invalidate("alm:jobs:*")

    return GeneratePatchesResponse(**result)


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

    job = await _get_job_or_404(job_id, db)

    cache_key = (
        f"alm:patches:list:{job_id}:p{page}:ps{page_size}"
        f":s{patch_status or ''}:l{language or ''}:t{task_id or ''}"
    )
    cached = await cache_get(cache_key)
    if cached:
        return PatchListResponse(**cached)

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

    # Batch-load validation results for all patches on this page (no N+1).
    patch_ids = [p.id for p in patches]
    validation_map = await _batch_get_validation_passed(patch_ids, db)

    summaries = [
        _patch_to_summary(patch, validation_map.get(patch.id))
        for patch in patches
    ]

    response = PatchListResponse(
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

    # Cache for completed jobs; shorter TTL for active jobs where apply/revert can occur.
    ttl = _PATCH_TTL if job.status == "complete" else _PATCH_ACTIVE_TTL
    await cache_set(cache_key, response.model_dump(), ttl=ttl)
    return response


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

    # Invalidate patch list caches for this job since status changed.
    await cache_invalidate(f"alm:patches:list:{job_id}:*")

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

    # Invalidate patch list caches for this job since status changed.
    await cache_invalidate(f"alm:patches:list:{job_id}:*")

    return RevertPatchResponse(
        patch_id=patch.id,
        status="reverted",
        reverted_at=now,
        reason=body.reason,
    )


@router.post("/{job_id}/push", response_model=VCSPushResponse)
async def push_patches(
    job_id: UUID,
    body: VCSPushRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> VCSPushResponse:
    """Push generated patches to the repository as a new branch.

    Clones the repo, writes patched_content for each selected patch,
    commits, pushes, and optionally creates a PR.
    """
    # Fetch job.
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    if not job.repo_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "no_repo_url",
                "message": "This job was not created from a git URL. Cannot push patches.",
            },
        )

    # Resolve credentials — body > job's stored provider.
    token = body.token
    provider_name = "github"
    username = None

    provider_id_to_lookup = body.provider_id or job.vcs_provider_id
    if provider_id_to_lookup:
        prov_result = await db.execute(select(VCSProvider).where(VCSProvider.id == provider_id_to_lookup))
        vcs_prov = prov_result.scalar_one_or_none()
        if vcs_prov:
            token = token or vcs_prov.token
            provider_name = vcs_prov.provider
            username = vcs_prov.username

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "no_token",
                "message": "No authentication token. Provide provider_id or token.",
            },
        )

    # Fetch patches to push.
    patch_query = select(Patch).where(Patch.job_id == job_id)
    if body.patch_ids:
        patch_query = patch_query.where(
            Patch.id.in_(body.patch_ids),
            Patch.status.in_(["pending", "applied"]),  # exclude reverted/failed
        )
    else:
        patch_query = patch_query.where(Patch.status == "pending")
    patches_result = await db.execute(patch_query)
    patches = list(patches_result.scalars().all())

    if not patches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "no_patches", "message": "No patches to push."},
        )

    branch_name = body.branch_name or f"alm/fixes-{str(job_id)[:8]}"
    commit_message = (
        f"ALM: Apply {len(patches)} refactor patches\n\n"
        f"Generated by ALM Platform\nJob: {job_id}\n"
    )

    try:
        loop = asyncio.get_running_loop()
        committed = await loop.run_in_executor(
            None,
            lambda: _vcs.push_patches_to_repo(
                repo_url=job.repo_url,
                token=token,
                provider=provider_name,
                username=username,
                patches=patches,
                branch_name=branch_name,
                commit_message=commit_message,
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "push_failed", "message": str(exc)},
        ) from exc

    # Optionally create a PR (GitHub only).
    pr_url = None
    if body.create_pr and provider_name == "github":
        base_branch = job.repo_branch or "main"
        pr_url = await _vcs.create_github_pr(
            repo_url=job.repo_url,
            token=token,
            base_branch=base_branch,
            head_branch=branch_name,
            title=f"ALM: {len(patches)} refactor patches",
            body=f"Automated refactor patches generated by ALM Platform.\n\nJob ID: `{job_id}`",
        )

    # Persist fix_branch and fix_pr_url on the job.
    job.fix_branch = branch_name
    job.fix_pr_url = pr_url
    job.updated_at = datetime.now(UTC)
    await db.flush()
    await cache_invalidate("alm:jobs:*")

    return VCSPushResponse(
        branch=branch_name,
        commits=1,
        patches_applied=committed,
        pr_url=pr_url,
        message=(
            f"Pushed {committed} file(s) to branch '{branch_name}'."
            + (f" PR: {pr_url}" if pr_url else "")
        ),
    )
