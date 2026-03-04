"""
Analysis orchestration service.

Coordinates the full agent pipeline for a single job:
  1. LanguageDetector — identify programming languages in the repo
  2. Mapper (UCG Builder) — parse source files and build the Universal Code Graph
  3. SmellDetector — detect architectural smells using rules + LLM
  4. Planner — generate a prioritized refactor plan via LLM
  5. Transformer — generate code patches for automated tasks via LLM
  6. Validator — sandbox-validate each generated patch
  7. Learner — create and store vector embeddings for similarity search

Each agent stage updates the job status in the database. If any stage fails
the job is marked FAILED with the error message and stage captured.
"""

import asyncio
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.job import Job

logger = get_logger(__name__)

# Pipeline stage names map to Job.current_stage values.
_STAGE_DETECTING = "detecting"
_STAGE_MAPPING = "mapping"
_STAGE_ANALYZING = "analyzing"
_STAGE_PLANNING = "planning"
_STAGE_TRANSFORMING = "transforming"
_STAGE_VALIDATING = "validating"


class AnalysisService:
    """
    Orchestrates the ALM analysis pipeline for a single job.

    Each public method corresponds to one pipeline stage. The ``run`` method
    executes all stages sequentially, updating job status and handling errors.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self, job_id: UUID, repo_path: str, db: AsyncSession | None = None) -> None:
        """
        Execute the full agent pipeline for a job.

        Args:
            job_id: The UUID of the job to process.
            repo_path: Path to the extracted repository on the local filesystem.
            db: Optional override for the database session (defaults to self._db).
        """
        session = db or self._db
        repo = Path(repo_path)

        job = await self._get_job(job_id, session)
        if job is None:
            logger.error("Job not found, aborting pipeline", extra={"job_id": str(job_id)})
            return

        try:
            # Stage 1: Language detection.
            await self._update_status(job, _STAGE_DETECTING, "detecting", session)
            language_info = await self._run_language_detector(job, repo, session)

            # Stage 2: UCG construction.
            await self._update_status(job, _STAGE_MAPPING, "mapping", session)
            await self._run_mapper(job, repo, language_info, session)

            # Stage 3: Smell detection.
            await self._update_status(job, _STAGE_ANALYZING, "analyzing", session)
            await self._run_smell_detector(job, session)

            # Stage 4: Refactor planning.
            await self._update_status(job, _STAGE_PLANNING, "planning", session)
            await self._run_planner(job, session)

            # Stage 5: Patch generation.
            await self._update_status(job, _STAGE_TRANSFORMING, "transforming", session)
            await self._run_transformer(job, session)

            # Stage 6: Patch validation.
            await self._update_status(job, _STAGE_VALIDATING, "validating", session)
            await self._run_validator(job, session)

            # Stage 7: Embedding and learning (best effort — non-critical).
            try:
                await self._run_learner(job, session)
            except Exception as exc:
                logger.warning(
                    "Learner stage failed (non-critical)",
                    extra={"job_id": str(job_id), "error": str(exc)},
                )

            # Mark job as complete.
            job.status = "complete"
            job.current_stage = None
            job.completed_at = datetime.now(UTC)
            job.updated_at = datetime.now(UTC)
            await session.flush()

            logger.info(
                "Job completed successfully",
                extra={
                    "job_id": str(job_id),
                    "duration_seconds": job.duration_seconds(),
                    "smell_count": job.smell_count,
                    "patch_count": job.patch_count,
                },
            )

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(
                "Job failed",
                extra={
                    "job_id": str(job_id),
                    "stage": job.current_stage,
                    "error": str(exc),
                    "traceback": tb,
                },
            )
            job.status = "failed"
            job.error_message = str(exc)
            job.error_stage = job.current_stage
            job.updated_at = datetime.now(UTC)
            try:
                await session.flush()
            except Exception:
                pass

    async def create_job(
        self,
        archive_path: Path,
        label: str | None = None,
        config: dict | None = None,
    ) -> UUID:
        """
        Create a new job record and return the job_id.

        In production the archive would be copied to a persistent storage
        location before being extracted. Here we create the DB record and
        return the ID so the caller can start the pipeline.
        """
        job_id = uuid.uuid4()
        job = Job(
            id=job_id,
            label=label,
            status="pending",
            archive_filename=archive_path.name,
            archive_size_bytes=archive_path.stat().st_size if archive_path.exists() else None,
            languages=[],
            config=config or {},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._db.add(job)
        await self._db.flush()
        logger.info("Job created", extra={"job_id": str(job_id)})
        return job_id

    async def get_job(self, job_id: UUID) -> dict:
        """Fetch job details from the DB as a plain dict."""
        job = await self._get_job(job_id, self._db)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        return {
            "job_id": str(job.id),
            "status": job.status,
            "label": job.label,
            "current_stage": job.current_stage,
            "languages": job.languages,
            "file_count": job.file_count,
            "total_lines": job.total_lines,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    async def cancel_job(self, job_id: UUID) -> None:
        """Cancel a PENDING job by updating its status to 'cancelled'."""
        job = await self._get_job(job_id, self._db)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        if job.status != "pending":
            raise ValueError(f"Only pending jobs can be cancelled (current: {job.status})")
        job.status = "cancelled"
        job.updated_at = datetime.now(UTC)
        await self._db.flush()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_job(self, job_id: UUID, session: AsyncSession) -> Job | None:
        result = await session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def _update_status(
        self, job: Job, stage: str, status_value: str, session: AsyncSession
    ) -> None:
        """Update job status and current_stage, flush to DB."""
        if job.status == "cancelled":
            raise asyncio.CancelledError("Job was cancelled")
        job.status = status_value
        job.current_stage = stage
        job.updated_at = datetime.now(UTC)
        if job.started_at is None:
            job.started_at = datetime.now(UTC)
        await session.flush()
        logger.info(
            f"Job stage: {stage}",
            extra={"job_id": str(job.id), "status": status_value},
        )

    # ------------------------------------------------------------------
    # Agent dispatch methods
    # Each method imports and runs the corresponding agent.
    # Agents may not yet be fully implemented; we handle ImportError/
    # NotImplementedError gracefully and log a warning.
    # ------------------------------------------------------------------

    async def _run_language_detector(
        self, job: Job, repo: Path, session: AsyncSession
    ) -> list[dict]:
        """Run the LanguageDetector agent and update job.languages."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.language_detector import LanguageDetector  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=repo,
                db_session=session,
                job_config=job.config or {},
            )
            detector = LanguageDetector()
            language_info = await detector.run(ctx, session)

            # Update job metadata.
            job.languages = [li["language"] for li in language_info] if language_info else []
            total_files = sum(li.get("file_count", 0) for li in (language_info or []))
            total_lines = sum(li.get("total_lines", 0) for li in (language_info or []))
            job.file_count = total_files if total_files > 0 else None
            job.total_lines = total_lines if total_lines > 0 else None
            job.updated_at = datetime.now(UTC)
            await session.flush()

            return language_info or []

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"LanguageDetector unavailable: {exc} — falling back to file scan",
                extra={"job_id": str(job.id)},
            )
            return await self._detect_languages_fallback(job, repo, session)

    async def _detect_languages_fallback(
        self, job: Job, repo: Path, session: AsyncSession
    ) -> list[dict]:
        """
        Simple language detection fallback using file extensions.

        Used when the LanguageDetector agent is not available.
        """
        _ext_to_lang = {
            ".java": "java",
            ".py": "python",
            ".php": "php",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
        }
        lang_counts: dict[str, int] = {}
        total_files = 0
        total_lines = 0

        try:
            for path in repo.rglob("*"):
                if not path.is_file():
                    continue
                # Skip hidden/vendor/test directories.
                parts = path.parts
                if any(p.startswith(".") or p in ("vendor", "node_modules", "__pycache__") for p in parts):
                    continue
                ext = path.suffix.lower()
                lang = _ext_to_lang.get(ext)
                if lang:
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                    total_files += 1
                    try:
                        lines = path.read_text(errors="ignore").count("\n")
                        total_lines += lines
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"Language fallback scan failed: {exc}", extra={"job_id": str(job.id)})

        job.languages = list(lang_counts.keys())
        job.file_count = total_files if total_files > 0 else None
        job.total_lines = total_lines if total_lines > 0 else None
        job.updated_at = datetime.now(UTC)
        await session.flush()

        return [{"language": lang, "file_count": count, "total_lines": 0} for lang, count in lang_counts.items()]

    async def _run_mapper(
        self, job: Job, repo: Path, language_info: list[dict], session: AsyncSession
    ) -> None:
        """Run the Mapper (UCG Builder) agent to construct the code graph."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.mapper import Mapper  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=repo,
                db_session=session,
                job_config=job.config or {},
            )
            ctx.languages = [li["language"] for li in language_info]
            mapper = Mapper()
            ucg_stats = await mapper.run(ctx, session)

            if ucg_stats:
                job.ucg_node_count = ucg_stats.get("node_count", 0)
                job.ucg_edge_count = ucg_stats.get("edge_count", 0)
                job.updated_at = datetime.now(UTC)
                await session.flush()

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"Mapper unavailable: {exc} — skipping UCG construction",
                extra={"job_id": str(job.id)},
            )

    async def _run_smell_detector(self, job: Job, session: AsyncSession) -> None:
        """Run the SmellDetector agent to identify architectural smells."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.smell_detector import SmellDetector  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=Path("/tmp"),  # not needed at this stage
                db_session=session,
                job_config=job.config or {},
            )
            ctx.languages = job.languages or []
            detector = SmellDetector()
            smell_results = await detector.run(ctx, session)
            smell_count = len(smell_results) if smell_results else 0
            job.smell_count = smell_count
            job.updated_at = datetime.now(UTC)
            await session.flush()

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"SmellDetector unavailable: {exc}",
                extra={"job_id": str(job.id)},
            )

    async def _run_planner(self, job: Job, session: AsyncSession) -> None:
        """Run the Planner agent to generate a prioritized refactor plan."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.planner import Planner  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=Path("/tmp"),
                db_session=session,
                job_config=job.config or {},
            )
            ctx.languages = job.languages or []
            planner = Planner()
            await planner.run(ctx, session)

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"Planner unavailable: {exc}",
                extra={"job_id": str(job.id)},
            )

    async def _run_transformer(self, job: Job, session: AsyncSession) -> None:
        """Run the Transformer agent to generate code patches."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.transformer import Transformer  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=Path("/tmp"),
                db_session=session,
                job_config=job.config or {},
            )
            ctx.languages = job.languages or []
            transformer = Transformer()
            patches = await transformer.run(ctx, session)
            patch_count = len(patches) if patches else 0
            job.patch_count = patch_count
            job.updated_at = datetime.now(UTC)
            await session.flush()

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"Transformer unavailable: {exc}",
                extra={"job_id": str(job.id)},
            )

    async def _run_validator(self, job: Job, session: AsyncSession) -> None:
        """Run the Validator agent to sandbox-validate each patch."""
        try:
            from app.agents.base import JobContext  # noqa: PLC0415
            from app.agents.validator import Validator  # noqa: PLC0415

            ctx = JobContext(
                job_id=job.id,
                repo_path=Path("/tmp"),
                db_session=session,
                job_config=job.config or {},
            )
            ctx.languages = job.languages or []
            validator = Validator()
            await validator.run(ctx, session)

        except (ImportError, NotImplementedError, AttributeError) as exc:
            logger.warning(
                f"Validator unavailable: {exc}",
                extra={"job_id": str(job.id)},
            )

    async def _run_learner(self, job: Job, session: AsyncSession) -> None:
        """Run the Learner agent to store vector embeddings (non-critical)."""
        from app.agents.base import JobContext  # noqa: PLC0415
        from app.agents.learner import Learner  # noqa: PLC0415

        ctx = JobContext(
            job_id=job.id,
            repo_path=Path("/tmp"),
            db_session=session,
            job_config=job.config or {},
        )
        ctx.languages = job.languages or []
        learner = Learner()
        await learner.run(ctx, session)
