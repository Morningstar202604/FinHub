"""Strong-reference tracking for fire-and-forget asyncio tasks.

The event loop holds only a **weak** reference to a running task, so a task
whose return value is discarded can be garbage-collected mid-flight. This is
documented behaviour, not a theoretical hazard: the symptom is a coroutine
that simply stops at an arbitrary await point, with no exception and no log.

The fix is one strong reference held until the task completes:

    _track_task(asyncio.create_task(do_work()))

Callers that already own a place to anchor the task (an ``app.state`` slot, a
long-lived service instance) should use that instead — this is for the
dispatch-style call sites where no such owner exists.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Strong references to in-flight background tasks. Each task removes itself on
# completion, so this stays proportional to concurrency, not to uptime.
_bg_tasks: set[asyncio.Task] = set()


def _on_task_done(task: asyncio.Task) -> None:
    _bg_tasks.discard(task)
    # A background task that raised would otherwise never surface: nobody
    # awaits it, so the exception is stored on the task and dropped when the
    # task is collected. Log it here instead.
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %r failed", task.get_name(), exc_info=exc
        )


def track_task(task: asyncio.Task) -> asyncio.Task:
    """Hold a strong reference to *task* until it finishes. Returns the task."""
    _bg_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


def spawn(coro, *, name: str | None = None) -> asyncio.Task:
    """``create_task`` + ``track_task`` in one call.

    Preferred at dispatch sites: it is impossible to forget the reference
    because there is no intermediate variable to drop.
    """
    return track_task(asyncio.create_task(coro, name=name))


def pending_count() -> int:
    """In-flight tracked tasks. Exposed for shutdown/diagnostics."""
    return len(_bg_tasks)
