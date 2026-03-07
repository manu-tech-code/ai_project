"""add repo_path to jobs

Revision ID: 20260307_add_repo_path
Revises: add_app_settings_table
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa

revision = "20260307_add_repo_path"
down_revision = "add_app_settings_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("repo_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "repo_path")
