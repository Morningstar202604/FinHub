from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestPathNormalization:
    """PTCSandbox path normalization and validation (sync -- no asyncio mark)."""

    def test_normalize_dot(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path(".") == wd

    def test_normalize_empty(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path("") == wd

    def test_normalize_slash(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path("/") == wd

    def test_normalize_relative(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path("data/file.txt") == f"{wd}/data/file.txt"

    def test_normalize_virtual_absolute(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path("/results/out.txt") == f"{wd}/results/out.txt"

    def test_normalize_already_absolute(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.normalize_path(f"{wd}/data/x.txt") == f"{wd}/data/x.txt"

    def test_normalize_tmp(self, shared_sandbox):
        assert shared_sandbox.normalize_path("/tmp/file.txt") == "/tmp/file.txt"

    def test_virtualize_path(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.virtualize_path(f"{wd}/data/x.txt") == "/data/x.txt"
        assert shared_sandbox.virtualize_path(wd) == "/"
        assert shared_sandbox.virtualize_path("/tmp/x.txt") == "/tmp/x.txt"

    def test_validate_allowed(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        assert shared_sandbox.validate_path(f"{wd}/data/x.txt") is True
        assert shared_sandbox.validate_path("/tmp/x.txt") is True

    def test_validate_denied(self, shared_sandbox):
        wd = shared_sandbox.config.filesystem.working_directory
        # Add a denied directory to test denial
        shared_sandbox.config.filesystem.denied_directories = [f"{wd}/_internal"]
        assert shared_sandbox.validate_path(f"{wd}/_internal/secret.txt") is False
        assert shared_sandbox.validate_path(f"{wd}/data/ok.txt") is True
        # Restore
        shared_sandbox.config.filesystem.denied_directories = []
