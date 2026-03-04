"""
BaseAgent — abstract base class for all ALM pipeline agents.

Each agent receives a JobContext and writes its results to the database.
Agents are idempotent: re-running on the same job_id must not create duplicates.

Pipeline execution order:
  1. LanguageDetectorAgent
  2. MapperAgent
  3. SmellDetectorAgent
  4. PlannerAgent
  5. TransformerAgent
  6. ValidatorAgent
  7. LearnerAgent
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


class JobContext:
    """
    Shared context object passed to all agents in the pipeline.
    Not serializable — contains live DB session and service clients.
    """

    def __init__(
        self,
        job_id: UUID,
        repo_path: Path,
        db_session: AsyncSession,
        job_config: dict | None = None,
        llm_provider=None,
        settings=None,
    ) -> None:
        self.job_id = job_id
        self.repo_path = repo_path
        self.db_session = db_session
        self.job_config = job_config or {}
        self.languages: list[str] = []  # populated by LanguageDetectorAgent
        self.llm = llm_provider  # LLMProvider instance (may be None)
        self.settings = settings  # Settings instance (may be None)


class BaseAgent(ABC):
    """
    Abstract base class for all pipeline agents.

    Subclasses must implement `run(context)` and `stage_name`.
    """

    #: The job status value set when this agent starts running.
    stage_name: str = "unknown"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"alm.agents.{self.__class__.__name__}")

    @abstractmethod
    async def run(self, context: JobContext) -> dict:
        """
        Execute the agent logic.

        Args:
            context: The shared job context with DB session and metadata.

        Returns:
            A dict of agent-specific output metrics (stored in job.config or logged).

        Raises:
            AgentError: On unrecoverable failure (triggers job retry or failure).
        """

    async def _update_job_status(self, context: JobContext, status: str) -> None:
        """Update job status in the database."""
        from app.models.job import Job  # avoid circular imports

        try:
            stmt = (
                update(Job)
                .where(Job.id == context.job_id)
                .values(
                    status=status,
                    current_stage=self.stage_name,
                    updated_at=datetime.now(UTC),
                )
            )
            await context.db_session.execute(stmt)
            await context.db_session.commit()
            self.logger.info(
                "[%s] Job status updated to '%s'", context.job_id, status
            )
        except Exception as exc:
            self.logger.error(
                "[%s] Failed to update job status to '%s': %s",
                context.job_id,
                status,
                exc,
            )

    async def _on_start(self, context: JobContext) -> None:
        """Called before run(). Updates job status to this agent's stage."""
        self.logger.info(
            "[%s] Starting agent %s", context.job_id, self.__class__.__name__
        )
        await self._update_job_status(context, self.stage_name)

    async def _on_complete(self, context: JobContext, result: dict) -> None:
        """Called after successful run()."""
        self.logger.info(
            "[%s] Agent %s completed: %s",
            context.job_id,
            self.__class__.__name__,
            result,
        )

    async def execute(self, context: JobContext) -> dict:
        """Template method: lifecycle management around run()."""
        await self._on_start(context)
        result = await self.run(context)
        await self._on_complete(context, result)
        return result

    async def emit_progress(
        self, context: JobContext, message: str, percent: int = 0
    ) -> None:
        """Log agent progress. Can be extended to push to Redis pub/sub."""
        self.logger.info("[%s] %s (%d%%)", context.job_id, message, percent)


class AgentError(Exception):
    """Raised when an agent encounters an unrecoverable error."""

    def __init__(
        self, message: str, agent: str, job_id: UUID, retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.agent = agent
        self.job_id = job_id
        self.retryable = retryable
