"""Tests for scripts/guard/error_leak_guard.py.

The guard's job is to tell two look-alike things apart:

* a **catch-all** handler (`except Exception`) putting its exception text into a
  client-facing field — the leak, and
* a **narrow** handler (`except InvalidStoreKeyError`) doing the same — the
  message is authored here and the caller needs it.

If it ever stops distinguishing those, it either lets leaks through or starts
demanding nonsense in unrelated files. Both directions are tested, on synthetic
trees, because the real repo is currently green and a green run proves nothing
about detection.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GUARD_PATH = REPO / "scripts" / "guard" / "error_leak_guard.py"


def _load_guard():
    """Import the guard without adding scripts/ to sys.path."""
    spec = importlib.util.spec_from_file_location("error_leak_guard", GUARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["error_leak_guard"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def guard():
    return _load_guard()


def _scan(guard, body: str, tmp_path: Path) -> list[str]:
    """Run the guard over a single synthetic module."""
    root = tmp_path / "repo"
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "route.py").write_text(body, encoding="utf-8")

    original = guard.SRC
    guard.SRC = root / "src"
    guard.REPO = root
    try:
        return guard.scan()
    finally:
        guard.SRC = original


class TestDetectsLeaks:
    """Every spelling that reaches a client field must be caught."""

    def test_fstring_interpolation_of_bound_name(self, guard, tmp_path):
        """The variant a naive `detail=str(e)` grep misses entirely."""
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        raise HTTPException(status_code=500, detail=f'boom: {e}')\n",
            tmp_path,
        )
        assert len(found) == 1
        assert 'f"{e}"' in found[0]

    def test_str_call_form(self, guard, tmp_path):
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        raise HTTPException(status_code=500, detail=str(e))\n",
            tmp_path,
        )
        assert len(found) == 1
        assert "str(e)" in found[0]

    def test_different_binding_name(self, guard, tmp_path):
        """`except ... as exc` must not slip through a hardcoded-`e` scan."""
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as exc:\n"
            "        raise HTTPException(status_code=500, detail=f'boom: {exc}')\n",
            tmp_path,
        )
        assert len(found) == 1

    def test_dict_shaped_detail(self, guard, tmp_path):
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        raise HTTPException(422, detail={'message': str(e)})\n",
            tmp_path,
        )
        assert len(found) == 1

    def test_bare_except_counts_as_catch_all(self, guard, tmp_path):
        """`except:` is the widest form of the same hazard."""
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except e:\n"
            "        raise HTTPException(500, detail=f'{e}')\n".replace(
                "except e:", "except Exception as e:"
            ),
            tmp_path,
        )
        assert len(found) == 1

    def test_reason_field_on_report_component(self, guard, tmp_path):
        """The plugin install report is rendered verbatim by the client."""
        found = _scan(
            guard,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        return _over_cap(reason=f'failed: {e}')\n",
            tmp_path,
        )
        assert len(found) == 1
        assert "reason=" in found[0]

    def test_hand_built_response_dict_in_a_route(self, guard, tmp_path):
        """A route can return a dict instead of raising — same wire, same rule.

        This is how the leak on the unauthenticated /health endpoint read:
        ``result["checkpointer"] = {"status": "error", "error": str(e)}``.
        """
        found = _scan(
            guard,
            "@router.get('/health')\n"
            "async def health_check():\n"
            "    result = {}\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        result['checkpointer'] = {'status': 'error', 'error': str(e)}\n"
            "    return result\n",
            tmp_path,
        )
        assert len(found) == 1
        assert "error" in found[0]
        assert "health_check" in found[0]


class TestDoesNotOverReport:
    """Legitimate patterns must stay silent, or the guard gets muted."""

    def test_narrow_exception_type_is_allowed(self, guard, tmp_path):
        """An authored message the caller needs to act on."""
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except InvalidStoreKeyError as exc:\n"
            "        raise HTTPException(status_code=400, detail=f'Invalid key: {exc}')\n",
            tmp_path,
        )
        assert found == []

    def test_scrubbed_value_is_allowed(self, guard, tmp_path):
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        raise HTTPException(status_code=400, detail=sanitize_error_text(str(e)))\n",
            tmp_path,
        )
        assert found == []

    def test_logger_binding_is_not_a_client_field(self, guard, tmp_path):
        """structlog `reason=` is a log field; only response constructors count."""
        found = _scan(
            guard,
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        logger.warning('rejected', reason=str(e))\n",
            tmp_path,
        )
        assert found == []

    def test_response_attribute_is_not_the_exception_message(self, guard, tmp_path):
        """`e.response.status_code` is an int and leaks nothing."""
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except HTTPStatusError as e:\n"
            "        raise HTTPException(\n"
            "            status_code=502, detail=f'Provider returned {e.response.status_code}'\n"
            "        )\n",
            tmp_path,
        )
        assert found == []

    def test_static_detail_is_allowed(self, guard, tmp_path):
        found = _scan(
            guard,
            "from fastapi import HTTPException\n\n\n"
            "async def f():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        raise HTTPException(status_code=500, detail='Failed to do the thing')\n",
            tmp_path,
        )
        assert found == []

    def test_tool_result_dict_outside_a_route_is_allowed(self, guard, tmp_path):
        """A tool result is read by the agent, not by an HTTP client.

        The agent cannot recover from a failure whose cause it is never shown,
        so this shape must stay permitted — and it is why the dict check is
        scoped to functions carrying a route decorator.
        """
        found = _scan(
            guard,
            "async def run_tool():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as exc:\n"
            "        return {'success': False, 'error': str(exc)}\n",
            tmp_path,
        )
        assert found == []


    def test_response_model_keyword_in_a_route(self, guard, tmp_path):
        """A response model built by keyword is not a `detail=` and not a dict.

        Found on a real route: ``PackageInstallResponse(..., error=str(e))``.
        Neither the keyword-only check nor the dict check sees it, which is why
        ``error`` had to join the client-facing field set.
        """
        found = _scan(
            guard,
            "@router.post('/{workspace_id}/sandbox/packages')\n"
            "async def install_sandbox_packages():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        return PackageInstallResponse(success=False, error=str(e))\n",
            tmp_path,
        )
        assert len(found) == 1
        assert "PackageInstallResponse" in found[0]


class TestAllowlistStaleness:
    def test_vanished_file_is_reported(self, guard, tmp_path, monkeypatch):
        monkeypatch.setattr(guard, "REPO", tmp_path)
        monkeypatch.setattr(
            guard, "_ALLOW", {"src/gone.py:1": "was justified once'"}
        )
        errors = guard.check_allowlist_staleness()
        assert len(errors) == 1
        assert "STALE allowance" in errors[0]


class TestRealTree:
    def test_production_is_clean(self):
        """The real src/ must have no catch-all leak."""
        module = _load_guard()
        assert module.scan() == [], (
            "a catch-all handler is putting exception text on the wire; "
            "run `python scripts/guard/error_leak_guard.py --list` for the list"
        )
