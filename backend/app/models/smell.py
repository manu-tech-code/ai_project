"""
SQLAlchemy ORM model for the smells table.

See docs/db-schema.md section 5 for the full DDL.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Smell(Base):
    """
    An architectural smell detected by the SmellDetector agent.

    Each smell record stores the type, severity, affected node IDs, rule-based
    evidence metrics, and an optional LLM-generated rationale explaining why
    this pattern is problematic.
    """

    __tablename__ = "smells"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SmellType enum value (e.g., "god_class", "long_method").
    smell_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Severity level: 'critical' | 'high' | 'medium' | 'low'
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-readable description of the detected smell.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Combined rule+LLM confidence score (0.0 to 1.0).
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Array of UCGNode UUIDs that are affected by this smell.
    affected_node_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    # Rule-based graph metrics that triggered detection
    # (e.g., {"method_count": 47, "lines_of_code": 892, "efferent_coupling": 23}).
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # LLM-generated explanation (null when using rule-only detection).
    llm_rationale: Mapped[str | None] = mapped_column(Text)

    # Dismissal tracking — allows users to mark known/acceptable issues.
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_by: Mapped[str | None] = mapped_column(Text)
    dismissed_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships.
    job: Mapped["Job"] = relationship("Job", back_populates="smells")  # noqa: F821
