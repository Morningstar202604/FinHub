"""Strong-reference tracking for fire-and-forget asyncio tasks, plus the guard
that makes "I forgot the reference" a test failure rather than a production
mystery.

The event loop holds only a **weak** reference to a running task, so a task
whose return value is discarded can be garbage-collected mid-flight. This is
documented behaviour, not a theoretical hazard: the symptom is a coroutine
that simply stops at an arbitrary await point, with no exception and no log.

Usage:

    spawn(do_work())                       # dispatch-style, nothing to anchor to
    track_task(asyncio.create_task(...))   # you already built the task

Callers that already own a place to anchor the task (an ``app.state`` slot, a
long-lived service instance) should use that instead — this is for the
dispatch-style call sites where no such owner exists.

Why the AST scan below exists
-----------------------------
The rule "a ``create_task`` result must be reachable" was already written down
in three different places — comments in ``thread_mutation``, ``insight_service``
and ``subagent_collection`` — and was violated anyway. Prose cannot be enforced,
so the rule is checked mechanically in ``tests/unit/server/utils/test_task_tracking.py``.

The scan deliberately does **not** try to be a linter. It answers one question:
is the created task either held somewhere durable, or awaited in the same
function? Everything else (awaiting a task already held in a plain local
variable, for instance) is reported as unproven rather than as a fault — see
``_is_provably_anchored``. A guard that cries wolf gets muted, and a muted guard
is worse than no guard.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# AST scan — used by the test, not by production.
# --------------------------------------------------------------------------- #

# Names that are known to hold the task durably.
_ANCHOR_NAMES = frozenset(
    {
        "spawn",
        "track_task",
        "create_task_with_context",
        "_track_task",
        "_retain_collector",
        "track_reader_task",
        "fire_and_forget",
    }
)

def _is_create_task_call(node: ast.AST) -> bool:
    """True for ``create_task(...)`` anywhere on the expression.

    Matches ``asyncio.create_task``, ``loop.create_task``, and the bare name.
    Callers that annotate their own tasks must not be invisible to this scan —
    an earlier revision matched only the ``asyncio.`` form and silently missed
    ``asyncio.get_running_loop().create_task(...)``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "create_task"
    return isinstance(func, ast.Name) and func.id == "create_task"


def _is_helper_definition(node: ast.AST) -> bool:
    """Is this a call to a *wrapper* that does the tracking itself?

    ``spawn``, ``track_task`` and friends are where this module's rule is
    implemented; scanning their bodies would report the implementation.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name in _ANCHOR_NAMES


# Set by ``scan_unanchored_create_tasks`` before it judges anything: assigning
# into a module-level name is durable, a local is not.
_MODULE_LEVEL_NAMES: set[str] = set()

# Functions whose *purpose* is to hold a task. ``spawn`` and ``track_task``
# both hand ``create_task``'s result straight to ``_bg_tasks``, but they do it
# through a local before the call, so no single call in the body reads as
# "anchored". Scanning past the definition would report the implementation of
# the rule rather than a violation of it.
_ANCHOR_IMPLEMENTATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("utils/task_tracking.py", "track_task"),
        ("utils/task_tracking.py", "spawn"),
        ("handlers/chat/detached.py", "fire_and_forget"),
        ("services/cache/_series_cache_core.py", "spawn_bg_task"),
        ("app/memo.py", "_spawn_background"),
        ("app/threads/_deps.py", "_track_task"),
        ("services/runs/subagent_collection.py", "_retain_collector"),
    }
)


def _module_level_names(tree: ast.Module) -> set[str]:
    """Names bound at module scope, including inside ``if``/``try`` blocks."""
    names: set[str] = set()

    def _collect(statements: Iterable[ast.stmt]) -> None:
        for stmt in statements:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    names.add(stmt.target.id)
            elif isinstance(stmt, (ast.If, ast.Try)):
                _collect(stmt.body)
                _collect(stmt.orelse)
                _collect(getattr(stmt, "finalbody", []) or [])
                for handler in getattr(stmt, "handlers", []) or []:
                    _collect(handler.body)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                _collect(stmt.body)

    _collect(tree.body)
    return names


def _is_create_task_call(node: ast.AST) -> bool:
    """True for ``create_task(...)`` anywhere on the expression.

    Matches ``asyncio.create_task``, ``loop.create_task``, and the bare name.
    Callers that annotate their own tasks must not be invisible to this scan —
    an earlier revision matched only the ``asyncio.`` form and silently missed
    ``asyncio.get_running_loop().create_task(...)``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "create_task"
    return isinstance(func, ast.Name) and func.id == "create_task"


