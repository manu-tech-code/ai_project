"""
API integration tests for VCS-backed analysis and patch-push endpoints:

  POST /api/v1/analyze/from-url   — submit job by cloning a git URL
  POST /api/v1/patches/{job_id}/push — push generated patches back to repo

All git/network operations are mocked.  Uses the shared SQLite in-memory DB
and the `client` fixture from conftest.py.

MOCKING STRATEGY
----------------
Both `clone_repo` and `push_patches_to_repo` are imported with local
`from app.services.vcs import X` statements *inside* endpoint function bodies.
Python re-resolves these names from the live module dict on every call, so
patching `app.services.vcs.X` is correct.

However, `push_patches_to_repo` is also called via `loop.run_in_executor`
which dispatches a synchronous lambda to a thread-pool worker. To keep tests
hermetic we patch at `git.Repo.clone_from` (the actual network call) for
clone tests and at `app.services.vcs.push_patches_to_repo` for push tests.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

ANALYZE_URL = "/api/v1/analyze/from-url"
PUSH_URL = "/api/v1/patches/{job_id}/push"


# ---------------------------------------------------------------------------
# DB helpers — insert rows that require a parent chain (Job > Plan > PlanTask
# > Patch) directly into the test session so we control exact state.
# ---------------------------------------------------------------------------


async def _make_job(db: AsyncSession, **kwargs):
    from app.models.job import Job  # noqa: PLC0415

    defaults = dict(
        id=uuid.uuid4(),
        status="complete",
        archive_filename="test.zip",
        languages=[],
        config={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    job = Job(**defaults)
    db.add(job)
    await db.flush()
    return job


async def _make_plan(db: AsyncSession, job_id: uuid.UUID):
    from app.models.plan import Plan  # noqa: PLC0415

    plan = Plan(
        id=uuid.uuid4(),
        job_id=job_id,
        version=1,
        priority_order=[],
        created_at=datetime.now(UTC),
    )
    db.add(plan)
    await db.flush()
    return plan


async def _make_task(db: AsyncSession, plan_id: uuid.UUID, job_id: uuid.UUID):
    from app.models.plan import PlanTask  # noqa: PLC0415

    task = PlanTask(
        id=uuid.uuid4(),
        plan_id=plan_id,
        job_id=job_id,
        title="Refactor OrderService",
        description="Extract helper methods",
        smell_ids=[],
        affected_files=["src/OrderService.java"],
        refactor_pattern="extract_method",
        dependencies=[],
        automated=True,
        status="pending",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()
    return task


async def _make_patch(db: AsyncSession, job_id: uuid.UUID, task_id: uuid.UUID, **kwargs):
    from app.models.patch import Patch  # noqa: PLC0415

    defaults = dict(
        id=uuid.uuid4(),
        job_id=job_id,
        task_id=task_id,
        file_path="src/OrderService.java",
        patch_type="modify",
        language="java",
        status="pending",
        original_content="class OrderService {}",
        patched_content="class OrderService { /* refactored */ }",
        diff="--- a/src/OrderService.java\n+++ b/src/OrderService.java\n",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    patch_obj = type("Patch", (), {})()  # placeholder until import
    from app.models.patch import Patch  # noqa: PLC0415

    patch_obj = Patch(**defaults)
    db.add(patch_obj)
    await db.flush()
    return patch_obj


# ---------------------------------------------------------------------------
# POST /api/v1/analyze/from-url
# ---------------------------------------------------------------------------


class TestAnalyzeFromURL:
    """Tests for POST /api/v1/analyze/from-url."""

    @pytest.mark.asyncio
    async def test_from_url_clone_failure_returns_422(self, client: AsyncClient):
        """When the underlying git clone raises, respond with 422 clone_failed.

        We patch git.Repo.clone_from (the leaf network call inside clone_repo)
        so the real git binary is never invoked.
        """
        with patch("git.Repo.clone_from", side_effect=Exception("auth failed")):
            resp = await client.post(
                ANALYZE_URL,
                json={
                    "repo_url": "https://github.com/owner/private-repo",
                    "token": "ghp_bad",
                },
            )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "clone_failed"
        assert "auth failed" in detail["message"]

    @pytest.mark.asyncio
    async def test_from_url_creates_job_with_repo_url(self, client: AsyncClient):
        """Successful clone creates a Job with repo_url set and returns job_id."""
        with patch("git.Repo.clone_from", return_value=MagicMock()):
            resp = await client.post(
                ANALYZE_URL,
                json={
                    "repo_url": "https://github.com/owner/my-repo",
                    "label": "my-repo-test",
                },
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_from_url_label_defaults_to_repo_name(self, client: AsyncClient):
        """When label is omitted the job label defaults to the repo name from the URL."""
        with patch("git.Repo.clone_from", return_value=MagicMock()):
            resp = await client.post(
                ANALYZE_URL,
                json={"repo_url": "https://github.com/owner/cool-project.git"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["label"] == "cool-project"

    @pytest.mark.asyncio
    async def test_from_url_returns_polling_links(self, client: AsyncClient):
        """Response includes self/graph/report links for polling."""
        with patch("git.Repo.clone_from", return_value=MagicMock()):
            resp = await client.post(
                ANALYZE_URL,
                json={"repo_url": "https://github.com/owner/repo"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "links" in data
        assert "self" in data["links"]
        assert "graph" in data["links"]

    @pytest.mark.asyncio
    async def test_from_url_with_stored_provider(self, client: AsyncClient, db_session: AsyncSession):
        """When provider_id is given, its credentials are resolved from the DB."""
        from app.models.vcs import VCSProvider  # noqa: PLC0415

        provider = VCSProvider(
            id=uuid.uuid4(),
            name="GitHub CI",
            provider="github",
            token="ghp_stored_token",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(provider)
        await db_session.flush()

        with patch("git.Repo.clone_from", return_value=MagicMock()) as mock_clone:
            resp = await client.post(
                ANALYZE_URL,
                json={
                    "repo_url": "https://github.com/owner/repo",
                    "provider_id": str(provider.id),
                },
            )

        assert resp.status_code == 202
        # clone was called (with auth injected)
        mock_clone.assert_called_once()

    @pytest.mark.asyncio
    async def test_from_url_provider_not_found_returns_404(self, client: AsyncClient):
        """A provider_id that doesn't exist in the DB returns 404."""
        resp = await client.post(
            ANALYZE_URL,
            json={
                "repo_url": "https://github.com/owner/repo",
                "provider_id": str(uuid.uuid4()),
            },
        )

        assert resp.status_code == 404
        # The endpoint raises HTTPException(404, ...) before any git call.
        # Accept both the endpoint's detail shape and the global 404 handler shape.
        body = resp.json()
        error_val = (
            (body.get("detail") or {}).get("error")
            or body.get("error")
        )
        assert error_val in ("provider_not_found", "not_found")

    @pytest.mark.asyncio
    async def test_from_url_invalid_config_returns_422(self, client: AsyncClient):
        """A config dict with an invalid field causes 422 invalid_config."""
        with patch("git.Repo.clone_from", return_value=MagicMock()):
            resp = await client.post(
                ANALYZE_URL,
                json={
                    "repo_url": "https://github.com/owner/repo",
                    "config": {"max_smells_per_class": "not-an-int"},
                },
            )
        # Either 422 from Pydantic body validation OR 422 from invalid_config handler.
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_from_url_missing_repo_url_returns_422(self, client: AsyncClient):
        """Omitting repo_url returns 422 (required field)."""
        resp = await client.post(ANALYZE_URL, json={"token": "ghp_x"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/patches/{job_id}/push
# ---------------------------------------------------------------------------


class TestPushPatches:
    """Tests for POST /api/v1/patches/{job_id}/push."""

    @pytest.mark.asyncio
    async def test_push_no_repo_url_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """A job without repo_url returns 400 no_repo_url."""
        job = await _make_job(db_session)

        resp = await client.post(
            PUSH_URL.format(job_id=job.id),
            json={"token": "ghp_x", "create_pr": False},
        )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "no_repo_url"

    @pytest.mark.asyncio
    async def test_push_no_token_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """A job with repo_url but no token/provider returns 400 no_token."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )

        resp = await client.post(
            PUSH_URL.format(job_id=job.id),
            json={"create_pr": False},  # no token, no provider_id
        )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "no_token"

    @pytest.mark.asyncio
    async def test_push_no_patches_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """A job with repo_url and token but no pending patches returns 400 no_patches."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )

        resp = await client.post(
            PUSH_URL.format(job_id=job.id),
            json={"token": "ghp_x", "create_pr": False},
        )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "no_patches"

    @pytest.mark.asyncio
    async def test_push_nonexistent_job_returns_404(self, client: AsyncClient):
        """A job_id that doesn't exist returns 404."""
        resp = await client.post(
            PUSH_URL.format(job_id=uuid.uuid4()),
            json={"token": "ghp_x", "create_pr": False},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_push_success(self, client: AsyncClient, db_session: AsyncSession):
        """When push_patches_to_repo succeeds, response reports patches_applied count."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)
        await _make_patch(db_session, job.id, task.id, file_path="src/Helper.java")

        # Patch git.Repo.clone_from (used by push_patches_to_repo internally)
        # AND mock out the push/commit/remote steps.
        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.git.add = MagicMock()
        mock_repo.index.commit = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        with patch("git.Repo.clone_from", return_value=mock_repo):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={
                    "token": "ghp_valid",
                    "create_pr": False,
                    "branch_name": "alm/test-branch",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["patches_applied"] == 2
        assert data["branch"] == "alm/test-branch"
        assert data["pr_url"] is None

    @pytest.mark.asyncio
    async def test_push_branch_name_defaults_to_job_id_prefix(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """When branch_name is omitted the default is 'alm/fixes-{job_id[:8]}'."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        with patch("git.Repo.clone_from", return_value=mock_repo):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={"token": "ghp_valid", "create_pr": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        expected_prefix = f"alm/fixes-{str(job.id)[:8]}"
        assert data["branch"] == expected_prefix

    @pytest.mark.asyncio
    async def test_push_creates_pr(self, client: AsyncClient, db_session: AsyncSession):
        """When create_pr=True and provider is github, pr_url appears in the response."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        pr_url = "https://github.com/owner/repo/pull/42"
        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        # Mock the PR creation HTTP call
        mock_http_response = MagicMock()
        mock_http_response.status_code = 201
        mock_http_response.json.return_value = {"html_url": pr_url}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_http_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("git.Repo.clone_from", return_value=mock_repo), \
             patch("app.services.vcs.httpx.AsyncClient", return_value=mock_http_client):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={
                    "token": "ghp_valid",
                    "create_pr": True,
                    "branch_name": "alm/my-branch",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_url"] == pr_url

    @pytest.mark.asyncio
    async def test_push_no_pr_for_non_github_provider(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """PR creation is skipped for non-GitHub providers even when create_pr=True."""
        from app.models.vcs import VCSProvider  # noqa: PLC0415

        vcs_provider = VCSProvider(
            id=uuid.uuid4(),
            name="GitLab",
            provider="gitlab",
            token="glpat-token",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(vcs_provider)
        await db_session.flush()

        job = await _make_job(
            db_session,
            repo_url="https://gitlab.example.com/owner/repo",
            vcs_provider_id=vcs_provider.id,
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        with patch("git.Repo.clone_from", return_value=mock_repo), \
             patch("app.services.vcs.httpx.AsyncClient") as mock_http:
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={"token": "glpat-token", "create_pr": True},
            )

        assert resp.status_code == 200
        # PR URL should be None since provider is gitlab, not github
        assert resp.json()["pr_url"] is None
        # httpx was not called for PR creation
        mock_http.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_git_failure_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """When the push fails at the git layer, respond with 422 push_failed."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        with patch("git.Repo.clone_from", side_effect=Exception("push rejected")):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={"token": "ghp_x", "create_pr": False},
            )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["error"] == "push_failed"
        assert "push rejected" in detail["message"]

    @pytest.mark.asyncio
    async def test_push_stores_fix_branch_on_job(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After a successful push, job.fix_branch is persisted in the DB."""
        from sqlalchemy import select  # noqa: PLC0415
        from app.models.job import Job  # noqa: PLC0415

        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        branch = "alm/persist-check"
        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        with patch("git.Repo.clone_from", return_value=mock_repo):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={"token": "ghp_x", "create_pr": False, "branch_name": branch},
            )

        assert resp.status_code == 200

        # Verify the fix_branch was persisted on the job row
        await db_session.refresh(job)
        assert job.fix_branch == branch

    @pytest.mark.asyncio
    async def test_push_with_patch_ids_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """When patch_ids is provided, only those patches are pushed."""
        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        patch1 = await _make_patch(db_session, job.id, task.id, file_path="src/A.java")
        await _make_patch(db_session, job.id, task.id, file_path="src/B.java")

        mock_repo = MagicMock()
        mock_repo.create_head.return_value = MagicMock()
        mock_repo.remote.return_value = MagicMock()

        with patch("git.Repo.clone_from", return_value=mock_repo):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={
                    "token": "ghp_x",
                    "create_pr": False,
                    "patch_ids": [str(patch1.id)],
                },
            )

        assert resp.status_code == 200
        # Only 1 patch file was written (src/A.java)
        data = resp.json()
        assert data["patches_applied"] == 1

    @pytest.mark.asyncio
    async def test_push_uses_stored_provider_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """When job has vcs_provider_id and no body token, the stored token is used."""
        from app.models.vcs import VCSProvider  # noqa: PLC0415

        vcs_provider = VCSProvider(
            id=uuid.uuid4(),
            name="GitHub",
            provider="github",
            token="ghp_stored_provider_token",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(vcs_provider)
        await db_session.flush()

        job = await _make_job(
            db_session,
            repo_url="https://github.com/owner/repo",
            vcs_provider_id=vcs_provider.id,
        )
        plan = await _make_plan(db_session, job.id)
        task = await _make_task(db_session, plan.id, job.id)
        await _make_patch(db_session, job.id, task.id)

        clone_calls = []

        def capture_clone(clone_url, **kwargs):
            clone_calls.append(clone_url)
            mock_r = MagicMock()
            mock_r.create_head.return_value = MagicMock()
            mock_r.remote.return_value = MagicMock()
            return mock_r

        with patch("git.Repo.clone_from", side_effect=capture_clone):
            resp = await client.post(
                PUSH_URL.format(job_id=job.id),
                json={"create_pr": False},  # no token in body — must use stored
            )

        assert resp.status_code == 200
        # The clone URL should contain the stored token (injected by _inject_token)
        assert len(clone_calls) == 1
        assert "ghp_stored_provider_token" in clone_calls[0]
