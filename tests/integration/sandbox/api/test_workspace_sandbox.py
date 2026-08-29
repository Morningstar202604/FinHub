"""Integration tests for workspace sandbox API endpoints.

Tests the sandbox stats and package install endpoints wired to a real
PTCSandbox (MemoryProvider). Database and auth are mocked via the
``sandbox_client`` fixture from conftest.
"""

from __future__ import annotations

import pytest

from .conftest import TEST_WS_ID

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE = f"/api/v1/workspaces/{TEST_WS_ID}/sandbox"


# ---------------------------------------------------------------------------
# TestSandboxStats
# ---------------------------------------------------------------------------


class TestSandboxStats:
    async def test_stats_running_workspace(self, sandbox_client):
        client, _sandbox = sandbox_client

        resp = await client.get(f"{BASE}/stats")
        assert resp.status_code == 200

        body = resp.json()
        assert body["workspace_id"] == TEST_WS_ID
        assert "resources" in body and isinstance(body["resources"], dict)
        assert "packages" in body and isinstance(body["packages"], list)
        assert "default_packages" in body and isinstance(body["default_packages"], list)

    async def test_stats_response_structure(self, sandbox_client):
        client, _sandbox = sandbox_client

        resp = await client.get(f"{BASE}/stats")
        assert resp.status_code == 200

        body = resp.json()
        # Verify all SandboxStatsResponse fields are present
        assert body["workspace_id"] == TEST_WS_ID
        assert "sandbox_id" in body
        assert "state" in body
        assert "resources" in body
        assert "disk_usage" in body
        assert "directory_breakdown" in body and isinstance(
            body["directory_breakdown"], list
        )
        assert "packages" in body and isinstance(body["packages"], list)
        assert "mcp_servers" in body and isinstance(body["mcp_servers"], list)
        assert "skills" in body and isinstance(body["skills"], list)
        assert "default_packages" in body and isinstance(
            body["default_packages"], list
        )


# ---------------------------------------------------------------------------
# TestPackageInstall
# ---------------------------------------------------------------------------


class TestPackageInstall:
    async def test_install_valid_package_name(self, sandbox_client):
        """POST with a valid package name returns 200 with expected structure.

        The actual pip install may fail (no pip in the temp dir sandbox) but
        the endpoint itself should not crash and should return a well-formed
        response.
        """
        client, _sandbox = sandbox_client

        resp = await client.post(
            f"{BASE}/packages",
            json={"packages": ["requests"]},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "success" in body
        assert "installed" in body and isinstance(body["installed"], list)
        assert "output" in body

    async def test_install_invalid_package_name(self, sandbox_client):
        """POST with a path-traversal package name returns 400."""
        client, _sandbox = sandbox_client

        resp = await client.post(
            f"{BASE}/packages",
            json={"packages": ["../../etc/passwd"]},
        )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    async def test_install_empty_packages(self, sandbox_client):
        """POST with an empty packages list returns 422 (pydantic validation)."""
        client, _sandbox = sandbox_client

        resp = await client.post(
            f"{BASE}/packages",
            json={"packages": []},
        )
        assert resp.status_code == 422
