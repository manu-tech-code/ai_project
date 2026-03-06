"""VCSProvider ORM model — stores version control credentials."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VCSProvider(Base):
    __tablename__ = "vcs_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)           # user-friendly label
    provider: Mapped[str] = mapped_column(Text, nullable=False)        # github | gitlab | bitbucket | other
    base_url: Mapped[str | None] = mapped_column(Text)                # for self-hosted instances
    token: Mapped[str] = mapped_column(Text, nullable=False)           # PAT or OAuth token
    username: Mapped[str | None] = mapped_column(Text)                # optional username
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
