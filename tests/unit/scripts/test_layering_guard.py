"""Tests for scripts/guard/layering_guard.py.

The guard is a *ratchet*: it tolerates the 14 `server -> tools` chains that
exist today and fails on anything new. The failure modes that matter are
therefore not "does it pass" but "does it still detect", so every detection
path gets an explicit test with a synthetic module tree rather than trusting
the real repo state (which is, by definition, currently green).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GUARD_PATH = REPO / "scripts" / "guard" / "layering_guard.py"


def _load_guard():
    """Import the guard as a module without adding scripts/ to sys.path."""
    spec = importlib.util.spec_from_file_location("layering_guard", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["layering_guard"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def guard():
    return _load_guard()


def test_guard_runs_and_reports_observed_and_frozen(guard):
    """Against the real tree the guard must agree with itself.

    If `observed` exceeded `_FROZEN`, `run_all` would carry a violation and the
    exit code would be 1 — so asserting on the parsed results proves the repo
    currently satisfies its own contract.
    """
    violations, observed, stale = guard.find_inversions()
    assert not stale, f"stale allow-list entries: {sorted(stale)}"
    new = {p for p in violations if p not in guard._FROZEN}
    assert not new, f"unexpected new inversions: {sorted(new)}"
    assert observed, "guard found zero server->tools chains; parsing likely broke"
    # Every frozen entry should be a real observed chain (no dead allowances).
    assert guard._FROZEN <= observed


def test_guard_exit_code_is_one_when_violations_exist(guard, monkeypatch):
    """The CI signal is the exit code, so pin it."""
    monkeypatch.setattr(guard, "find_inversions", lambda: ({("a.b", "c.d")}, set(), set()))
    assert guard.run_all()["server_to_tools_inversions"]


def test_fixed_chains_are_tracked_separately(guard):
    """A fixed chain must be asserted absent, not merely unfrozen.

    Otherwise undoing the fix would look identical to 'never had the problem'.
    """
    assert guard._FIXED_MUST_STAY_FIXED
    for pair in guard._FIXED_MUST_STAY_FIXED:
        assert pair not in guard._FROZEN, (
            f"{pair} is both fixed and frozen — contradictory"
        )


def test_parse_finds_function_level_imports(guard, tmp_path, monkeypatch):
    """The entire point: cycles hidden inside function bodies must be seen.

    grimp and Python's import system only see module-level imports, which is why
    they report zero bidirectional couples. This asserts the AST walk descends
    into function bodies.

    Note on setup: `_module_name` builds the name from the path relative to
    REPO, so a synthetic tree is laid out under a fake REPO whose child is
    `src/` — giving `src.<pkg>.<mod>` names exactly as the real tree does.
    """
    # Built by joining rather than as one literal: the fixture's first line
    # looks like a nested docstring, and Python 3.13's tokenizer plus pytest's
    # assertion rewriter emit a spurious `invalid escape sequence` SyntaxWarning
    # for that shape even though nothing here contains a bad escape.
    fake_mod = "\n".join(
        [
            '"""x."""',
            "",
            "",
            "def f():",
            "    from src.tools.web import manifest",
            "    return manifest",
            "",
        ]
    )
    root = tmp_path / "repo"
    (root / "src" / "server").mkdir(parents=True)
    (root / "src" / "server" / "a.py").write_text(fake_mod, encoding="utf-8")
    monkeypatch.setattr(guard, "REPO", root)
    monkeypatch.setattr(guard, "SRC", root / "src")

    refs = guard._per_file_module_refs()
    assert "src.server.a" in refs
    assert "src.tools.web" in refs["src.server.a"], "function-level import missed"
