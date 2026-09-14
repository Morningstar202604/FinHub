#!/usr/bin/env python3
r"""Leak guard — a catch-all handler must not put its exception text on the wire.

The rule, stated narrowly
-------------------------
``detail=`` (and the dict-shaped ``detail={...}``, and the plugin install
report's ``reason=``) is client-facing. When the handler is a **catch-all** —
``except Exception`` / ``except BaseException`` — the thing it caught is as
likely to be a driver or transport error as an application one, and those put
the host, the port, the resolved IP, the request URL and the response body into
``str(exc)``. Composing a client-facing field from that text publishes whatever
the failure happened to contain.

When the handler names a **narrow** exception type, the message is authored by
this codebase and meant to be read: ``InvalidStoreKeyError`` says which rule the
key broke. Echoing those is the whole point of catching them, and this guard
does not touch them. The distinction is the caught type, not the spelling.

Why the rule is drawn here
--------------------------
``sanitize_error_text`` masks credential *shapes* — DSN userinfo, bearer tokens,
``sk-`` keys, keyed query params. That is the right tool for echoing a value
that must survive. It is the wrong tool for a generic 500: masking
``postgresql://user:pw@host`` leaves ``host``, and a psycopg error's table and
column names pass through untouched. So on a catch-all the correct move is to
drop the text and keep the action, which is exactly what
``src/server/utils/api.py`` has done since it was written — under a comment
that says "Never ``detail=str(e)`` here".

That comment was the only enforcement, and it was violated. This is the same
rule, made checkable.

What is deliberately *not* flagged
----------------------------------
* **Narrow ``except`` types.** Authored messages; see above.
* **Text that happens to come from a response, not a message** —
  ``f"Provider returned {e.response.status_code}"`` interpolates an int and
  leaks nothing. Attribute chains into a response object are not the exception
  message, so ``str(e)``-shaped composition is what is matched.
* **Logger calls.** ``logger.error("...", reason=...)`` is a structlog binding,
  not an HTTP field. Only the recognised response constructors are inspected.
* **Explicitly scrubbed values** — ``sanitize_error_text(...)`` / ``single_line
  (...)`` / a known local helper such as ``_client_safe(...)``. The value was
  considered; whether the mask is sufficient is a review question, not a
  pattern question.

Usage:
    python scripts/guard/error_leak_guard.py [--check] [--json] [--list]
Exit code 0 = clean; 1 = violation found (CI uses this).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# Constructors that carry a client-facing payload. ``HTTPException`` and
# ``JSONResponse`` are the HTTP surface; ``ProbeResult`` / install-report
# components are rendered verbatim by the UI. Anything else — loggers,
# internal dataclasses — is out of scope by construction.
_CLIENT_CALLABLES: frozenset[str] = frozenset(
    {"HTTPException", "JSONResponse", "ProbeResult", "of", "_over_cap"}
)

# ``error`` belongs here as much as ``detail`` does: a response model built by
# keyword (``PackageInstallResponse(..., error=...)``) puts it on the wire just
# as surely. It was left out of an earlier revision, which is exactly how a
# real leak on a route sat undetected — coverage gaps in a guard are worse than
# no guard, because the green tick is read as "checked".
_CLIENT_FIELDS: frozenset[str] = frozenset({"detail", "message", "reason", "error"})

# Values routed through one of these were considered and scrubbed. Whether the
# mask is enough is a review question; this guard checks that it happened.
_SCRUBBERS: frozenset[str] = frozenset(
    {"sanitize_error_text", "single_line", "_client_safe", "sandbox_unreachable_detail"}
)

# Catch-all types. Catching one of these means the type carries no information
# about whether the message is authored, so the message must not travel.
_CATCH_ALL_TYPES: frozenset[str] = frozenset({"Exception", "BaseException"})

# Types whose message is authored here and is meant for the caller. Kept as a
# named set so the exemption is visible and arguable rather than implicit in
# some type check. Note this is a *characterisation*, not an allow-list: the
# guard derives safety from "the handler is not a catch-all" first.
_ALLOW: dict[str, str] = {}


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return getattr(func, "id", None)


# Decorator attribute names that mark an HTTP route handler. A ``{"error":
# str(e)}`` built inside one of these is a response body; the same dict built
# inside a plain function is a tool result the LLM is meant to read, and
# flagging that would be wrong.
_ROUTE_VERBS: frozenset[str] = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}
)


def _is_route_function(func: ast.AST) -> bool:
    """Does this function carry a router decorator (``@router.get`` etc.)?"""
    for dec in getattr(func, "decorator_list", []) or []:
        if isinstance(dec, ast.Call):
            dec = dec.func
        if isinstance(dec, ast.Attribute) and dec.attr in _ROUTE_VERBS:
            return True
        # ``@router.get(...)`` where router itself is an attribute is covered
        # above; ``@app.get`` likewise. A bare ``@get`` is not a FastAPI route.
    return False


def _handler_is_catch_all(handler: ast.ExceptHandler) -> bool:
    """True for ``except Exception`` / ``except BaseException`` / bare ``except:``.

    A bare ``except:`` is the widest form of the same hazard, so it counts.
    A tuple like ``except (ValueError, RuntimeError)`` is *not* catch-all: the
    types are named and their messages are ours.
    """
    if handler.type is None:
        return True
    for node in ast.walk(handler.type):
        if isinstance(node, ast.Name) and node.id in _CATCH_ALL_TYPES:
            return True
    return False


def _exception_binding(handler: ast.ExceptHandler) -> set[str]:
    """Names the handler bound, e.g. ``{"e"}`` for ``except Exception as e``."""
    return {handler.name} if handler.name else set()


def _is_scrubbed(node: ast.AST) -> bool:
    """Does this expression pass its value through a known scrubber?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _callee_name(sub) in _SCRUBBERS:
            return True
    return False


