"""Tests for ``handle_api_exceptions``.

This decorator is the reference implementation of the rule that
``scripts/guard/error_leak_guard.py`` enforces: on a catch-all branch the
exception text is logged and dropped, never echoed. It had zero call sites and
zero tests when it was found, which is a bad combination — an untested
abstraction that nobody has exercised is not obviously correct, and it is the
one place a future author is most likely to copy from.

The test that matters is ``test_driver_error_text_is_logged_not_echoed``. It
asserts both halves of the contract, because asserting only the response would
pass for a decorator that simply discarded the exception, and a failure nobody
can diagnose is its own bug.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from src.server.utils.api import handle_api_exceptions


@pytest.fixture()
def log():
    return logging.getLogger("test.handle_api_exceptions")


@pytest.mark.asyncio
async def test_http_exception_passes_through_unchanged(log):
    """An explicit HTTP status is a deliberate choice; it must not be rewritten."""

    @handle_api_exceptions("do the thing", log)
    async def f():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    with pytest.raises(HTTPException) as exc:
        await f()
    assert exc.value.status_code == 418
    assert exc.value.detail == "I'm a teapot"


@pytest.mark.asyncio
async def test_value_error_becomes_scrubbed_409_when_opted_in(log):
    @handle_api_exceptions("create workspace", log, conflict_on_value_error=True)
    async def f():
        raise ValueError("Workspace X not found")

    with pytest.raises(HTTPException) as exc:
        await f()
    assert exc.value.status_code == 409
    assert exc.value.detail == "Workspace X not found"


@pytest.mark.asyncio
async def test_value_error_is_reraised_when_not_opted_in(log):
    """Not every route wants a 409; the flag must actually gate it."""

    @handle_api_exceptions("create workspace", log)
    async def f():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await f()


@pytest.mark.asyncio
async def test_driver_error_text_is_logged_not_echoed(log, caplog):
    """The contract, both halves.

    A psycopg connection failure carries the host, the port and the database
    name. The user is not entitled to any of it, but the on-call engineer is —
    so it must reach the log and must not reach the response.
    """
    dsn = "postgresql://svc:hunter2@db.internal:5432/finhub"

    @handle_api_exceptions("open the ledger", log)
    async def f():
        raise RuntimeError(f"connection refused: {dsn}")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc:
            await f()

    assert exc.value.status_code == 500
    # The response carries the action, not the cause.
    assert exc.value.detail == "Failed to open the ledger"
    assert "db.internal" not in exc.value.detail
    assert "hunter2" not in exc.value.detail

    # ...and the cause is still recoverable server-side.
    assert any("db.internal" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_credential_in_the_message_is_scrubbed_from_the_log_too(log, caplog):
    """The log is not a safe sink either — it is scrubbed, not raw.

    Logs get shipped, aggregated and read by people who should not see a
    password. Scrubbing there is why the decorator calls
    ``sanitize_error_text`` on the way to ``logger.exception`` as well.
    """
    @handle_api_exceptions("call the provider", log)
    async def f():
        raise RuntimeError("Authorization: Bearer sk-NOTAREALKEY1234567890 failed")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException):
            await f()

    messages = [r.getMessage() for r in caplog.records]
    assert any("REDACTED" in m for m in messages), messages
    assert not any("sk-NOTAREALKEY1234567890" in m for m in messages), messages


@pytest.mark.asyncio
async def test_return_value_and_signature_survive(log):
    """FastAPI builds its dependency graph from the signature; break it and DI breaks."""
    import inspect

    @handle_api_exceptions("fetch", log)
    async def f(workspace_id: str, *, user_id: str | None = None) -> int:
        return 42

    assert await f("ws-1", user_id="u-1") == 42
    params = inspect.signature(f).parameters
    assert list(params) == ["workspace_id", "user_id"]