def _is_provably_anchored(node: ast.AST, func: ast.AST) -> bool:
    """Is this ``create_task`` result either wrapped, held, or awaited?

    Ways to be fine:

    1. wrapped by a known tracking helper (``_ANCHOR_NAMES``) — including
       inside a collection that is then passed to ``gather``/``wait``;
    2. stored into something durable — a module-level global, or an attribute
       of any object (``op.heartbeat = ...``). Services and singletons are the
       owners here, and we cannot prove they are short-lived, so we accept it;
    3. assigned to a local that is later ``await``ed in the same function;
    4. awaited in place — ``await asyncio.shield(create_task(...))``, or as an
       element of ``asyncio.gather``/``wait`` that is itself awaited. The await
       is the anchor.
    5. handed to a call we do not own (``handler(create_task(...))``). Whether
       that call retains it is beyond the AST; reporting it would be a guess.

    Deliberately *not* covered, and reported instead:

    * a bare ``create_task(coro)`` as an expression statement — the shape that
      actually leaked in production;
    * a local that is never awaited — unprovable from the AST, and the scanner
      says so rather than pretending to have checked.
    """
    parent = getattr(node, "_ancestor", None)
    if isinstance(parent, ast.Await):
        return True

    # (1) wrapped by a tracking helper — check the enclosing call chain
    enclosing = parent
    while isinstance(enclosing, (ast.Call, ast.Starred, ast.List, ast.Tuple, ast.Set)):
        called = getattr(enclosing, "func", None)
        name = (
            called.attr
            if isinstance(called, ast.Attribute)
            else getattr(called, "id", None)
        )
        if name in _ANCHOR_NAMES:
            return True
        if name in ("gather", "wait", "shield", "ensure_future"):
            # The await on the surrounding statement is the anchor.
            for anc in _ancestors_of(enclosing):
                if isinstance(anc, ast.Await):
                    return True
        enclosing = getattr(enclosing, "_ancestor", None)

    # (2) stored into a durable location: attribute, or a module-level name
    target = None
    if isinstance(parent, ast.Assign) and parent.targets:
        target = parent.targets[0]
    elif isinstance(parent, ast.AnnAssign):
        target = parent.target
    if target is not None:
        if isinstance(target, ast.Attribute):
            return True  # self.x / op.heartbeat — owned by an object
        name = getattr(target, "id", None)
        if name:
            if name in _MODULE_LEVEL_NAMES:
                return True  # a module global outlives the function
            # (3) local: does any await in this function await it?
            for anc in ast.walk(func):
                if isinstance(anc, ast.Name) and anc.id == name:
                    if isinstance(getattr(anc, "_ancestor", None), ast.Await):
                        return True
            # (3b) local holding a *collection*: the task is anchored if that
            # collection reaches an await (``await gather(*tasks)``). Follow
            # the name one hop instead of assuming. Note the gather call's own
            # ancestor is the ``Await``, so a Name that reaches an Await is
            # already evidence — checking for the callee first would miss it.
            for anc in ast.walk(func):
                if isinstance(anc, ast.Name) and anc.id == name:
                    holders = list(_ancestors_of(anc))
                    if any(isinstance(h, ast.Await) for h in holders):
                        return True
                    if any(
                        isinstance(h, ast.Call)
                        and _callee_name(h) in ("gather", "wait", "shield", "wait_for")
                        for h in holders
                    ):
                        return True
            return False

    # (4) element of a collection literal. The collection itself must be
    # anchored: either it is consumed by an awaited call in place, or it is
    # bound to a name that is (``tasks = [...]`` then ``await gather(*tasks)``).
    if isinstance(parent, (ast.List, ast.Tuple, ast.Set, ast.Starred)):
        for holder in _ancestors_of(parent):
            if isinstance(holder, ast.Await):
                return True
            if isinstance(holder, ast.Call) and _callee_name(holder) in (
                "gather",
                "wait",
                "shield",
                "ensure_future",
                "wait_for",
            ):
                return True
            if _is_helper_call(holder):
                return True
            if isinstance(holder, (ast.Assign, ast.AnnAssign)):
                bound = (
                    holder.targets[0]
                    if isinstance(holder, ast.Assign)
                    else holder.target
                )
                bound_name = getattr(bound, "id", None)
                if bound_name is None:
                    # ``op.tasks = [...]`` — owned by an object.
                    return isinstance(bound, ast.Attribute)
                if bound_name in _MODULE_LEVEL_NAMES:
                    return True
                for ref in ast.walk(func):
                    if isinstance(ref, ast.Name) and ref.id == bound_name:
                        if any(
                            isinstance(h, ast.Await) for h in _ancestors_of(ref)
                        ):
                            return True
                return False

    # (5) passed into a call we do not own
    if isinstance(parent, ast.Call) and node in parent.args:
        return True
    if isinstance(parent, ast.keyword):
        return True

    return False


