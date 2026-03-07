"""
API tests for POST /api/v1/patches/{job_id}/generate.

Covers:
  - 404 when job does not exist
  - 409 when job is not in 'complete' status
  - 409 when job has no repo_path
  - 409 when repo_path directory does not exist on disk
  - 200 with correct GeneratePatchesResponse shape on a complete job with a
    valid repo_path directory (TransformerAgent.run is mocked)
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.job import Job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(**kwargs) -> Job:
    """Return a Job ORM instance with sensible defaults for generate tests."""
    defaults = dict(
        id=uuid.uuid4(),
        status="complete",
        label="test-job",
        languages=[],
        config={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        repo_path=None,
    )
    defaults.update(kwargs)
    return Job(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_patches_404_job_not_found(client: AsyncClient):
    """POST generate with a random UUID that has no matching job → 404."""
    random_id = uuid.uuid4()
    response = await client.post(f"/api/v1/patches/{random_id}/generate", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_patches_409_job_not_complete(
    client: AsyncClient, db_session
):
    """POST generate when job status is 'pending' → 409 job_not_complete."""
    job = _make_job(status="pending")
    db_session.add(job)
    await db_session.flush()

    response = await client.post(f"/api/v1/patches/{job.id}/generate", json={})
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"] == "job_not_complete"


@pytest.mark.asyncio
async def test_generate_patches_409_repo_path_missing(
    client: AsyncClient, db_session
):
    """POST generate when job.repo_path is None → 409 repo_path_missing."""
    job = _make_job(status="complete", repo_path=None)
    db_session.add(job)
    await db_session.flush()

    response = await client.post(f"/api/v1/patches/{job.id}/generate", json={})
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"] == "repo_path_missing"


@pytest.mark.asyncio
async def test_generate_patches_409_repo_path_not_on_disk(
    client: AsyncClient, db_session
):
    """POST generate when repo_path is set but directory is gone → 409 repo_path_not_found."""
    job = _make_job(
        status="complete",
        repo_path="/tmp/alm_job_does_not_exist_xyz987",
    )
    db_session.add(job)
    await db_session.flush()

    response = await client.post(f"/api/v1/patches/{job.id}/generate", json={})
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"] == "repo_path_not_found"


@pytest.mark.asyncio
async def test_generate_patches_200_success(
    client: AsyncClient, db_session, tmp_path: Path
):
    """POST generate on a complete job with a valid repo_path → 200 with correct shape."""
    # tmp_path is a real directory on disk — satisfies the existence check.
    job = _make_job(status="complete", repo_path=str(tmp_path))
    db_session.add(job)
    await db_session.flush()

    mock_result = {"patches_created": 2, "patch_ids": ["id1", "id2"]}

    # TransformerAgent is imported lazily with `from app.agents.transformer import
    # TransformerAgent` inside generate_patches. Patching the class in its source
    # module intercepts the import because Python caches the module object in
    # sys.modules — the `from X import Y` binds Y at call time from the cached module.
    with patch(
        "app.agents.transformer.TransformerAgent",
    ) as MockAgent:
        instance = MockAgent.return_value
        instance.run = AsyncMock(return_value=mock_result)

        response = await client.post(f"/api/v1/patches/{job.id}/generate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["patches_created"] == 2
    assert body["patch_ids"] == ["id1", "id2"]

    # Verify patch_count on the job was updated from the authoritative DB count.
    # The agent is mocked (no real Patch rows inserted), so the DB count is 0.
    from sqlalchemy import select
    refreshed = await db_session.execute(select(Job).where(Job.id == job.id))
    refreshed_job = refreshed.scalar_one()
    assert refreshed_job.patch_count == 0  # authoritative DB count, no real patches inserted
