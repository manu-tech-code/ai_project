"""
SQLAlchemy ORM model for the api_keys table.

Raw API key values are never stored — only bcrypt hashes (work factor 12).
See docs/db-schema.md section 7 for the full DDL.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class APIKey(Base):
    """
    API key record.

    The raw key value is returned exactly once at creation time and is never
    stored. The ``key_hash`` column holds the bcrypt hash (cost 12).
    The ``key_prefix`` (first 12 characters) is stored plaintext for display
    and pre-filter lookups during verification.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-readable label for identification in the admin UI.
    label: Mapped[str] = mapped_column(Text, nullable=False)

    # bcrypt hash of the raw key (cost 12). Never the raw value.
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # First 12 characters of the raw key for display/pre-filter (safe to store).
    # Example: "alm_live_a1b2" for key "alm_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)

    # Authorization scopes: subset of ['read', 'write', 'admin'].
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    # Per-key rate limit override (requests per minute).
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100
    )

    # Lifecycle management.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    def is_valid(self) -> bool:
        """Return True if the key is not revoked and not expired."""
        if self.revoked:
            return False
        if self.expires_at and self.expires_at < datetime.now(UTC):
            return False
        return True
