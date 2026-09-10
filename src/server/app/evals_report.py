"""Evals dashboard (M4-4): read-only serving of the last harness report.

The evals harness (``python -m evals run all``) already writes
``evals/runs/latest.json`` — this endpoint just serves it with a bounded cache
so the frontend dashboard doesn't re-run anything and never reads arbitrary
paths. No DB, no mutation; 404 when no report exists yet (CI publishes one as
an artifact on every run).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evals", tags=["Evals"])

# Repo-root-relative, unchanged across dev/CI: ``evals/runs/latest.json``.
_REPORTS_DIR = Path(__file__).resolve().parents[3] / "evals" / "runs"
_LATEST_JSON = _REPORTS_DIR / "latest.json"


def _load_latest() -> dict[str, Any]:
    """Read the latest.json summary; None-safe shape on read errors."""
    try:
        if not _LATEST_JSON.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "no_evals_report",
                    "message": (
                        "No evals report yet. Run `uv run python -m evals run all` "
                        "to produce one."
                    ),
                },
            )
        return json.loads(_LATEST_JSON.read_text(encoding="utf-8"))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to read evals report")
        raise HTTPException(
            status_code=502,
            detail={"code": "evals_report_unreadable", "message": "Report is unreadable."},
        )


@router.get("/report")
async def get_evals_report() -> Response:
    """Serve the latest harness summary as JSON (the dashboard's data source)."""
    data = _load_latest()
    s = json.dumps(data, ensure_ascii=False)
    return Response(
        content=s,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )