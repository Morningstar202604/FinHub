"""Generic sandbox egress relay — grants, sandbox auth, and streaming passthrough.

Sandboxes never hold vendor credentials; they dial ``/v1/egress/{grant_id}``
with a workspace-scoped relay JWT and the relay attaches the credential
host-side per request. MCP OAuth connections are the v1 grant producer; the
resolver layer is the extension point for further credential kinds.
"""

from enum import StrEnum


class RelayError(StrEnum):
    """Every value the relay can put in ``X-Relay-Error``.

    The sandbox-side client keys its user-facing hints off these codes but
    cannot import this module (it runs inside the sandbox, with none of the
    server package available), so the vocabulary is duplicated there by
    necessity. ``tests/unit/core/test_relay_error_hints.py`` is what keeps the
    two in step — extend that hint table whenever a member is added here.
    """

    # prepare_relay
    RELAY_DISABLED = "relay_disabled"
    RELAY_AUTH = "relay_auth"
    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    NEEDS_REAUTH = "needs_reauth"
    METHOD_BLOCKED = "method_blocked"
    TOOL_BLOCKED = "tool_blocked"
    REFRESH_IN_PROGRESS = "refresh_in_progress"
    # open_upstream
    DESTINATION_BLOCKED = "destination_blocked"
    UPSTREAM_UNREACHABLE = "upstream_unreachable"
    VENDOR_REDIRECT = "vendor_redirect"
    # the route's own budgets
    LIMITED_RATE = "limited_rate"
    LIMITED_CONCURRENCY = "limited_concurrency"
    WALL_CLOCK = "wall_clock"


class RelayRejection(Exception):
    """Terminal per-request outcome, mapped by the router to an HTTP answer.

    ``code`` is machine-readable and surfaced as an X-Relay-Error header so
    the generated client (and the agent) can distinguish relay-auth failures
    from vendor-auth failures without parsing bodies. Every rejection the
    pipeline can raise is one of these, so the route needs exactly one arm.
    """

    def __init__(
        self,
        status: int,
        code: RelayError,
        detail: str = "",
        *,
        retry_after: int | None = None,
    ):
        self.status = status
        self.code = RelayError(code)
        self.detail = detail or str(self.code)
        self.retry_after = retry_after
        super().__init__(self.detail)
