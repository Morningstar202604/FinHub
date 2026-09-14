"""
Server script
"""
import os
import sys

# Make the `src` layout importable when running from the repo root
# (uvicorn loads "src.server.app:app", which imports the ptc_agent package).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import asyncio

# Windows Event Loop Fix - must be before any async imports
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import argparse
import logging
import uvicorn

logger = logging.getLogger(__name__)

def _guard_oss_bind(host: str) -> None:
    """Refuse to expose an unauthenticated server on a non-loopback address.

    HOST_MODE=oss disables authentication entirely (see auth/jwt_bearer.py) and
    attributes every request to a single fixed user. That is fine for a laptop
    or a single-tenant box, but binding it to 0.0.0.0 silently publishes the
    whole workspace — chat history, BYOK keys, sandboxes — to the network.
    Fail closed unless the operator explicitly opts out.
    """
    from src.config.env import ALLOW_INSECURE_OSS, HOST_MODE

    if HOST_MODE != "oss" or ALLOW_INSECURE_OSS:
        return
    if host.strip() in ("127.0.0.1", "localhost", "::1"):
        return

    sys.exit(
        "\n".join(
            [
                "",
                "REFUSING TO START: HOST_MODE=oss disables authentication, but the server was",
                f"asked to bind to '{host}' (a non-loopback address). Anyone who can reach this",
                "port gets full access to every workspace and stored API key.",
                "",
                "Choose one:",
                "  1. Bind to loopback:        python server.py --host 127.0.0.1",
                "  2. Enable real auth:        HOST_MODE=platform (requires SUPABASE_URL)",
                "  3. Accept the risk:         ALLOW_INSECURE_OSS=1 (only if a reverse proxy,",
                "                              VPN, or firewall already restricts access)",
                "",
            ]
        )
    )


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the server")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (default: True except on Windows)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of uvicorn worker processes (default: 1)",
    )

    args = parser.parse_args()

    _guard_oss_bind(args.host)

    # Configure SSE event logger independently
    # This allows viewing ONLY SSE events by setting SSE_EVENT_LOG_LEVEL=info
    # and server --log-level=error
    import os
    sse_event_log_level = os.getenv("SSE_EVENT_LOG_LEVEL", "info").upper()
    sse_logger = logging.getLogger("sse_events")
    sse_logger.setLevel(getattr(logging, sse_event_log_level))
    # Add dedicated handler so SSE logs output independently of root logger level
    sse_handler = logging.StreamHandler()
    sse_handler.setLevel(getattr(logging, sse_event_log_level))
    sse_handler.setFormatter(logging.Formatter("%(message)s"))
    sse_logger.addHandler(sse_handler)
    # Prevent duplicate logs by not propagating to root logger
    sse_logger.propagate = False


    # Determine reload setting
    reload = False
    if args.reload:
        reload = True

    # Uvicorn never exposes the worker count to the app, so hand it over via
    # env: the lifespan refuses --workers>1 when the WriterGuard fence cannot
    # activate (non-Postgres checkpointer or split app/checkpoint databases).
    # That hard gate is the whole multi-worker admission story — the old
    # single-worker warning's mechanisms (in-process report-back caps/drain,
    # in-memory compaction guard, BTM liveness healing) are all distributed
    # or deleted as of v4 Phase 2 (accepted residual: same-pair dispatch
    # lifecycle overlap across processes, gen-CAS-bounded last-writer-wins).
    os.environ["LANGALPHA_WORKERS"] = str(args.workers)

    try:
        logger.info(f"Starting server on {args.host}:{args.port}")
        if sys.platform == "win32":
            # psycopg async requires a selector event loop. uvicorn.run() picks
            # a Proactor loop on Windows by default, which silently never
            # completes PostgreSQL socket IO (lifespan hangs → PoolTimeout),
            # so drive uvicorn on an explicit SelectorEventLoop here.
            import selectors
            loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.set_event_loop(loop)
            config = uvicorn.Config(
                "src.server.app:app",
                host=args.host,
                port=args.port,
                reload=reload,
                workers=args.workers,
                log_level=args.log_level,
                timeout_keep_alive=300,
                timeout_graceful_shutdown=60,
            )
            server = uvicorn.Server(config)
            try:
                loop.run_until_complete(server.serve())
            finally:
                loop.close()
        else:
            uvicorn.run(
                "src.server.app:app",
                host=args.host,
                port=args.port,
                reload=reload,
                workers=args.workers,
                log_level=args.log_level,
                timeout_keep_alive=300,  # 5 minutes - for long-running workflows
                timeout_graceful_shutdown=60,  # 60 seconds for graceful shutdown
            )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        exit(1)
