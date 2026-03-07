"""SQLAlchemy ORM model for the job_logs table."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobLog(Base):
    """
    Stores per-sub-step progress log entries emitted by pipeline agents.

    One row per emit_progress() call. seq is monotonically increasing per job
    and is computed at insert time using COALESCE(MAX(seq), 0) + 1.
    """

    __tablename__ = "job_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("job_id", "seq", name="uq_job_logs_job_id_seq"),
        Index("ix_job_logs_job_id_seq", "job_id", "seq"),
    )


async def insert_job_log(
    db,
    job_id: uuid.UUID,
    stage: str,
    message: str,
    percent: int = 0,
) -> JobLog:
    """Insert a log entry with auto-incrementing seq per job."""
    seq_result = await db.execute(
        select(func.coalesce(func.max(JobLog.seq), 0) + 1).where(
            JobLog.job_id == job_id
        )
    )
    next_seq = seq_result.scalar_one()

    log = JobLog(
        id=uuid.uuid4(),
        job_id=job_id,
        seq=next_seq,
        stage=stage,
        message=message,
        percent=percent,
        created_at=datetime.now(UTC),
    )
    db.add(log)
    return log
