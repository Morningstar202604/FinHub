"""M4-4: evals report endpoint — read-only dashboard data source.

Protects two contract points: the endpoint serves ``evals/runs/latest.json``
(pure read, never re-runs the harness, no arbitrary path resolution) and
degrades to 404 with a stable code when the report doesn't exist yet.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.server.app import evals_report


def _fake_json(payload: dict) -> object:
    class _FakePath:
        def exists(self) -> bool:
            return True

        def read_text(self, encoding: str = "utf-8") -> str:
            return json.dumps(payload)

    return _FakePath()


@pytest.mark.asyncio
@pytest.mark.enable_inet_socket
async def test_serves_latest_report_when_exists():
    payload = {
        "ok": True,
        "passed": 10,
        "total": 10,
        "suites": {"intent": {"passed": 5, "total": 5}},
        "detail": ["- [PASS] hi"],
    }
    with patch.object(evals_report, "_LATEST_JSON", _fake_json(payload)):
        resp = await evals_report.get_evals_report()

    body = json.loads(resp.body.decode("utf-8"))
    assert resp.media_type == "application/json"
    assert body["ok"] is True
    assert body["suites"]["intent"]["passed"] == 5


@pytest.mark.asyncio
@pytest.mark.enable_inet_socket
async def test_404_with_stable_code_when_missing():
    class _Missing:
        def exists(self) -> bool:
            return False

    with patch.object(evals_report, "_LATEST_JSON", _Missing()):
        with pytest.raises(HTTPException) as ei:
            await evals_report.get_evals_report()

    assert ei.value.status_code == 404
    assert isinstance(ei.value.detail, dict)
    assert ei.value.detail["code"] == "no_evals_report"