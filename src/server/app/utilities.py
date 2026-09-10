"""
Utility endpoints for TTS, podcast, RAG, config, health checks, and WebSocket.

This module handles miscellaneous endpoints:
- Text-to-speech conversion
- Podcast generation
- RAG configuration and resources
- Server configuration
- WebSocket chat
- Health checks
- Custom metrics
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

logger = logging.getLogger(__name__)
INTERNAL_SERVER_ERROR_DETAIL = "Internal Server Error"

# Create router (health checks are unversioned at /health)
health_router = APIRouter(tags=["Health"])

@health_router.get("/health")
async def health_check():
    """Health check endpoint with checkpointer pool stats + Redis liveness.

    Non-fatal probes: checkpointer/Redis failures mark the result ``degraded``
    (or ``error``) but never raise — a healthy API server that lost its Redis
    must still answer 200 /health so load balancers keep the instance during
    a blip instead of flipping it in and out.
    """
    from src.server.app.setup import checkpointer
    from src.server.utils.checkpointer import get_checkpointer_health

    result = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "service": "ptc-agent",
    }

    # Include checkpointer pool health if configured
    try:
        checkpointer_health = await get_checkpointer_health(checkpointer)
        result["checkpointer"] = checkpointer_health
        if checkpointer_health.get("status") == "unhealthy":
            result["status"] = "degraded"
    except Exception as e:
        result["checkpointer"] = {"status": "error", "error": str(e)}
        result["status"] = "degraded"

    # Redis liveness (M3-infra): the event-buffer transport and cache both
    # depend on it. Non-fatal like the checkpointer probe — report, degrade,
    # keep serving on a transient Redis blip.
    try:
        from src.utils.cache.redis_cache import get_cache_client

        redis_ok = await get_cache_client().health_check()
        result["redis"] = {"status": "healthy" if redis_ok else "unreachable"}
        if not redis_ok:
            result["status"] = "degraded"
    except Exception as e:
        result["redis"] = {"status": "error", "error": str(e)}
        result["status"] = "degraded"

    return result