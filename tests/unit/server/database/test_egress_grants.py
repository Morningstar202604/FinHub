"""Ownership and atomicity of a workspace's egress grant set.

A grant is what lets a sandbox spend someone's OAuth credential, so three
contracts matter at this layer. ``connection_id`` is *selected* under the owner
predicate rather than trusted from the caller: another user's connection must
produce no grant at all, indistinguishably from one that does not exist. The
upserts and the retirement of everything else commit together — a grant set
that committed without its retirement half is an authorization overhang the
sandbox can still spend. And because the write is a whole-set *replacement*, it
is fenced by a workspace advisory lock plus a ``mcp_config_version`` CAS: two
workers cannot be merged by row locks (their sets need not overlap), so a
resolver carrying a superseded version must replace nothing at all.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from src.server.database.egress_grants import (
    GRANT_KIND_OAUTH_MCP,
    sync_oauth_grants,
)
from src.server.services.writer_guard import advisory_key

OWNER = "user-owner"
INTRUDER = "user-intruder"
CONNECTION_ID = "11111111-1111-4111-8111-111111111111"
OTHER_CONNECTION_ID = "44444444-4444-4444-8444-444444444444"
UNKNOWN_CONNECTION_ID = "33333333-3333-4333-8333-333333333333"
WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
VERSION = 7


class _Cursor:
    """Models the four things this SQL's correctness rests on: the INSERT rows
    come from a SELECT over the connections table (not from the parameters),
    that SELECT filters on connection status as well as owner, the retirement
    sweeps every active grant outside the keep list, and the live
    ``mcp_config_version`` is re-read (under the lock) rather than trusted from
    the caller."""

    def __init__(self, connections: dict[str, str]) -> None:
        self._connections = connections  # connection_id -> owning user_id
        # connection_id -> status; absent means the default, connected.
        self.statuses: dict[str, str] = {}
        self.grants: dict[tuple, dict] = {}  # (workspace, kind, conn) -> row
        self._rows: list[dict] = []
        self._row: dict | None = None
        self.rowcount = 0
        self.depth = 0  # transaction nesting at the time of the last execute
        self.statements: list[tuple[str, tuple, int]] = []
        self.lock_keys: list[int] = []
        # The workspace's live config version; None models a deleted workspace.
        self.version: int | None = VERSION

    async def execute(self, sql: str, params: tuple) -> None:
        self.statements.append((sql, params, self.depth))
        if "pg_advisory_xact_lock" in sql:
            self.lock_keys.append(params[0])
        elif "mcp_config_version" in sql:
            self._row = (
                None if self.version is None else {"mcp_config_version": self.version}
            )
        elif sql.lstrip().startswith("INSERT"):
            # The servable list is unpacked as optional on purpose: the fake
            # filters on status only while the statement actually binds one, so
            # dropping the predicate shows up as a wrong grant set rather than
            # as an unpacking error here.
            _user_id, workspace_id, kind, connection_ids, owner, *rest = params
            servable = rest[0] if rest else None
            self._rows = []
            for connection_id in connection_ids:
                # The source SELECT: no matching row ⇒ nothing is inserted for
                # that id and ON CONFLICT never fires, so it never RETURNs.
                if self._connections.get(connection_id) != owner:
                    continue
                if (
                    servable is not None
                    and self.statuses.get(connection_id, "connected") not in servable
                ):
                    continue
                row = self.grants.setdefault(
                    (workspace_id, kind, connection_id),
                    {"grant_id": f"grant-for-{connection_id}", "status": "revoked"},
                )
                row["status"] = "active"
                self._rows.append(
                    {"connection_id": connection_id, "grant_id": row["grant_id"]}
                )
        else:
            workspace_id, kind, keep = params
            self._rows = []
            stale = [
                row
                for (ws, k, _c), row in self.grants.items()
                if ws == workspace_id
                and k == kind
                and row["status"] == "active"
                and row["grant_id"] not in keep
            ]
            for row in stale:
                row["status"] = "revoked"
            self.rowcount = len(stale)

    async def fetchall(self) -> list[dict]:
        return self._rows

    async def fetchone(self) -> dict | None:
        return self._row

    def active_grant_ids(self) -> set[str]:
        return {r["grant_id"] for r in self.grants.values() if r["status"] == "active"}

    def grant_writes(self) -> list[tuple[str, tuple, int]]:
        """Only the statements that touch grant rows — the fence reads excluded."""
        return [
            s
            for s in self.statements
            if "pg_advisory_xact_lock" not in s[0] and "mcp_config_version" not in s[0]
        ]


@pytest.fixture
def db():
    """A connections table with two connections, both owned by OWNER."""
    cursor = _Cursor({CONNECTION_ID: OWNER, OTHER_CONNECTION_ID: OWNER})

    @asynccontextmanager
    async def _cursor_cm(**kwargs):
        yield cursor

    @asynccontextmanager
    async def _transaction():
        cursor.depth += 1
        try:
            yield
        finally:
            cursor.depth -= 1

    class _Conn:
        cursor = staticmethod(_cursor_cm)
        transaction = staticmethod(_transaction)

    @asynccontextmanager
    async def _fake_db(conn=None):
        yield conn if conn is not None else _Conn()

    with patch("src.server.database.egress_grants.get_db_connection", new=_fake_db):
        yield cursor


async def _sync(user_id: str, *connection_ids: str, config_version: int = VERSION):
    return await sync_oauth_grants(
        user_id=user_id,
        workspace_id=WORKSPACE_ID,
        connection_ids=list(connection_ids),
        config_version=config_version,
    )


class TestOwnership:
    @pytest.mark.asyncio
    async def test_the_owner_gets_a_grant(self, db):
        synced = await _sync(OWNER, CONNECTION_ID)
        assert synced.grants == {CONNECTION_ID: f"grant-for-{CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_another_users_connection_yields_no_grant(self, db):
        """The id is real, but not theirs — it must bind into no workspace."""
        synced = await _sync(INTRUDER, CONNECTION_ID)
        assert synced.grants == {}

    @pytest.mark.asyncio
    async def test_an_unknown_connection_fails_the_same_way(self, db):
        """Same empty answer as the wrong-owner case: guessing ids teaches nothing."""
        synced = await _sync(OWNER, UNKNOWN_CONNECTION_ID)
        assert synced.grants == {}

    @pytest.mark.asyncio
    async def test_one_bad_id_does_not_cost_the_others_their_grants(self, db):
        synced = await _sync(OWNER, UNKNOWN_CONNECTION_ID, CONNECTION_ID)
        assert synced.grants == {CONNECTION_ID: f"grant-for-{CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_the_predicate_is_in_the_sql_not_the_caller(self, db):
        """Pinned structurally too — the fake can only model what the SQL says.

        Were the ownership filter to move out of the statement, every arm above
        would still pass against a differently-shaped fake.
        """
        await _sync(OWNER, CONNECTION_ID)
        sql, params, _depth = db.grant_writes()[0]
        flat = re.sub(r"\s+", " ", sql)
        assert "FROM user_mcp_oauth_connections c" in flat
        assert "WHERE c.connection_id = ANY(%s::uuid[]) AND c.user_id = %s" in flat
        # The inserted connection_id AND destination_url both come from the
        # connection row (c.connection_id, c.server_url), never a parameter —
        # a caller can never steer the grant at a host the token wasn't issued
        # for. No destination_url parameter exists to pass.
        assert "SELECT %s, %s::uuid, %s, c.connection_id, c.server_url" in flat
        assert params[3:5] == ([CONNECTION_ID], OWNER)
        assert params[2] == GRANT_KIND_OAUTH_MCP


class TestConnectionStatusFilter:
    """A grant is spendable authority, so it may only be bound to a connection
    whose credential is still servable.

    The upsert's ``DO UPDATE SET status = 'active'`` makes this load-bearing in
    both directions: without the predicate, the next resolve of a workspace
    that still names a revoked connection would *reactivate* the grant the
    disconnect just retired, and a needs_reauth connection would carry an
    active grant the frontend already renders as broken.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["revoked", "needs_reauth"])
    async def test_a_non_servable_connection_gets_no_grant(self, db, status):
        db.statuses[CONNECTION_ID] = status

        synced = await _sync(OWNER, CONNECTION_ID)

        assert synced.grants == {}

    @pytest.mark.asyncio
    async def test_an_ambiguous_connection_still_gets_one(self, db):
        # refresh_ambiguous is servable: the old access token keeps working
        # until it expires, so cutting the grant would break a live sandbox.
        db.statuses[CONNECTION_ID] = "refresh_ambiguous"

        synced = await _sync(OWNER, CONNECTION_ID)

        assert synced.grants == {CONNECTION_ID: f"grant-for-{CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_a_revoked_connections_grant_is_retired_not_reactivated(self, db):
        await _sync(OWNER, CONNECTION_ID, OTHER_CONNECTION_ID)
        db.statuses[CONNECTION_ID] = "revoked"

        # The stale catalog still names it, so the resolver still asks for it.
        synced = await _sync(OWNER, CONNECTION_ID, OTHER_CONNECTION_ID)

        assert synced.grants == {OTHER_CONNECTION_ID: f"grant-for-{OTHER_CONNECTION_ID}"}
        assert synced.retired == 1
        assert db.active_grant_ids() == {f"grant-for-{OTHER_CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_the_status_predicate_is_in_the_sql_with_the_owner_one(self, db):
        """Structural, like the ownership pin: both predicates guard the same
        SELECT, and the servable vocabulary rides in as a parameter."""
        await _sync(OWNER, CONNECTION_ID)

        sql, params, _depth = db.grant_writes()[0]
        assert "AND c.status = ANY(%s)" in re.sub(r"\s+", " ", sql)
        assert params[-1] == ["connected", "refresh_ambiguous"]


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_re_syncing_returns_the_same_grant(self, db):
        first = await _sync(OWNER, CONNECTION_ID)
        second = await _sync(OWNER, CONNECTION_ID)
        assert first.grants == second.grants
        assert second.retired == 0


class TestRetirement:
    """The retire predicate is what closes the authorization overhang: an
    active grant the resolved set no longer contains must stop being
    spendable, and the upserted set is the only thing that protects a grant."""

    @pytest.mark.asyncio
    async def test_a_dropped_server_loses_its_grant(self, db):
        await _sync(OWNER, CONNECTION_ID, OTHER_CONNECTION_ID)
        synced = await _sync(OWNER, CONNECTION_ID)

        assert synced.retired == 1
        assert db.active_grant_ids() == {f"grant-for-{CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_an_empty_set_retires_everything_active(self, db):
        await _sync(OWNER, CONNECTION_ID, OTHER_CONNECTION_ID)
        synced = await _sync(OWNER)

        assert synced.grants == {}
        assert synced.retired == 2
        assert db.active_grant_ids() == set()
        # Nothing to upsert ⇒ only the retirement statement is issued.
        assert len(db.grant_writes()) == 3

    @pytest.mark.asyncio
    async def test_a_connection_that_vanished_loses_its_grant_too(self, db):
        """Its id is still resolved, but it no longer selects a row — the keep
        list is built from what was upserted, never from what was asked for."""
        await _sync(OWNER, CONNECTION_ID)
        db._connections.pop(CONNECTION_ID)
        synced = await _sync(OWNER, CONNECTION_ID)

        assert synced.grants == {}
        assert synced.retired == 1

    @pytest.mark.asyncio
    async def test_upsert_and_retirement_commit_together(self, db):
        await _sync(OWNER, CONNECTION_ID)
        assert [depth for _sql, _params, depth in db.grant_writes()] == [1, 1]

    @pytest.mark.asyncio
    async def test_the_fence_shares_that_transaction(self, db):
        """``pg_advisory_xact_lock`` outside the transaction would release at
        once, and a version read outside it could be overtaken before the
        writes land — both must sit in the same txn as the grant writes."""
        await _sync(OWNER, CONNECTION_ID)
        assert [depth for _sql, _params, depth in db.statements] == [1, 1, 1, 1]


class TestConfigVersionCAS:
    """A whole-set replacement cannot be merged with a concurrent one: two
    workers' sets need not overlap, so Postgres row locks protect nothing. The
    stale worker must therefore be told to stand down entirely — otherwise its
    upsert reactivates a grant the fresh worker just revoked (``ON CONFLICT DO
    UPDATE SET status='active'``) and its retirement revokes the fresh set."""

    @pytest.mark.asyncio
    async def test_a_stale_version_replaces_nothing(self, db):
        await _sync(OWNER, CONNECTION_ID)
        before = db.active_grant_ids()
        db.statements.clear()

        # A fresh worker bumped the config and synced; this resolver still
        # carries the old version.
        db.version = VERSION + 1
        synced = await _sync(OWNER, OTHER_CONNECTION_ID, config_version=VERSION)

        assert synced is None
        # Not "wrote something harmless" — issued no grant statement at all.
        assert db.grant_writes() == []
        assert db.active_grant_ids() == before

    @pytest.mark.asyncio
    async def test_a_matching_version_proceeds(self, db):
        synced = await _sync(OWNER, CONNECTION_ID, config_version=VERSION)
        assert synced is not None
        assert synced.grants == {CONNECTION_ID: f"grant-for-{CONNECTION_ID}"}

    @pytest.mark.asyncio
    async def test_a_deleted_workspace_replaces_nothing(self, db):
        """No row ⇒ no version ⇒ no match, rather than a NULL that compares
        equal to something."""
        db.version = None
        assert await _sync(OWNER, CONNECTION_ID) is None
        assert db.grant_writes() == []

    @pytest.mark.asyncio
    async def test_the_version_is_re_read_under_the_lock(self, db):
        """Order is the whole fix: locking after the read would let a newer
        sync commit in between, and never re-reading would trust the caller's
        stale copy."""
        await _sync(OWNER, CONNECTION_ID)
        kinds = [
            "lock"
            if "pg_advisory_xact_lock" in sql
            else "version"
            if "mcp_config_version" in sql
            else "write"
            for sql, _params, _depth in db.statements
        ]
        assert kinds == ["lock", "version", "write", "write"]

    @pytest.mark.asyncio
    async def test_the_lock_is_workspace_scoped_and_domain_separated(self, db):
        await _sync(OWNER, CONNECTION_ID)
        assert db.lock_keys == [advisory_key("EG", WORKSPACE_ID)]
        # A different workspace converges concurrently rather than queueing.
        assert advisory_key("EG", WORKSPACE_ID) != advisory_key("EG", CONNECTION_ID)
        # And the tag keeps it off the writer guard's thread/namespace keys.
        assert advisory_key("EG", WORKSPACE_ID) != advisory_key("T", WORKSPACE_ID)
