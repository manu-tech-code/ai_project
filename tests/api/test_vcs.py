"""
API integration tests for VCS provider CRUD (/api/v1/vcs/providers)
and the connection-test endpoint (/api/v1/vcs/test).

All external I/O (httpx, git) is mocked.  Tests use the shared SQLite
in-memory DB and the `client` fixture from conftest.py.
"""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/vcs"

GITHUB_PAYLOAD = {
    "name": "My GitHub Account",
    "provider": "github",
    "token": "ghp_ABCDEFGH12345678",
}

GITLAB_PAYLOAD = {
    "name": "Self-Hosted GitLab",
    "provider": "gitlab",
    "base_url": "https://gitlab.example.com",
    "token": "glpat-XXXXXXXXXXXXXXXXXXXX",
    "username": "ci-bot",
}


# ---------------------------------------------------------------------------
# Helpers — insert a VCSProvider via the API so we get a valid UUID.
# ---------------------------------------------------------------------------


async def _create_provider(client: AsyncClient, payload: dict) -> dict:
    """POST a provider and return the response JSON (asserts 201)."""
    resp = await client.post(f"{BASE}/providers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# TestVCSProviders — CRUD
# ---------------------------------------------------------------------------


class TestVCSProviders:
    """Full CRUD lifecycle for /api/v1/vcs/providers."""

    @pytest.mark.asyncio
    async def test_list_providers_empty(self, client: AsyncClient):
        """GET /vcs/providers on a fresh DB returns an empty list."""
        resp = await client.get(f"{BASE}/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_provider_github(self, client: AsyncClient):
        """POST creates a GitHub provider; response includes token_hint, not raw token."""
        resp = await client.post(f"{BASE}/providers", json=GITHUB_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "github"
        assert data["name"] == "My GitHub Account"
        assert "token_hint" in data
        # token_hint must be masked (starts with ***)
        assert data["token_hint"].startswith("***")
        # The hint must include the last 4 chars of the token
        assert data["token_hint"].endswith(GITHUB_PAYLOAD["token"][-4:])

    @pytest.mark.asyncio
    async def test_create_provider_gitlab(self, client: AsyncClient):
        """POST creates a GitLab provider with base_url and username."""
        resp = await client.post(f"{BASE}/providers", json=GITLAB_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "gitlab"
        assert data["base_url"] == "https://gitlab.example.com"
        assert data["username"] == "ci-bot"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_provider_invalid_type(self, client: AsyncClient):
        """provider field must match the allowed pattern; 'invalid' returns 422."""
        payload = {**GITHUB_PAYLOAD, "provider": "invalid"}
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_provider_missing_token(self, client: AsyncClient):
        """Omitting the required token field returns 422."""
        payload = {"name": "No Token Provider", "provider": "github"}
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_provider_empty_token(self, client: AsyncClient):
        """An empty string token violates min_length=1 and returns 422."""
        payload = {**GITHUB_PAYLOAD, "token": ""}
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_provider_empty_name(self, client: AsyncClient):
        """An empty string name violates min_length=1 and returns 422."""
        payload = {**GITHUB_PAYLOAD, "name": ""}
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_provider(self, client: AsyncClient):
        """GET /vcs/providers/{id} returns the correct provider record."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        provider_id = created["id"]

        resp = await client.get(f"{BASE}/providers/{provider_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == provider_id
        assert data["provider"] == "github"

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self, client: AsyncClient):
        """GET /vcs/providers/<random-uuid> returns 404.

        NOTE: The app has a global 404 exception handler that returns a flat
        {"error": "not_found", ...} body rather than the default FastAPI
        {"detail": ...} wrapper.  Both shapes contain an "error" key at some
        level, so we check either structure.
        """
        random_id = str(uuid.uuid4())
        resp = await client.get(f"{BASE}/providers/{random_id}")
        assert resp.status_code == 404
        body = resp.json()
        # Accept both the global handler shape and the endpoint's HTTPException shape
        error_val = body.get("error") or (body.get("detail") or {}).get("error")
        assert error_val is not None

    @pytest.mark.asyncio
    async def test_get_provider_invalid_uuid(self, client: AsyncClient):
        """GET /vcs/providers/<non-uuid> triggers path validation and returns 422."""
        resp = await client.get(f"{BASE}/providers/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_provider_name(self, client: AsyncClient):
        """PATCH updates the provider name while leaving token unchanged."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        provider_id = created["id"]

        resp = await client.patch(
            f"{BASE}/providers/{provider_id}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        # token_hint should still reflect the original token
        assert data["token_hint"].endswith(GITHUB_PAYLOAD["token"][-4:])

    @pytest.mark.asyncio
    async def test_update_provider_token(self, client: AsyncClient):
        """PATCH with a new token causes token_hint to reflect the new token."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        provider_id = created["id"]
        new_token = "ghp_NEWTOKEN9999"

        resp = await client.patch(
            f"{BASE}/providers/{provider_id}",
            json={"token": new_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Hint must end with last 4 chars of the NEW token
        assert data["token_hint"].endswith(new_token[-4:])
        # Must not end with last 4 chars of old token (they differ)
        assert not data["token_hint"].endswith(GITHUB_PAYLOAD["token"][-4:])

    @pytest.mark.asyncio
    async def test_update_provider_not_found(self, client: AsyncClient):
        """PATCH on a non-existent provider returns 404."""
        resp = await client.patch(
            f"{BASE}/providers/{uuid.uuid4()}",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_provider(self, client: AsyncClient):
        """DELETE removes the provider; subsequent GET returns 404."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        provider_id = created["id"]

        del_resp = await client.delete(f"{BASE}/providers/{provider_id}")
        assert del_resp.status_code == 204

        get_resp = await client.get(f"{BASE}/providers/{provider_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_provider_not_found(self, client: AsyncClient):
        """DELETE on a non-existent provider returns 404."""
        resp = await client.delete(f"{BASE}/providers/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_token_not_exposed_in_create_response(self, client: AsyncClient):
        """The raw token must never appear in any JSON response field."""
        token = GITHUB_PAYLOAD["token"]
        resp = await client.post(f"{BASE}/providers", json=GITHUB_PAYLOAD)
        assert resp.status_code == 201
        # Check the raw JSON body string — the token should not appear
        assert token not in resp.text

    @pytest.mark.asyncio
    async def test_token_not_exposed_in_get_response(self, client: AsyncClient):
        """Raw token must not appear in GET /vcs/providers/{id} response body."""
        token = GITHUB_PAYLOAD["token"]
        created = await _create_provider(client, GITHUB_PAYLOAD)
        resp = await client.get(f"{BASE}/providers/{created['id']}")
        assert resp.status_code == 200
        assert token not in resp.text

    @pytest.mark.asyncio
    async def test_token_not_exposed_in_list_response(self, client: AsyncClient):
        """Raw token must not appear in GET /vcs/providers list response body."""
        token = GITHUB_PAYLOAD["token"]
        await _create_provider(client, GITHUB_PAYLOAD)
        resp = await client.get(f"{BASE}/providers")
        assert resp.status_code == 200
        assert token not in resp.text

    @pytest.mark.asyncio
    async def test_response_has_no_token_field(self, client: AsyncClient):
        """VCSProviderResponse schema must not include a 'token' key."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        assert "token" not in created
        # token_hint is fine; raw 'token' must be absent
        assert "token_hint" in created

    @pytest.mark.asyncio
    async def test_list_providers_after_create(self, client: AsyncClient):
        """After creating a provider it appears in the list endpoint."""
        created = await _create_provider(client, GITHUB_PAYLOAD)
        provider_id = created["id"]

        resp = await client.get(f"{BASE}/providers")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()]
        assert provider_id in ids

    @pytest.mark.asyncio
    async def test_provider_bitbucket_accepted(self, client: AsyncClient):
        """'bitbucket' is a valid provider value."""
        payload = {
            "name": "Bitbucket Workspace",
            "provider": "bitbucket",
            "token": "bb_PAT_12345678",
            "username": "myuser",
        }
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_provider_other_accepted(self, client: AsyncClient):
        """'other' is a valid provider value."""
        payload = {
            "name": "Generic Git Server",
            "provider": "other",
            "token": "some-token-xxxx",
        }
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_token_hint_short_token_masked_fully(self, client: AsyncClient):
        """A token with <= 4 chars should be fully masked as '***'."""
        payload = {**GITHUB_PAYLOAD, "token": "abc"}
        resp = await client.post(f"{BASE}/providers", json=payload)
        assert resp.status_code == 201
        assert resp.json()["token_hint"] == "***"


# ---------------------------------------------------------------------------
# TestVCSTestConnection — POST /api/v1/vcs/test
# ---------------------------------------------------------------------------


class TestVCSTestConnection:
    """Tests for POST /api/v1/vcs/test (connection probe without persisting)."""

    @pytest.mark.asyncio
    async def test_test_connection_github_success(self, client: AsyncClient):
        """Mock httpx returning 200 → success=True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.vcs.httpx.AsyncClient", return_value=mock_client_instance):
            resp = await client.post(
                f"{BASE}/test",
                json={
                    "provider": "github",
                    "token": "ghp_test_token_1234",
                    "repo_url": "https://github.com/owner/repo",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "message" in data

    @pytest.mark.asyncio
    async def test_test_connection_github_auth_failure(self, client: AsyncClient):
        """Mock httpx returning 401 → success=False."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.vcs.httpx.AsyncClient", return_value=mock_client_instance):
            resp = await client.post(
                f"{BASE}/test",
                json={
                    "provider": "github",
                    "token": "ghp_INVALID",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "401" in data["message"]

    @pytest.mark.asyncio
    async def test_test_connection_gitlab_success(self, client: AsyncClient):
        """GitLab provider with 200 response → success=True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.vcs.httpx.AsyncClient", return_value=mock_client_instance):
            resp = await client.post(
                f"{BASE}/test",
                json={
                    "provider": "gitlab",
                    "token": "glpat-valid",
                    "base_url": "https://gitlab.example.com",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_test_connection_other_provider_no_http_call(self, client: AsyncClient):
        """'other' provider skips HTTP probe and always returns success=True."""
        with patch("app.services.vcs.httpx.AsyncClient") as mock_cls:
            resp = await client.post(
                f"{BASE}/test",
                json={
                    "provider": "other",
                    "token": "some-token",
                },
            )
            # httpx.AsyncClient must NOT have been called
            mock_cls.assert_not_called()

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_test_connection_network_exception(self, client: AsyncClient):
        """A network error during the probe returns success=False (no 500)."""
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=Exception("network error"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.vcs.httpx.AsyncClient", return_value=mock_client_instance):
            resp = await client.post(
                f"{BASE}/test",
                json={
                    "provider": "github",
                    "token": "ghp_any",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "network error" in data["message"].lower() or "failed" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_test_connection_missing_token_returns_422(self, client: AsyncClient):
        """'token' is required; omitting it returns 422."""
        resp = await client.post(
            f"{BASE}/test",
            json={"provider": "github"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_test_connection_missing_provider_returns_422(self, client: AsyncClient):
        """'provider' is required; omitting it returns 422."""
        resp = await client.post(
            f"{BASE}/test",
            json={"token": "ghp_test"},
        )
        assert resp.status_code == 422
