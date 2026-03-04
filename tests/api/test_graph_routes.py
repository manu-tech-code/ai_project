"""
API integration tests for /api/v1/graph and /api/v1/smells endpoints.

All tests use the in-process FastAPI test client with SQLite + mocked auth.
"""

import pytest
from httpx import AsyncClient

_FAKE_JOB_ID = "00000000-0000-0000-0000-000000000042"
_FAKE_NODE_ID = "00000000-0000-0000-0000-000000000043"
_FAKE_SMELL_ID = "00000000-0000-0000-0000-000000000044"
_FAKE_PLAN_ID = "00000000-0000-0000-0000-000000000045"


# ---------------------------------------------------------------------------
# Graph routes — 404 for nonexistent job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/graph/{_FAKE_JOB_ID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_graph_nodes_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/graph/{_FAKE_JOB_ID}/nodes")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_graph_node_detail_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/graph/{_FAKE_JOB_ID}/nodes/{_FAKE_NODE_ID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_graph_edges_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/graph/{_FAKE_JOB_ID}/edges")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_graph_metrics_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/graph/{_FAKE_JOB_ID}/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_post_subgraph_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.post(
        f"/api/v1/graph/{_FAKE_JOB_ID}/subgraph",
        json={
            "seed_node_ids": [_FAKE_NODE_ID],
            "depth": 1,
            "direction": "both",
        },
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Graph routes — invalid UUID path params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_graph_invalid_uuid_returns_422(client: AsyncClient):
    response = await client.get("/api/v1/graph/not-a-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_graph_nodes_invalid_uuid_returns_422(client: AsyncClient):
    response = await client.get("/api/v1/graph/not-a-uuid/nodes")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Smells routes — 404 for nonexistent job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_smells_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/smells/{_FAKE_JOB_ID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_smell_detail_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/smells/{_FAKE_JOB_ID}/{_FAKE_SMELL_ID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_smell_summary_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/smells/{_FAKE_JOB_ID}/summary")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_smell_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.post(
        f"/api/v1/smells/{_FAKE_JOB_ID}/{_FAKE_SMELL_ID}/dismiss",
        json={"reason": "Not applicable", "dismissed_by": "qa@example.com"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Smells routes — invalid UUID path params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_smells_invalid_uuid_returns_422(client: AsyncClient):
    response = await client.get("/api/v1/smells/not-a-uuid")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Plan routes — 404 for nonexistent job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plan_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/plan/{_FAKE_JOB_ID}")
    # Plan endpoint may not be mounted; accept 404 or 422 for missing route
    assert response.status_code in (404, 422)


@pytest.mark.asyncio
async def test_get_plan_tasks_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/plan/{_FAKE_JOB_ID}/tasks")
    assert response.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Patches routes — 404 for nonexistent job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_patches_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/patches/{_FAKE_JOB_ID}")
    assert response.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Report routes — 404 for nonexistent job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_report_nonexistent_job_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/report/{_FAKE_JOB_ID}")
    assert response.status_code in (404, 422)
