"""Pydantic schemas for VCS provider CRUD and push operations."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VCSProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., pattern="^(github|gitlab|bitbucket|other)$")
    base_url: str | None = None      # for self-hosted
    token: str = Field(..., min_length=1)
    username: str | None = None


class VCSProviderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    base_url: str | None = None
    token: str | None = None
    username: str | None = None


class VCSProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider: str
    base_url: str | None
    username: str | None
    token_hint: str        # last 4 chars of token, e.g. "***abc1"
    created_at: datetime
    updated_at: datetime


class VCSTestRequest(BaseModel):
    provider: str
    base_url: str | None = None
    token: str
    repo_url: str | None = None  # optional: test access to specific repo


class VCSTestResponse(BaseModel):
    success: bool
    message: str


class VCSFromURLRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS URL of the git repository")
    branch: str | None = Field(None, description="Branch to clone (default: repo default branch)")
    provider_id: UUID | None = None    # stored provider to use for auth
    token: str | None = None           # one-time token (for public repos or without stored config)
    label: str | None = Field(None, max_length=200)
    config: dict = Field(default_factory=dict)


class VCSPushRequest(BaseModel):
    branch_name: str | None = Field(None, description="Branch name for fixes (default: alm/fixes-{job_id[:8]})")
    provider_id: UUID | None = None   # stored provider for auth
    token: str | None = None          # one-time token
    create_pr: bool = Field(True, description="Try to create a PR after pushing")
    patch_ids: list[UUID] | None = None   # None = push all pending patches


class VCSPushResponse(BaseModel):
    branch: str
    commits: int
    patches_applied: int
    pr_url: str | None
    message: str