def _composes_exception_text(node: ast.AST, bound: set[str]) -> list[str]:
    """How this expression turns the caught exception into a string.

    Returns the offending shapes, so the message can name what it saw rather
    than just asserting a violation. Only composition *into a string* counts:
    ``e.response.status_code`` is an int off a response object, not the
    exception's message, and flagging it would make the guard noise.
    """
    shapes: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            name = _callee_name(sub)
            if name in ("str", "repr", "format") and sub.args:
                target = sub.args[0]
                if isinstance(target, ast.Name) and target.id in bound:
                    shapes.append(f"{name}({target.id})")
            if name == "getattr" and sub.args:
                target = sub.args[0]
                if isinstance(target, ast.Name) and target.id in bound:
                    shapes.append(f"getattr({target.id}, ...)")
        # A JoinedStr (f-string) that interpolates the bare bound name.
        if isinstance(sub, ast.JoinedStr):
            for part in sub.values:
                if isinstance(part, ast.FormattedValue):
                    inner = part.value
                    if isinstance(inner, ast.Name) and inner.id in bound:
                        shapes.append(f'f"{{{inner.id}}}"')
                    # `{e!r}` and `{e!s}`.
                    if isinstance(inner, ast.Attribute):
                        continue
    return shapes


def scan() -> list[str]:
    """Every catch-all handler that composes a client-facing field from its exc."""
    errors: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
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

        rel = path.relative_to(REPO)

        # A route handler that builds its response body by hand —
        # ``result["x"] = {"error": str(e)}`` — rather than raising, which is
        # the same leak through a door the keyword-only check above does not
        # cover. Found for real on the unauthenticated /health endpoint.
        errors.extend(_route_dict_leaks(tree, rel))

        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            if not _handler_is_catch_all(handler):
                continue
            bound = _exception_binding(handler)
            if not bound:
                continue

            for call in ast.walk(handler):
                if not isinstance(call, ast.Call):
                    continue
                if _callee_name(call) not in _CLIENT_CALLABLES:
                    continue
                for kw in call.keywords:
                    if kw.arg not in _CLIENT_FIELDS:
                        continue
                    shapes = _composes_exception_text(kw.value, bound)
                    if not shapes:
                        continue
                    if _is_scrubbed(kw.value):
                        continue
                    key = f"{rel}:{call.lineno}"
                    if key in _ALLOW:
                        continue
                    errors.append(
                        f"{key}: `{kw.arg}=` on {_callee_name(call)}() built from "
                        f"{', '.join(sorted(set(shapes)))} inside a catch-all "
                        f"({_caught_text(handler)}) — the client receives the "
                        f"message verbatim"
                    )
    return errors


