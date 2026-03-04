"""
SQLAlchemy ORM models for ucg_nodes, ucg_edges, and embeddings tables.

See docs/db-schema.md sections 4 and 6 for the full DDL and column semantics.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# pgvector type — provides native vector(1536) column support.
# Falls back gracefully if the extension is not installed in the test environment.
try:
    from pgvector.sqlalchemy import Vector

    _VECTOR_COLUMN = Vector(1536)
    _HAS_PGVECTOR = True
except ImportError:
    from sqlalchemy import JSON as _VECTOR_COLUMN  # type: ignore[assignment]
    _HAS_PGVECTOR = False


class UCGNode(Base):
    """
    A node in the Universal Code Graph.

    One UCGNode represents a single code entity (CLASS, METHOD, FILE, etc.)
    within a specific analysis job. All language-specific fields are stored
    in the JSONB ``properties`` column.
    """

    __tablename__ = "ucg_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Node type enum value — must be one of the NodeType values from the spec.
    node_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Fully-qualified identifier for the code entity (e.g. "com.example.UserService").
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Language identifier: java | python | php | javascript | typescript
    language: Mapped[str] = mapped_column(Text, nullable=False)
    # Source file location.
    file_path: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    col_start: Mapped[int | None] = mapped_column(Integer)
    col_end: Mapped[int | None] = mapped_column(Integer)
    # All node-type-specific fields (see tech-spec.md section 5.1).
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 1536-dimensional vector embedding populated by the Learner agent.
    embedding: Mapped[object | None] = mapped_column(_VECTOR_COLUMN, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships.
    job: Mapped["Job"] = relationship("Job", back_populates="ucg_nodes")  # noqa: F821


class UCGEdge(Base):
    """
    A directed edge in the Universal Code Graph.

    Represents a typed relationship between two UCGNode instances within the
    same job. Self-loops are forbidden at the DB level (CHECK constraint).
    """

    __tablename__ = "ucg_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Edge type enum value — must be one of the EdgeType values from the spec.
    edge_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ucg_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ucg_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Edge-specific properties (e.g., call_count for CALLS edges).
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Relative weight of the edge (defaults to 1.0, must be positive).
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships.
    job: Mapped["Job"] = relationship("Job", back_populates="ucg_edges")  # noqa: F821
    source_node: Mapped["UCGNode"] = relationship(
        "UCGNode", foreign_keys=[source_node_id], lazy="select"
    )
    target_node: Mapped["UCGNode"] = relationship(
        "UCGNode", foreign_keys=[target_node_id], lazy="select"
    )


class Embedding(Base):
    """
    Supplementary vector embeddings for semantic similarity search.

    Stores text embeddings for any job entity: ucg_node, smell, plan_task,
    or patch. The ``entity_id`` column references the primary key of the
    corresponding table row identified by ``entity_type``.
    """

    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Discriminator: 'ucg_node' | 'smell' | 'plan_task' | 'patch'
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The text that was embedded (stored for reproducibility and debugging).
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 1536-dimensional vector embedding.
    embedding: Mapped[object] = mapped_column(_VECTOR_COLUMN, nullable=False)

    model_used: Mapped[str] = mapped_column(
        Text, nullable=False, default="text-embedding-3-small"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
