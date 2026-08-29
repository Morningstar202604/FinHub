"""Contract tests for SandboxRuntime file operations."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio(loop_scope="class")
class TestRuntimeFileIO:
    """SandboxRuntime file operations: upload, download, list, batch upload."""

    async def test_upload_and_download(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        content = b"Hello, sandbox!"
        async with timed("file_io", "upload_and_download"):
            await shared_runtime.upload_file(content, f"{wd}/fio_test.txt")
            downloaded = await shared_runtime.download_file(f"{wd}/fio_test.txt")
        assert downloaded == content

    async def test_upload_creates_parent_dirs(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        async with timed("file_io", "nested_upload"):
            await shared_runtime.upload_file(b"nested", f"{wd}/fio_a/b/c/deep.txt")
        content = await shared_runtime.download_file(f"{wd}/fio_a/b/c/deep.txt")
        assert content == b"nested"

    async def test_download_nonexistent_raises(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        async with timed("file_io", "download_nonexistent"):
            with pytest.raises((FileNotFoundError, Exception)):
                await shared_runtime.download_file(f"{wd}/nonexistent_xyz.txt")

    async def test_upload_overwrite(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        async with timed("file_io", "overwrite"):
            await shared_runtime.upload_file(b"version1", f"{wd}/fio_data.txt")
            await shared_runtime.upload_file(b"version2", f"{wd}/fio_data.txt")
        content = await shared_runtime.download_file(f"{wd}/fio_data.txt")
        assert content == b"version2"

    async def test_upload_binary(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        binary_data = bytes(range(256))
        async with timed("file_io", "binary"):
            await shared_runtime.upload_file(binary_data, f"{wd}/fio_binary.bin")
            downloaded = await shared_runtime.download_file(f"{wd}/fio_binary.bin")
        assert downloaded == binary_data

    async def test_upload_files_batch(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        files = [
            (b"content_a", f"{wd}/fio_batch/a.txt"),
            (b"content_b", f"{wd}/fio_batch/b.txt"),
            (b"content_c", f"{wd}/fio_batch/c.txt"),
        ]
        async with timed("file_io", "batch_upload"):
            await shared_runtime.upload_files(files)

        for content, path in files:
            downloaded = await shared_runtime.download_file(path)
            assert downloaded == content

    async def test_list_files(self, shared_runtime, timed):
        wd = await shared_runtime.fetch_working_dir()
        await shared_runtime.upload_file(b"a", f"{wd}/fio_listdir/file1.txt")
        await shared_runtime.upload_file(b"b", f"{wd}/fio_listdir/file2.txt")
        await shared_runtime.exec(f"mkdir -p {wd}/fio_listdir/subdir")

        async with timed("file_io", "list_files"):
            entries = await shared_runtime.list_files(f"{wd}/fio_listdir")

        def _get_name(e):
            """Extract name from entry -- handles both dict and object."""
            if isinstance(e, dict):
                return e.get("name", "")
            return getattr(e, "name", str(e))

        names = {_get_name(e) for e in entries}
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subdir" in names

    async def test_large_file(self, shared_runtime, timed):
        """Test file I/O with a 1MB file."""
        wd = await shared_runtime.fetch_working_dir()
        large_content = b"x" * (1024 * 1024)
        async with timed("file_io", "large_file"):
            await shared_runtime.upload_file(large_content, f"{wd}/fio_large.bin")
            downloaded = await shared_runtime.download_file(f"{wd}/fio_large.bin")
        assert len(downloaded) == len(large_content)
        assert downloaded == large_content
