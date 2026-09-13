"""Socket tripwire: unit tests must not reach real network endpoints.

A mock that silently stops intercepting (e.g. after a module move breaks a
patch target) fails OPEN — the test goes green against live I/O. Blocking
socket creation turns that failure mode into a loud error. AF_UNIX stays
allowed: asyncio's event loop self-pipe is a unix socketpair. On Windows the
selector loop's self-pipe is an AF_INET socketpair instead, so starlette's
TestClient portal (and any asyncio.run in a sync test) is blocked by the
strict policy — those tests opt in per-test with ``enable_inet_socket``,
which lets AF_INET/AF_INET6 socket() calls through while getaddrinfo stays
blocked against remote hosts.
"""

from pathlib import Path

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def _no_real_sockets(request):
    if request.node.get_closest_marker("enable_socket"):
        yield
        return
    if request.node.get_closest_marker("enable_inet_socket"):
        _disable_sockets_allow_inet()
        yield
        pytest_socket.enable_socket()
        return
    pytest_socket.disable_socket(allow_unix_socket=True)
    yield
    pytest_socket.enable_socket()


def _disable_sockets_allow_inet() -> None:
    """Same tripwire as disable_socket, but let AF_INET/AF_INET6 socket()
    through so Windows selector-loop self-pipes can be built. getaddrinfo
    stays blocked, so no real remote host can be reached.

    Implementation: call disable_socket(allow_unix_socket=True) to install
    the unix-only guard, then wrap its GuardedSocket.__new__ to also allow
    AF_INET/AF_INET6 — everything else still raises SocketBlockedError.
    """
    import socket as _socket
    import pytest_socket as _ps

    _ps.disable_socket(allow_unix_socket=True)
    active = _socket.socket  # GuardedSocket class installed by pytest_socket
    _guard_new = active.__new__

    def _permissive_new(cls, *args, **kwargs):
        family = args[0] if args else kwargs.get("family", -1)
        if family in (_socket.AF_INET, _socket.AF_INET6):
            return _ps._true_socket.__new__(cls, *args, **kwargs)
        return _guard_new(cls, *args, **kwargs)

    active.__new__ = _permissive_new


@pytest.fixture(autouse=True)
def _reader_pool_follows_cache_client(monkeypatch):
    """Alias the dedicated stream-reader pool onto the injected cache client.

    Blocking XREADs moved off the cache pool in production, but unit tests
    inject their fakes through ``get_cache_client``. Without this the readers
    would build a real ``BlockingConnectionPool`` and block inside XREAD; the
    accessor deliberately has no cache fallback of its own.

    One seam, and it follows whichever client the caller resolved, because the
    accessor is handed that client rather than looking one up. A test wanting
    real reader-pool behavior overrides this single symbol.
    """
    from src.utils.cache import stream_pool

    async def _reader(cache):
        return getattr(cache, "client", None)

    monkeypatch.setattr(stream_pool, "get_stream_reader_client", _reader)


@pytest.fixture(autouse=True)
def _empty_user_skill_bundle(monkeypatch):
    """Stub the per-turn user-skill bundle to empty for unit tests.

    ``resolve_llm_config`` loads it from Postgres on every turn; unit tests
    have no pool. Both binding sites are patched: the package attribute the
    lazy imports resolve, and the defining module's global that
    ``sandbox_skill_sync_params`` calls. Tests *about* the bundle itself put
    the real function back — see ``server/services/user_skills/conftest.py``.
    """
    from src.server.services import user_skills
    from src.server.services.user_skills import materialize

    async def _empty(user_id, workspace_id=None):
        return user_skills.EMPTY_USER_SKILL_BUNDLE

    monkeypatch.setattr(user_skills, "load_user_skill_bundle", _empty)
    monkeypatch.setattr(materialize, "load_user_skill_bundle", _empty)


@pytest.fixture(scope="session")
def shipped_skill_md():
    """Locate a shipped skill's SKILL.md on disk, by name.

    A registry entry's ``skill_md_path`` is where the *agent* reaches the file
    inside a sandbox, not where this repo keeps it: the shipped skills live in
    the bundle that declares them, and the sync flattens every source into one
    directory. Joining that suffix onto the repo root reads as correct and is
    not, so the lookup asks the bundles instead.
    """
    from ptc_agent.config.plugins import bundled_skill_dirs

    def find(name: str) -> Path:
        for root in bundled_skill_dirs():
            candidate = root / name / "SKILL.md"
            if candidate.is_file():
                return candidate
        raise AssertionError(f"no bundle ships a {name!r} skill")

    return find
