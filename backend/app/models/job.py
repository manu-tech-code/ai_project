"""
SQLAlchemy ORM models for the jobs and reports tables.

See docs/db-schema.md section 3 for the full DDL.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Job(Base):
    """
    Central tracking record for each ALM analysis job.

    Tracks the full lifecycle from archive submission through pipeline completion,
    including per-stage progress, error state, and summary statistics.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    current_stage: Mapped[str | None] = mapped_column(Text)

    # Archive metadata — populated when the upload is received.
    archive_filename: Mapped[str | None] = mapped_column(Text)
    archive_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    archive_checksum: Mapped[str | None] = mapped_column(Text)  # SHA-256

    # Extracted code metadata — populated by LanguageDetector agent.
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    file_count: Mapped[int | None] = mapped_column(Integer)
    total_lines: Mapped[int | None] = mapped_column(Integer)

    # User-supplied configuration overrides.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # UCG summary — populated by Mapper agent.
    ucg_node_count: Mapped[int | None] = mapped_column(Integer)
    ucg_edge_count: Mapped[int | None] = mapped_column(Integer)

    # Analysis summary — populated by SmellDetector and Transformer agents.
    smell_count: Mapped[int | None] = mapped_column(Integer)
    patch_count: Mapped[int | None] = mapped_column(Integer)

    # Error tracking.
    error_message: Mapped[str | None] = mapped_column(Text)
    error_stage: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships.
    ucg_nodes: Mapped[list["UCGNode"]] = relationship(  # noqa: F821
        "UCGNode", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    ucg_edges: Mapped[list["UCGEdge"]] = relationship(  # noqa: F821
        "UCGEdge", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    smells: Mapped[list["Smell"]] = relationship(  # noqa: F821
        "Smell", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    plans: Mapped[list["Plan"]] = relationship(  # noqa: F821
        "Plan", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    patches: Mapped[list["Patch"]] = relationship(  # noqa: F821
        "Patch", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    report: Mapped["Report | None"] = relationship(  # noqa: F821
        "Report", back_populates="job", cascade="all, delete-orphan", lazy="select",
        uselist=False,
    )

    def duration_seconds(self) -> float | None:
        """Return elapsed seconds between started_at and completed_at."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def stage_progress(self) -> dict[str, str]:
        """
        Return a dict mapping each pipeline stage to its state.

        States: 'complete' | 'running' | 'pending' | 'failed'
        """
        stages = ["detecting", "mapping", "analyzing", "planning", "transforming", "validating"]
        stage_order = {s: i for i, s in enumerate(stages)}

        current = self.current_stage or ""
        current_idx = stage_order.get(current, -1)

        progress: dict[str, str] = {}
        for stage in stages:
            idx = stage_order[stage]
            if self.status == "failed" and stage == current:
                progress[stage] = "failed"
            elif idx < current_idx or self.status in ("complete",):
                progress[stage] = "complete"
            elif idx == current_idx:
                progress[stage] = "running"
            else:
                progress[stage] = "pending"

        return progress


# Type annotations for relationships (resolved lazily by SQLAlchemy).
# These string literals are evaluated at mapper configuration time, not import time.
# No bottom-of-file imports needed here.


class Report(Base):
    """
    Cached modernization report data for a completed job.

    Full report content is generated on-demand and cached here for fast retrieval.
    One report per job (enforced by unique constraint on job_id).
    """

    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("job_id", name="uq_reports_job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Full report content cached as JSON and Markdown.
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    report_markdown: Mapped[str | None] = mapped_column(Text)

    # Denormalized summary statistics for fast list queries.
    modernization_score: Mapped[int | None] = mapped_column(Integer)
    total_smells: Mapped[int | None] = mapped_column(Integer)
    critical_smells: Mapped[int | None] = mapped_column(Integer)
    patches_generated: Mapped[int | None] = mapped_column(Integer)
    patches_passed: Mapped[int | None] = mapped_column(Integer)
    estimated_hours: Mapped[float | None] = mapped_column(Float)

    # Relationships.
    job: Mapped["Job"] = relationship("Job", back_populates="report")
