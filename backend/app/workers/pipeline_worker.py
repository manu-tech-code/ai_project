"""
Pipeline worker — consumes jobs from the alm.analyze queue and runs the full
analysis pipeline via AnalysisService.

Usage:
    python -m app.workers.pipeline_worker

Each queue message must carry a ``payload.repo_path`` so the analysis service
can locate the extracted source files on the shared volume.

If RabbitMQ is not reachable at startup the process exits with a non-zero code
so Docker/Kubernetes can restart it with back-off.
"""

import asyncio
import logging
import sys
from uuid import UUID

logger = logging.getLogger("alm.worker.pipeline")


async def _handle_message(body: dict) -> None:
    """Consume one job message and run the full analysis pipeline."""
    job_id_str = body.get("job_id")
    repo_path = body.get("payload", {}).get("repo_path", "")

    if not job_id_str:
        logger.error("Received message without job_id: %s", body)
        return

    if not repo_path:
        logger.error("Received message without repo_path for job %s", job_id_str)
        return

    job_id = UUID(job_id_str)
    logger.info("Worker processing job", extra={"job_id": job_id_str})

    from app.core.database import AsyncSessionLocal  # noqa: PLC0415
    from app.services.analysis import AnalysisService  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        service = AnalysisService(db)
        try:
            await service.run(job_id=job_id, repo_path=repo_path, db=db)
        except Exception as exc:
            logger.exception(
                "Pipeline failed",
                extra={"job_id": job_id_str, "error": str(exc)},
            )


async def main() -> None:
    from app.core.logging import configure_logging  # noqa: PLC0415

    configure_logging()

    from app.services.queue.rabbitmq import get_rabbitmq_service  # noqa: PLC0415

    logger.info("ALM pipeline worker starting")

    mq = await get_rabbitmq_service()
    if not mq._available:
        logger.error(
            "RabbitMQ is not available. Set RABBITMQ_URL and ensure RabbitMQ is running."
        )
        sys.exit(1)

    await mq.consume("analyze", _handle_message)
    logger.info("Worker listening on queue 'alm.analyze'. Press Ctrl+C to stop.")

    try:
        await asyncio.Future()  # Block forever until interrupted.
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Worker interrupted, shutting down.")
    finally:
        await mq.close()


if __name__ == "__main__":
    asyncio.run(main())