def _callee_name(call: ast.Call) -> str | None:
    """The called name, for both ``f(x)`` and ``mod.f(x)``."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return getattr(func, "id", None)


def _is_helper_call(node: ast.AST) -> bool:
    """True when *node* is a call to a known tracking helper."""
    return isinstance(node, ast.Call) and _callee_name(node) in _ANCHOR_NAMES


def _ancestors_of(node: ast.AST):
    """Yield *node*'s ancestors, nearest first."""
    parent = getattr(node, "_ancestor", None)
    while parent is not None:
        yield parent
        parent = getattr(parent, "_ancestor", None)


def _annotate_ancestors(tree: ast.AST) -> None:
    """Attach a ``_ancestor`` link to every node, depth-first.

    Deliberately a recursive descent rather than a single ``ast.walk`` pass.
    ``ast.walk`` is breadth-first, and an earlier revision of this scan added
    the attribute from whichever parent it happened to reach first — so a
    ``create_task`` call nested inside an ``Expr`` could end up holding a stale
    or wrong ancestor and be judged against the wrong shape. Recursion makes
    "the parent" mean the parent.
    """
    for child in ast.iter_child_nodes(tree):
        child._ancestor = tree  # type: ignore[attr-defined]
        _annotate_ancestors(child)


def scan_unanchored_create_tasks(root: Path) -> list[str]:
    """Return ``path:line: name`` for every create_task with no provable anchor.

    Only production code is scanned; a test may reasonably create a task and
    assert on it.
    """
    global _MODULE_LEVEL_NAMES

    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "test" in path.name or "test" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        _annotate_ancestors(tree)
        _MODULE_LEVEL_NAMES = _module_level_names(tree)

        rel = path.relative_to(root)
        rel_key = str(rel).replace("\\", "/")
        # Function bodies.
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (rel_key, func.name) in _ANCHOR_IMPLEMENTATIONS:
                continue
            for node in ast.walk(func):
                if _is_create_task_call(node) and not _is_provably_anchored(node, func):
                    findings.append(f"{rel}:{node.lineno}: {func.name}()")

        # Module scope. Rare, but the same hazard with a worse symptom: the
        # task is anchored by a module global that is only rebound on reload.
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for node in ast.walk(stmt):
                if _is_create_task_call(node) and not _is_provably_anchored(
                    node, tree
                ):
                    findings.append(f"{rel}:{node.lineno}: <module>")
    return findings
