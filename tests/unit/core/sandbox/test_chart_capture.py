"""Unit tests for shared chart capture module.

Tests build_code_wrapper() and extract_artifacts() from the _chart_capture module
which is shared by MemoryRuntime and DockerRuntime.
"""

import pytest

from ptc_agent.core.sandbox.providers._chart_capture import (
    build_code_wrapper,
    extract_artifacts,
)
from ptc_agent.core.sandbox.runtime import Artifact


# ---------------------------------------------------------------------------
# build_code_wrapper
# ---------------------------------------------------------------------------


class TestBuildCodeWrapper:
    def test_wraps_user_code(self):
        """User code should appear in the wrapper."""
        wrapped = build_code_wrapper("print('hello')")
        assert "print('hello')" in wrapped

    def test_wrapper_is_valid_python(self):
        """The generated wrapper should be valid Python syntax."""
        wrapped = build_code_wrapper("x = 1 + 2")
        compile(wrapped, "<test>", "exec")

    def test_includes_matplotlib_patch(self):
        """Wrapper should include matplotlib monkey-patch code."""
        wrapped = build_code_wrapper("pass")
        assert "matplotlib" in wrapped
        assert "__CHART_ARTIFACT__" in wrapped
        assert "_capture_show" in wrapped

    def test_multiline_code(self):
        """Multi-line user code should be fully included."""
        code = "x = 1\ny = 2\nprint(x + y)"
        wrapped = build_code_wrapper(code)
        assert "x = 1" in wrapped
        assert "y = 2" in wrapped
        assert "print(x + y)" in wrapped

    def test_empty_code(self):
        """Empty string should still produce valid wrapper."""
        wrapped = build_code_wrapper("")
        compile(wrapped, "<test>", "exec")

    def test_code_with_imports(self):
        """User code with imports should appear after the wrapper preamble."""
        code = "import json\nprint(json.dumps({'a': 1}))"
        wrapped = build_code_wrapper(code)
        assert "import json" in wrapped
        compile(wrapped, "<test>", "exec")

    def test_sets_agg_backend(self):
        """Wrapper should set matplotlib to Agg (non-interactive) backend."""
        wrapped = build_code_wrapper("pass")
        assert "matplotlib.use('Agg')" in wrapped

    def test_replaces_plt_show(self):
        """Wrapper should replace plt.show with the capture function."""
        wrapped = build_code_wrapper("pass")
        assert "plt.show = _capture_show" in wrapped

    def test_handles_import_error(self):
        """Wrapper should gracefully handle missing matplotlib (try/except)."""
        wrapped = build_code_wrapper("pass")
        assert "except ImportError" in wrapped


# ---------------------------------------------------------------------------
# extract_artifacts
# ---------------------------------------------------------------------------


class TestExtractArtifacts:
    def test_no_artifacts_returns_empty(self):
        """Plain stdout with no markers should yield no artifacts."""
        artifacts, clean = extract_artifacts("hello\nworld")
        assert artifacts == []
        assert "hello" in clean
        assert "world" in clean

    def test_single_artifact(self):
        """A single __CHART_ARTIFACT__ marker should be extracted."""
        stdout = "output\n__CHART_ARTIFACT__:image/png:chart_1.png:ABCD==\nmore output"
        artifacts, clean = extract_artifacts(stdout)
        assert len(artifacts) == 1
        assert artifacts[0].type == "image/png"
        assert artifacts[0].name == "chart_1.png"
        assert artifacts[0].data == "ABCD=="
        assert "__CHART_ARTIFACT__" not in clean
        assert "output" in clean
        assert "more output" in clean

    def test_multiple_artifacts(self):
        """Multiple __CHART_ARTIFACT__ markers should all be extracted."""
        stdout = "__CHART_ARTIFACT__:image/png:a.png:AAA\ntext\n__CHART_ARTIFACT__:image/png:b.png:BBB"
        artifacts, clean = extract_artifacts(stdout)
        assert len(artifacts) == 2
        assert artifacts[0].name == "a.png"
        assert artifacts[1].name == "b.png"
        assert "text" in clean

    def test_empty_stdout(self):
        """Empty stdout should yield no artifacts and empty clean output."""
        artifacts, clean = extract_artifacts("")
        assert artifacts == []

    def test_only_artifacts_no_other_output(self):
        """When stdout is only artifact markers, clean output should be empty/whitespace."""
        stdout = "__CHART_ARTIFACT__:image/png:chart.png:DATA"
        artifacts, clean = extract_artifacts(stdout)
        assert len(artifacts) == 1
        assert clean.strip() == ""

    def test_artifact_has_correct_type(self):
        """Extracted artifacts should be Artifact dataclass instances."""
        stdout = "__CHART_ARTIFACT__:image/png:test.png:BASE64DATA"
        artifacts, _ = extract_artifacts(stdout)
        assert len(artifacts) == 1
        assert isinstance(artifacts[0], Artifact)

    def test_artifact_data_with_colons(self):
        """The data portion (4th field) should capture everything after the 3rd colon."""
        # base64 data can contain characters like + / = but not colons normally,
        # but the split(":", 3) should handle it correctly
        stdout = "__CHART_ARTIFACT__:image/png:chart.png:ABC:DEF:GHI"
        artifacts, _ = extract_artifacts(stdout)
        assert len(artifacts) == 1
        # split(":", 3) means: _, mime, name, data = parts
        # data should be "ABC:DEF:GHI"
        assert artifacts[0].data == "ABC:DEF:GHI"

    def test_preserves_line_order(self):
        """Clean output should preserve the order of non-artifact lines."""
        stdout = "line1\n__CHART_ARTIFACT__:image/png:x.png:DATA\nline2\nline3"
        _, clean = extract_artifacts(stdout)
        lines = [l for l in clean.split("\n") if l.strip()]
        assert lines == ["line1", "line2", "line3"]

    def test_malformed_marker_not_enough_parts(self):
        """A malformed marker with fewer than 4 parts is silently dropped."""
        stdout = "__CHART_ARTIFACT__:image/png:incomplete\nreal output"
        artifacts, clean = extract_artifacts(stdout)
        # Only 3 parts after split, so it should NOT be extracted as artifact
        assert len(artifacts) == 0
        # Malformed markers are silently dropped from clean output
        assert "__CHART_ARTIFACT__" not in clean

    def test_artifact_preserves_whitespace_in_surrounding_lines(self):
        """Whitespace in non-artifact lines should be preserved."""
        stdout = "  indented\n__CHART_ARTIFACT__:image/png:x.png:D\n  also indented"
        _, clean = extract_artifacts(stdout)
        assert "  indented" in clean
        assert "  also indented" in clean
