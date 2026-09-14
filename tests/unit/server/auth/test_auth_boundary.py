"""Contract tests for the authentication boundary.

``jwt_bearer`` / ``ws_auth`` are the single source of identity for every HTTP
and WebSocket request, and they carry a deliberate "fail open" path
(``HOST_MODE=oss`` returns a fixed local user without looking at any token).
That combination is exactly the kind of code that regresses silently: a wrong
guard does not raise, it just stops checking.

These tests pin the boundary itself — which mode grants what, and what happens
when a token is absent, tampered with, or expired — without needing a live
Supabase. ``_decode_token`` is patched where the network would be hit.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.server.auth import jwt_bearer

# asyncio_mode=strict (see pyproject [tool.pytest.ini_options]) — every async
# test must opt in explicitly.
pytestmark = pytest.mark.asyncio

LOCAL_USER = "local-dev-user"


def _creds(token: str = "header.payload.signature") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def oss_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOST_MODE=oss: authentication is disabled by design."""
    monkeypatch.setattr(jwt_bearer, "HOST_MODE", "oss")
    monkeypatch.setattr(jwt_bearer, "LOCAL_DEV_USER_ID", LOCAL_USER)


@pytest.fixture
def platform_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOST_MODE=platform: every request must carry a verifiable token."""
    monkeypatch.setattr(jwt_bearer, "HOST_MODE", "platform")


class TestOssMode:
    """oss mode must degrade to a fixed user — and ONLY to that."""

    async def test_missing_credentials_still_resolves_to_local_user(self, oss_mode):
        assert await jwt_bearer.verify_jwt_token(None) == LOCAL_USER

    async def test_present_credentials_are_ignored_not_honoured(
        self, oss_mode, monkeypatch
    ):
        """A forged token must not be able to impersonate a real user.

        The dangerous regression is the well-meaning "fix" that decodes the
        token when one is present: that turns a single-tenant install into an
        auth bypass for anyone who can guess a ``sub`` claim.
        """

        def _explode(_token: str):
            raise AssertionError("oss mode must not decode tokens at all")

        monkeypatch.setattr(jwt_bearer, "_decode_token", _explode)
        assert await jwt_bearer.verify_jwt_token(_creds("forged")) == LOCAL_USER

    async def test_auth_info_reports_the_local_user(self, oss_mode):
        info = await jwt_bearer.get_current_auth_info(None)
        assert info.user_id == LOCAL_USER


class TestPlatformMode:
    """platform mode must never resolve an identity without a verified token."""

    async def test_missing_credentials_are_rejected(self, platform_mode):
        with pytest.raises(HTTPException) as exc:
            await jwt_bearer.verify_jwt_token(None)
        assert exc.value.status_code == 401

    async def test_missing_credentials_rejected_for_auth_info(self, platform_mode):
        with pytest.raises(HTTPException) as exc:
            await jwt_bearer.get_current_auth_info(None)
        assert exc.value.status_code == 401

    async def test_valid_token_yields_its_subject(self, platform_mode, monkeypatch):
        monkeypatch.setattr(
            jwt_bearer, "_decode_token", lambda _t: jwt_bearer.AuthInfo("user-abc-123")
        )
        assert await jwt_bearer.verify_jwt_token(_creds()) == "user-abc-123"

    async def test_verification_failure_propagates(self, platform_mode, monkeypatch):
        """A bad signature/expiry must surface, not fall back to a default user."""

        def _reject(_token: str):
            raise HTTPException(status_code=401, detail="Invalid token")

        monkeypatch.setattr(jwt_bearer, "_decode_token", _reject)
        with pytest.raises(HTTPException) as exc:
            await jwt_bearer.verify_jwt_token(_creds("tampered"))
        assert exc.value.status_code == 401

    async def test_auth_info_carries_the_provider(self, platform_mode, monkeypatch):
        monkeypatch.setattr(
            jwt_bearer,
            "_decode_token",
            lambda _t: jwt_bearer.AuthInfo("user-abc-123", auth_provider="supabase"),
        )
        info = await jwt_bearer.get_current_auth_info(_creds())
        assert (info.user_id, info.auth_provider) == ("user-abc-123", "supabase")
