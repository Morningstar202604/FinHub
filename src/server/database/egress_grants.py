"""
Database layer for sandbox egress grants — the relay's contract.

A grant binds (user, workspace, credential) to one exact destination captured
at creation. The relay authorizes every request with one query here; grant or
connection status flips deny the next request with no sandbox convergence.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from src.server.database.mcp_oauth import SERVABLE_PARAM
from src.server.database.pool import get_db_connection

logger = logging.getLogger(__name__)

GRANT_KIND_OAUTH_MCP = "oauth_mcp"


@dataclass(frozen=True)
class GrantSync:
    """The workspace's grant set after one convergence.

    ``grants`` maps connection_id → grant_id for every connection that got one;
    ``retired`` counts the overhang that was revoked, which is what tells a
    caller with no local state that a sandbox still has a credential file to
    tear down.
    """

    grants: dict[str, str]
    retired: int


async def sync_oauth_grants(
    *,
    user_id: str,
    workspace_id: str,
    connection_ids: Sequence[str],
    config_version: int,
) -> GrantSync | None:
    """Make ``connection_ids`` exactly this workspace's active OAuth grants.

    One transaction: upsert a grant per connection, then revoke every other
    active grant of the workspace. Retirement is not optional cleanup — an
    active grant the resolved set no longer contains is an authorization
    overhang, since the sandbox may still hold that grant_id and a live relay
    JWT — so it must not be able to commit separately from the upserts.

    The relay dials ``destination_url``, and it is taken from the connection's
    consented ``server_url`` inside the INSERT — never from a caller argument.
    That is the whole security posture: a mutable catalog-row URL can never
    steer a grant at a host the token wasn't issued for. Connections are
    likewise *selected* under the owner predicate rather than trusted, so an id
    that is absent or another user's simply produces no grant (and is then
    retired like any other): a caller that guessed an id learns nothing. That
    same SELECT carries the servable-status predicate, since the upsert's
    ``status = 'active'`` would otherwise reactivate a grant on a connection
    that has since been revoked or needs re-auth.

    Returns None, having touched no grant row, when ``config_version`` no
    longer matches ``workspaces.mcp_config_version`` — the caller resolved
    against a superseded config and a newer sync owns the set. This is a
    whole-set replacement, so two workers cannot be merged by row locks: the
    stale one would reactivate what the fresh one just revoked.
    """
    # Deferred like platform_secret_sweep's: writer_guard reaches back into
    # src.server.database.pool, so importing it at module scope from the
    # database layer would close a database → services → database loop.
    from src.server.services.writer_guard import advisory_key

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            # Serialize this workspace's replacements across workers, THEN
            # re-read the version under that lock. The lock alone would only
            # order a stale writer last; the CAS alone could pass and then be
            # overtaken. Together they make "CAS passed" mean no newer set can
            # commit ahead of this one. Transaction-scoped, so a worker that
            # dies mid-replacement releases it.
            await cur.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (advisory_key("EG", workspace_id),),
            )
            await cur.execute(
                "SELECT mcp_config_version FROM workspaces WHERE workspace_id = %s",
                (workspace_id,),
            )
            ws_row = await cur.fetchone()
            # A workspace that no longer exists matches no version, so it also
            # replaces nothing.
            live_version = ws_row["mcp_config_version"] if ws_row else None
            if live_version != config_version:
                logger.info(
                    f"[egress_grants_db] stale grant replacement for workspace "
                    f"{workspace_id} (resolved v{config_version}, live "
                    f"v{live_version}) — left to the newer sync"
                )
                return None

            granted: dict[str, str] = {}
            if connection_ids:
                await cur.execute(
                    """
                    INSERT INTO sandbox_egress_grants
                        (user_id, workspace_id, kind, connection_id,
                         destination_url, status, created_at, updated_at)
                    SELECT %s, %s::uuid, %s, c.connection_id, c.server_url,
                           'active', NOW(), NOW()
                    FROM user_mcp_oauth_connections c
                    WHERE c.connection_id = ANY(%s::uuid[]) AND c.user_id = %s
                      AND c.status = ANY(%s)
                    ON CONFLICT (workspace_id, kind, connection_id) DO UPDATE SET
                        destination_url = EXCLUDED.destination_url,
                        status = 'active',
                        updated_at = NOW()
                    RETURNING connection_id, grant_id
                    """,
                    (
                        user_id, workspace_id, GRANT_KIND_OAUTH_MCP,
                        list(connection_ids), user_id, SERVABLE_PARAM,
                    ),
                )
                granted = {
                    str(row["connection_id"]): str(row["grant_id"])
                    for row in await cur.fetchall()
                }

            await cur.execute(
                """
                UPDATE sandbox_egress_grants
                SET status = 'revoked', updated_at = NOW()
                WHERE workspace_id = %s AND kind = %s AND status = 'active'
                  AND grant_id != ALL(%s::uuid[])
                """,
                (
                    workspace_id, GRANT_KIND_OAUTH_MCP,
                    list(granted.values()),
                ),
            )
            if cur.rowcount:
                logger.info(
                    f"[egress_grants_db] retired {cur.rowcount} stale grant(s) "
                    f"for workspace {workspace_id}"
                )
            return GrantSync(grants=granted, retired=cur.rowcount)


async def fetch_grant_for_relay(grant_id: str) -> dict[str, Any] | None:
    """The relay's per-request authorization read.

    Authorization only — no credential. The vendor token comes from the OAuth
    lifecycle (which owns refresh and the generation CAS), so this stays a
    cheap non-decrypting read on the hot path. None for an unknown grant_id
    (the route answers a uniform 404 for absent and wrong-scope alike).
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT g.user_id, g.workspace_id, g.connection_id,
                       g.destination_url, g.allowed_methods, g.tool_allowlist,
                       g.status AS grant_status,
                       c.status AS connection_status
                FROM sandbox_egress_grants g
                JOIN user_mcp_oauth_connections c ON c.connection_id = g.connection_id
                WHERE g.grant_id = %s
                """,
                (grant_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "workspace_id": str(row["workspace_id"]),
                "connection_id": str(row["connection_id"]),
                "destination_url": row["destination_url"],
                "allowed_methods": row["allowed_methods"],
                "tool_allowlist": row["tool_allowlist"],
                "grant_status": row["grant_status"],
                "connection_status": row["connection_status"],
            }


async def revoke_grants_for_connection(connection_id: str, *, conn=None) -> int:
    """Flip every grant of a connection to revoked. Returns count."""
    async with get_db_connection(conn) as db:
        async with db.cursor() as cur:
            await cur.execute(
                """
                UPDATE sandbox_egress_grants
                SET status = 'revoked', updated_at = NOW()
                WHERE connection_id = %s AND status != 'revoked'
                """,
                (connection_id,),
            )
            if cur.rowcount:
                logger.info(
                    f"[egress_grants_db] revoked {cur.rowcount} grant(s) "
                    f"for connection {connection_id}"
                )
            return cur.rowcount
