"""The sse-upgrade probe handles a URL a *package author* chose.

That makes the probe's failure text untrusted input: it names the host, port
and path that were just reached, so whatever lands in ``ProbeResult.detail``
must not carry the exception message. These tests pin that boundary, plus the
three verdicts the probe exists to distinguish (reachable / auth-challenged /
dead) and the two caps that bound the phase.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.plugins.probe import (
    MAX_CONCURRENT_PROBES,
    MAX_PROBED_ENTRIES,
    _client_safe,
    _is_auth_challenge,
    probe_all,
    probe_streamable_http,
)

# A realistic transport failure: everything an operator would want (and an
# attacker would love to read back) is in here.
_HOSTY = "connect failed to https://evil.example.com:8443/mcp (timeout 10s)"


def _async_cm(value):
    """An ``async with`` guard that yields *value* and swallows nothing."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _client_that_raises(exc: BaseException):
    """An MCP client whose ``list_tools`` fails — i.e. the probe's own timeout."""
    client = MagicMock()
    client.list_tools = AsyncMock(side_effect=exc)
    return client


# ---------------------------------------------------------------------------
# _client_safe — the client-facing boundary
# ---------------------------------------------------------------------------


def test_client_safe_keeps_the_class():
    """The class is still diagnostic: refused vs timed out vs wanted auth."""
    assert _client_safe(ConnectionRefusedError("nope")) == "ConnectionRefusedError"


@pytest.mark.parametrize("secret", ["db.internal", "8443", "/mcp", "hunter2"])
def test_client_safe_drops_every_part_of_the_probed_address(secret: str):
    """Host, port, path and credentials are all attacker-chosen material.

    Sanitising the message is not enough here — the scrubber masks credential
    *shapes*, and a bare ``https://host:8443/mcp`` is not one, so it would
    survive untouched. Nothing but the class may travel.
    """
    exc = RuntimeError("postgresql://svc:hunter2@db.internal:8443/mcp refused")
    assert secret not in _client_safe(exc)


def test_client_safe_on_a_bare_url_message():
    """The shape that actually occurs: no userinfo for the scrubber to find."""
    assert _client_safe(OSError(_HOSTY)) == "OSError"


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def test_auth_challenge_counts_as_success():
    """401/403 proves a streamable-HTTP listener; creds are the connector's job."""
    assert _is_auth_challenge(Exception("HTTP 401 unauthorized"))
    assert _is_auth_challenge(Exception("403 forbidden"))
    assert not _is_auth_challenge(Exception("500 boom"))


@pytest.mark.asyncio
async def test_blocked_url_reports_the_class_and_nothing_else():
    """The egress guard's reason names the resolved address — it stays server-side."""
    boom = ValueError("resolves to 10.0.0.7 which is not public")
    with patch(
        "src.server.services.plugins.probe.pin_public_url",
        AsyncMock(side_effect=boom),
    ):
        result = await probe_streamable_http("k", "http://evil.example.com/mcp")

    assert result.ok is False
    assert result.detail == "blocked url: ValueError"
    for leak in ("10.0.0.7", "evil.example.com", "not public"):
        assert leak not in result.detail


@pytest.mark.asyncio
async def test_auth_challenge_is_reported_as_upgradable():
    with (
        patch("src.server.services.plugins.probe.pin_public_url", AsyncMock()),
        patch(
            "src.server.services.plugins.probe.pinned_discovery_client",
            MagicMock(),
        ),
        patch(
            "src.server.services.plugins.probe.streamable_http_client",
            MagicMock(side_effect=Exception("HTTP 401 unauthorized")),
        ),
    ):
        result = await probe_streamable_http("k", "https://example.com/mcp")

    assert result.ok is True
    assert "authentication" in result.detail


@pytest.mark.asyncio
async def test_timeout_is_reported_with_a_reason():
    """A bare TimeoutError stringifies empty; the caps exist to produce it,
    so it must not come back as an unexplained failure."""
    with (
        patch("src.server.services.plugins.probe.pin_public_url", AsyncMock()),
        patch(
            "src.server.services.plugins.probe.pinned_discovery_client",
            MagicMock(return_value=_async_cm(MagicMock())),
        ),
        patch("src.server.services.plugins.probe.streamable_http_client", MagicMock()),
        patch(
            "src.server.services.plugins.probe.Client",
            MagicMock(return_value=_async_cm(_client_that_raises(TimeoutError()))),
        ),
    ):
        result = await probe_streamable_http("k", "https://slow.example.com/mcp")

    assert result.ok is False
    assert "within" in result.detail


@pytest.mark.asyncio
async def test_unreachable_endpoint_leaks_no_host():
    with (
        patch("src.server.services.plugins.probe.pin_public_url", AsyncMock()),
        patch(
            "src.server.services.plugins.probe.pinned_discovery_client",
            MagicMock(),
        ),
        patch(
            "src.server.services.plugins.probe.streamable_http_client",
            MagicMock(side_effect=OSError(_HOSTY)),
        ),
    ):
        result = await probe_streamable_http("k", "https://evil.example.com/mcp")

    assert result.ok is False
    assert result.detail == "OSError"
    assert "evil.example.com" not in result.detail


# ---------------------------------------------------------------------------
# probe_all — bounds, and entries past the cap are still reported
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entries_past_the_cap_are_reported_not_dropped():
    entries = [(f"k{i}", "https://example.com/mcp") for i in range(MAX_PROBED_ENTRIES + 3)]

    with patch(
        "src.server.services.plugins.probe.probe_streamable_http",
        AsyncMock(return_value=MagicMock(ok=True, detail="")),
    ):
        results = await probe_all(entries)

    assert len(results) == len(entries)
    assert [r for r in results if r.ok]
    over = [r for r in results if "not probed" in r.detail]
    assert len(over) == 3
    assert all(not r.ok for r in over)


@pytest.mark.asyncio
async def test_concurrency_is_bounded():
    """One package controls how many endpoints get probed; the semaphore is
    what keeps a stall from holding unbounded sockets."""
    seen = 0
    peak = 0

    async def slow(_key, _url):
        nonlocal seen, peak
        seen += 1
        peak = max(peak, seen)
        await asyncio.sleep(0)
        seen -= 1
        return MagicMock(ok=True, detail="")

    entries = [(f"k{i}", "https://example.com/mcp") for i in range(MAX_CONCURRENT_PROBES * 3)]
    with patch("src.server.services.plugins.probe.probe_streamable_http", slow):
        await probe_all(entries)

    assert peak <= MAX_CONCURRENT_PROBES
