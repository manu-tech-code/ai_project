"""add prompt to patches

Revision ID: 20260307_add_prompt_to_patches
Revises: 20260307_add_repo_path
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa

revision = "20260307_add_prompt_to_patches"
down_revision = "20260307_add_repo_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patches", sa.Column("prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("patches", "prompt")
