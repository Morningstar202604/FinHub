"""What ``sanitize_error_text`` must scrub before exception text is delivered."""

from __future__ import annotations

import pytest

from src.server.utils.error_sanitization import sanitize_error_text


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://svc:hunter2@db.example:5432/app",
        "redis://default:s3cret@cache.example:6379/0",
        "amqp://guest:guest@broker.example:5672/",
    ],
)
def test_a_connection_dsn_never_carries_its_password_through(dsn: str) -> None:
    """The exceptions this scrubber exists for are connection failures, and
    those quote a DSN rather than an http(s) URL."""
    scrubbed = sanitize_error_text(f"connection failed: {dsn}")

    assert "hunter2" not in scrubbed
    assert "s3cret" not in scrubbed
    assert ":guest@" not in scrubbed
    # The host survives — it is the diagnostic, and the credential is not.
    assert ".example" in scrubbed


def test_the_scheme_survives_so_the_message_still_reads() -> None:
    assert sanitize_error_text("GET https://u:p@api.example/v1 failed") == (
        "GET https://api.example/v1 failed"
    )


def test_bare_password_key_value_pairs_are_masked() -> None:
    """``password=`` / ``passwd=`` / ``pwd=`` outside a URL query are
    credential-shaped too (provider exceptions echo config dumps)."""
    assert sanitize_error_text("auth failed: password=hunter2hunter2") == (
        "auth failed: password=[REDACTED]"
    )
    assert sanitize_error_text("auth failed: passwd=s3cr3twords") == (
        "auth failed: passwd=[REDACTED]"
    )


def test_password_masking_needs_a_value_shaped_like_a_secret() -> None:
    """Ordinary prose with the word password stays readable; short values
    (below the 8-char secret threshold) pass through unmasked."""
    assert sanitize_error_text("password is required") == "password is required"
    assert sanitize_error_text("passphrase=hunter2 stays") == "passphrase=hunter2 stays"
    assert sanitize_error_text("pwd: short") == "pwd: short"


def test_ordinary_text_with_an_at_sign_is_left_alone() -> None:
    """Only userinfo directly after a scheme is credential-shaped; an address
    or a decorator in a traceback is not."""
    text = "raised in @retry wrapper; contact ops@example.com"

    assert sanitize_error_text(text) == text
