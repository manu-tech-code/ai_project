"""
Analysis endpoints — job submission, status polling, listing, and cancellation.

POST   /analyze                — submit a new job (multipart archive upload)
GET    /analyze/{job_id}       — get job status and full metadata
GET    /analyze                — list jobs (paginated, filterable by status)
DELETE /analyze/{job_id}       — cancel a pending job or delete a completed one
"""

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.job import Job
from app.schemas.job import (
    JobConfig,
    JobListResponse,
    JobResponse,
    JobSubmitResponse,
    JobSummaryResponse,
    PaginationMeta,
)

router = APIRouter()
logger = get_logger(__name__)

_ALLOWED_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/octet-stream",  # browsers sometimes send this for .tar.gz
}

_ALLOWED_EXTENSIONS = {".zip", ".tar.gz", ".tgz", ".tar"}
_MAX_FILES_IN_ARCHIVE = 50_000
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_job_response(job: Job) -> JobResponse:
    """Build a JobResponse from a Job ORM instance."""
    duration = job.duration_seconds()
    ucg_stats = None
    if job.ucg_node_count is not None:
        ucg_stats = {
            "node_count": job.ucg_node_count,
            "edge_count": job.ucg_edge_count,
        }
    return JobResponse(
        job_id=job.id,
        status=job.status,
        label=job.label,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        duration_seconds=duration,
        languages=job.languages or [],
        file_count=job.file_count,
        total_lines=job.total_lines,
        archive_size_bytes=job.archive_size_bytes,
        config=job.config or {},
        current_stage=job.current_stage,
        stage_progress=job.stage_progress(),
        error=job.error_message,
        ucg_stats=ucg_stats,
        smell_count=job.smell_count,
        patch_count=job.patch_count,
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_archive_extension(filename: str) -> None:
    """Raise HTTP 400 if the filename has an unsupported extension."""
    name_lower = filename.lower()
    if not any(name_lower.endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_archive",
                "message": f"Unsupported archive format. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
            },
        )


def _extract_archive(data: bytes, dest_dir: str) -> tuple[int, int]:
    """
    Extract the archive bytes into dest_dir.

    Returns (file_count, total_bytes) and raises HTTP 400 on invalid archive
    or HTTP 413 on archive bomb detection.
    """
    file_count = 0
    total_bytes = 0

    try:
        if data[:4] == b"PK\x03\x04" or data[:2] == b"PK":
            # ZIP archive
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = zf.infolist()
                if len(members) > _MAX_FILES_IN_ARCHIVE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": "archive_bomb", "message": "Archive contains too many files."},
                    )
                for member in members:
                    if member.file_size + total_bytes > _MAX_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "error": "archive_bomb",
                                "message": "Archive exceeds maximum uncompressed size (2 GB).",
                            },
                        )
                    total_bytes += member.file_size
                    file_count += 1
                    # Path traversal protection: reject absolute or parent-traversal paths.
                    safe_path = os.path.realpath(os.path.join(dest_dir, member.filename))
                    if not safe_path.startswith(os.path.realpath(dest_dir)):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": "invalid_archive", "message": "Path traversal detected in archive."},
                        )
                zf.extractall(dest_dir)
        else:
            # TAR archive (possibly compressed)
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                members_list = tf.getmembers()
                if len(members_list) > _MAX_FILES_IN_ARCHIVE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": "archive_bomb", "message": "Archive contains too many files."},
                    )
                for member in members_list:
                    total_bytes += member.size
                    if total_bytes > _MAX_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "error": "archive_bomb",
                                "message": "Archive exceeds maximum uncompressed size (2 GB).",
                            },
                        )
                    if member.isfile():
                        file_count += 1
                    safe_path = os.path.realpath(os.path.join(dest_dir, member.name))
                    if not safe_path.startswith(os.path.realpath(dest_dir)):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": "invalid_archive", "message": "Path traversal detected in archive."},
                        )
                tf.extractall(dest_dir)

    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_archive", "message": f"Corrupted or invalid archive: {exc}"},
        ) from exc

    return file_count, total_bytes


