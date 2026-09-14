"""
Shared encryption key helper for pgcrypto-based encryption at rest.

Used by api_keys.py and oauth_tokens.py for pgp_sym_encrypt/decrypt.

Operational constraint — the key is bound as a *query parameter*, never
interpolated into SQL text, so it never appears in application logs. It can
still reach the PostgreSQL server's own log, because ``log_statement=all`` and
``log_min_duration_statement`` record the statement *with its bound parameter
values* (``log_parameter_max_length_on_error`` / ``..._on_sample`` govern how
much). Concretely:

- Keep ``log_statement`` at ``none`` and ``log_min_duration_statement`` at
  ``-1`` in any environment holding real secrets (the shipped compose files
  and .env.example leave both at the safe default).
- If statement logging is genuinely required for diagnosis, enable it only for
  the duration of a session (``SET log_statement``) and never while the vault,
  BYOK-key, or OAuth-token paths are in use.

These tables are the only place where a *decryption* of user secrets happens,
so a parameter-logging misconfiguration here has the widest blast radius.
"""

import os


def get_encryption_key() -> str:
    """Return the symmetric encryption key for data stored at rest."""
    key = os.getenv("BYOK_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "BYOK_ENCRYPTION_KEY environment variable is not set. "
            "Required for encrypting sensitive data at rest."
        )
    return key


def encryption_configured() -> bool:
    """True when the at-rest encryption key is set — i.e. encrypted stores
    (vault secrets, BYOK keys, OAuth tokens) can hold data at all."""
    return bool(os.getenv("BYOK_ENCRYPTION_KEY"))