def _route_dict_leaks(tree: ast.Module, rel: Path) -> list[str]:
    """Response bodies assembled by hand inside a route handler.

    A route can return a dict instead of raising, and the dict is the wire
    format just the same. This is scoped to functions that actually carry a
    route decorator, because ``return {"success": False, "error": str(exc)}``
    in a plain function is a tool result the LLM is supposed to read — the
    agent cannot fix a failure it cannot see.
    """
    errors: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_route_function(func):
            continue
        for handler in ast.walk(func):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            if not _handler_is_catch_all(handler):
                continue
            bound = _exception_binding(handler)
            if not bound:
                continue
            for node in ast.walk(handler):
                # result["checkpointer"] = {"error": str(e)}
                value = None
                if isinstance(node, ast.Assign) and node.value is not None:
                    value = node.value
                elif isinstance(node, ast.Return) and node.value is not None:
                    value = node.value
                if value is None:
                    continue

                # Two shapes reach the client from a return: a literal dict, and
                # a response model built by keyword —
                # ``PackageInstallResponse(..., error=str(e))``. The second is
                # the one a detail=-only check misses entirely, because the
                # constructor is not a known HTTP callable.
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Dict):
                        for k, v in zip(sub.keys, sub.values):
                            if not isinstance(k, ast.Constant):
                                continue
                            if k.value not in _CLIENT_FIELDS:
                                continue
                            shapes = _composes_exception_text(v, bound)
                            if not shapes or _is_scrubbed(v):
                                continue
                            errors.append(
                                f"{rel}:{sub.lineno}: response dict key {k.value!r} "
                                f"built from {', '.join(sorted(set(shapes)))} "
                                f"inside a catch-all in route {func.name}() — "
                                f"the client receives the message verbatim"
                            )
                    elif isinstance(sub, ast.Call):
                        for kw in sub.keywords:
                            if kw.arg not in _CLIENT_FIELDS:
                                continue
                            shapes = _composes_exception_text(kw.value, bound)
                            if not shapes or _is_scrubbed(kw.value):
                                continue
                            errors.append(
                                f"{rel}:{sub.lineno}: {_callee_name(sub)}("
                                f"{kw.arg}=...) built from "
                                f"{', '.join(sorted(set(shapes)))} inside a "
                                f"catch-all in route {func.name}() — the client "
                                f"receives the message verbatim"
                            )
    return errors


def _caught_text(handler: ast.ExceptHandler) -> str:
    if handler.type is None:
        return "bare except"
    try:
        return f"except {ast.unparse(handler.type)}"
    except Exception:  # noqa: BLE001 — only used for a message
        return "except <unparseable>"


def check_allowlist_staleness() -> list[str]:
    """An ``_ALLOW`` entry whose file has vanished is dead text."""
    errors: list[str] = []
    for key in sorted(_ALLOW):
        path_part = key.rsplit(":", 1)[0]
        if not (REPO / path_part).exists():
            errors.append(
                f"STALE allowance: {key} — file no longer exists; delete it "
                f"from _ALLOW in scripts/guard/error_leak_guard.py"
            )
    return errors


def run_all() -> dict[str, list[str]]:
    return {
        "error_leaks": scan(),
        "allowlist_staleness": check_allowlist_staleness(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run checks (default)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--list", action="store_true", help="list findings, exit 0")
    args = parser.parse_args()

    results = run_all()
    violations = {k: v for k, v in results.items() if v}

    if args.list:
        for name, errors in results.items():
            print(f"# {name}: {len(errors)} finding(s)")
            for err in errors:
                print(f"  {err}")
        return 0
    if args.json:
        print(json.dumps({"ok": not violations, "violations": violations}, indent=2))
        return 1 if violations else 0

    if violations:
        for name, errors in results.items():
            if not errors:
                continue
            print(f"[FAIL] {name}")
            for err in errors:
                print(f"        - {err}")
    else:
        print(
            "[OK] error-leak guard — no client-facing field built from a "
            "catch-all exception"
        )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
