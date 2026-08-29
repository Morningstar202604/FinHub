from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="class")]


class TestTokenUpload:
    """PTCSandbox.upload_token_file() -- token file lifecycle."""

    async def test_upload_tokens(self, shared_sandbox):
        tokens = {
            "access_token": "gxsa_test_access",
            "refresh_token": "gxsr_test_refresh",
            "client_id": "test-client",
        }
        await shared_sandbox.upload_token_file(tokens)

        # Read back from the sandbox using the same path constant
        token_path = f"{shared_sandbox._work_dir}/_internal/.mcp_tokens.json"
        content = await shared_sandbox.runtime.download_file(token_path)
        assert content is not None
        data = json.loads(content)
        assert data["access_token"] == "gxsa_test_access"
        assert data["refresh_token"] == "gxsr_test_refresh"
        assert data["client_id"] == "test-client"
        assert "auth_service_url" in data
        assert "ginlix_data_url" in data

    async def test_token_overwrite(self, shared_sandbox):
        """Uploading tokens again should overwrite the file."""
        await shared_sandbox.upload_token_file({"access_token": "v1", "refresh_token": "r1", "client_id": "c1"})
        await shared_sandbox.upload_token_file({"access_token": "v2", "refresh_token": "r2", "client_id": "c2"})

        token_path = f"{shared_sandbox._work_dir}/_internal/.mcp_tokens.json"
        content = await shared_sandbox.runtime.download_file(token_path)
        data = json.loads(content)
        assert data["access_token"] == "v2"


class TestManifest:
    """PTCSandbox manifest lifecycle -- write, read, and sync detection."""

    async def test_write_and_read_manifest(self, shared_sandbox):
        # Compute and write
        manifest = await shared_sandbox._compute_sandbox_manifest()
        await shared_sandbox._write_unified_manifest(manifest)

        # Read back
        remote = await shared_sandbox._read_unified_manifest()
        assert remote is not None
        assert remote.get("schema_version") == 1
        assert "modules" in remote

    async def test_manifest_versioning(self, shared_sandbox):
        """Two consecutive manifests should have matching versions when
        nothing changed."""
        m1 = await shared_sandbox._compute_sandbox_manifest()
        m2 = await shared_sandbox._compute_sandbox_manifest()

        # Module versions should match for same config
        for module_name in m1.get("modules", {}):
            v1 = m1["modules"][module_name].get("version")
            v2 = m2["modules"][module_name].get("version")
            if v1 is not None:
                assert v1 == v2, f"Module {module_name} version mismatch"