async def _run_analysis_pipeline(job_id: uuid.UUID, repo_path: str) -> None:
    """
    Background task that runs the full analysis pipeline for a job.

    Imports the AnalysisService and runs it. Errors are caught and written
    back to the job record as status=failed.
    """
    from app.core.database import AsyncSessionLocal  # noqa: PLC0415
    from app.services.analysis import AnalysisService  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        service = AnalysisService(db)
        try:
            await service.run(job_id=job_id, repo_path=repo_path, db=db)
        except Exception as exc:
            logger.exception("Analysis pipeline failed", extra={"job_id": str(job_id), "error": str(exc)})


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobSubmitResponse)
async def submit_job(
    background_tasks: BackgroundTasks,
    archive: UploadFile = File(..., description="Source code archive (.zip, .tar.gz, .tgz)"),
    label: str | None = Form(None),
    config: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> JobSubmitResponse:
    """
    Submit a new analysis job by uploading a source code archive.

    The archive is extracted to a temporary directory and an analysis pipeline
    is started as a background task. Returns immediately with job_id and
    polling links.
    """
    settings = get_settings()

    # Validate archive extension.
    filename = archive.filename or "upload"
    _validate_archive_extension(filename)

    # Read archive content.
    content = await archive.read()
    archive_size = len(content)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if archive_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "archive_too_large",
                "message": f"Archive exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
            },
        )

    checksum = _sha256_bytes(content)

    # Parse optional config JSON.
    job_config: dict = {}
    if config:
        try:
            raw = json.loads(config)
            validated = JobConfig(**raw)
            job_config = validated.model_dump()
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "invalid_config", "message": str(exc)},
            ) from exc

    # Extract archive to a persistent temp directory (pipeline reads from here).
    extract_dir = tempfile.mkdtemp(prefix="alm_job_")
    try:
        file_count, _ = _extract_archive(content, extract_dir)
    except HTTPException:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise

    # Create the job record in the database.
    job = Job(
        id=uuid.uuid4(),
        label=label,
        status="pending",
        archive_filename=filename,
        archive_size_bytes=archive_size,
        archive_checksum=checksum,
        languages=[],
        config=job_config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    job_id = job.id

    logger.info(
        "Job created",
        extra={"job_id": str(job_id), "archive": filename, "size_bytes": archive_size},
    )

    # Start the analysis pipeline as a background task.
    background_tasks.add_task(_run_analysis_pipeline, job_id, extract_dir)

    base_url = "/api/v1"
    return JobSubmitResponse(
        job_id=job_id,
        status="pending",
        label=label,
        created_at=job.created_at,
        estimated_duration_seconds=300,
        links={
            "self": f"{base_url}/analyze/{job_id}",
            "graph": f"{base_url}/graph/{job_id}",
            "report": f"{base_url}/report/{job_id}",
        },
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> JobResponse:
    """Get full job status and metadata by job ID."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "message": f"No job found with ID {job_id}"},
        )
    return _build_job_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    job_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> JobListResponse:
    """List all analysis jobs with optional status filter (paginated)."""
    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    # Build query with optional status filter.
    base_query = select(Job).order_by(Job.created_at.desc())
    count_query = select(func.count()).select_from(Job)

    if job_status:
        base_query = base_query.where(Job.status == job_status)
        count_query = count_query.where(Job.status == job_status)

    total_items_result = await db.execute(count_query)
    total_items = total_items_result.scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    jobs_result = await db.execute(base_query.offset(offset).limit(page_size))
    jobs = jobs_result.scalars().all()

    summaries = []
    for job in jobs:
        summaries.append(
            JobSummaryResponse(
                job_id=job.id,
                status=job.status,
                label=job.label,
                created_at=job.created_at,
                completed_at=job.completed_at,
                duration_seconds=job.duration_seconds(),
                languages=job.languages or [],
                file_count=job.file_count,
                smell_count=job.smell_count,
                patch_count=job.patch_count,
            )
        )

    return JobListResponse(
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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> None:
    """
    Cancel a pending job or delete a completed one.

    Running jobs (status=detecting/mapping/analyzing/planning/transforming/validating)
    cannot be deleted. Returns 204 No Content on success.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "message": f"No job found with ID {job_id}"},
        )

    _running_statuses = {"detecting", "mapping", "analyzing", "planning", "transforming", "validating"}
    if job.status in _running_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "job_running",
                "message": f"Job {job_id} is currently running (status={job.status}) and cannot be deleted.",
            },
        )

    if job.status == "pending":
        job.status = "cancelled"
        job.updated_at = datetime.now(UTC)
        await db.flush()
        logger.info("Job cancelled", extra={"job_id": str(job_id)})
    else:
        # Completed, failed, cancelled — delete the record (cascades to all related rows).
        await db.delete(job)
        await db.flush()
        logger.info("Job deleted", extra={"job_id": str(job_id)})
