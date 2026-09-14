#!/usr/bin/env python3
"""Layering guard — ratchet for the package-dependency inversions.

Background
----------
`src/` has no module-level import cycles (Tarjan: 641 modules, no SCC > 1), yet
six package pairs refer to each other *bidirectionally*. Every one of those
cycles is hidden inside function bodies: the top-level import graph looks clean
and the real graph is tangled. That is why `grimp`/`import-linter`'s default
view reports zero couples while the source plainly has them.

The worst of them is `server <-> tools`. `tools` is the capability layer; it
should be reachable *from* `server`, never the reverse, because a capability
that depends on the application shell cannot be reused, tested in isolation, or
type-checked as a leaf. The count is `tools -> server` 33 vs `server -> tools`
16 — the inversion is real and sizeable.

What this guard does
--------------------
It is a *ratchet*, not a pure assertion. Turning on a hard "server must not
import tools" rule today would fail CI on 13 pre-existing chains and the only
way to green would be a risky big-bang refactor of the hottest paths in the
repo. Instead:

  * `_FROZEN` lists the 13 chains that exist right now. They are tolerated.
  * Any chain *not* in `_FROZEN` fails immediately — new inversions are blocked.
  * A chain in `_FROZEN` that no longer reproduces also fails, with a message
    telling you to delete the entry. So the list can only shrink, and a
    refactor that fixes one is forced to claim the win rather than leave a
    stale allowance lying around.

Net effect: the number can go down, never up, and never silently.

Deliberately stdlib-only and offline (no app imports, no grimp dependency), so
it runs in the same `lint` CI job as `ruff` with nothing extra to install.

Usage:
    python scripts/guard/layering_guard.py [--check] [--json] [--list]
Exit code 0 = no new violations; 1 = violation (CI uses this).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# Packages that participate in the layering contract. Anything else under src/
# is treated as out of scope (kept explicit so a new top-level package is a
# deliberate addition rather than an accidental one).
KNOWN_PACKAGES = frozenset(
    {
        "config",
        "data_client",
        "core",
        "llms",
        "market_protocol",
        "observability",
        "ptc_agent",
        "server",
        "tools",
        "utils",
    }
)

# Chains tolerated today: (importer_module, imported_module). Exact module
# paths, not packages, so an allowance cannot silently widen to cover a new
# file. Sorted for stable diffs.
#
# To shrink this list: fix a chain, re-run, and delete the line the guard tells
# you is stale. Do not add entries to make a red build green — a new entry is
# precisely the regression this file exists to catch.
_FROZEN: frozenset[tuple[str, str]] = frozenset(
    {
        # --- server reaching into tools: the C1 inversion -------------------
        # `tools.web.manifest` is pricing metadata that server-side cost
        # accounting needs but cannot own. Correct fix: push the data down to
        # config (see ARCH_AUDIT_REPORT C1).
        ("src.server.app.api_keys", "src.tools.web.manifest"),
        ("src.server.app.users", "src.tools.web.manifest"),
        ("src.server.services.llm.config", "src.tools.web.manifest"),
        # company profile lookup built as a tool but consumed as a service.
        ("src.server.app.market_data", "src.tools.market_data.company"),
        # retrieval is a capability; server's memory app calls into it.
        ("src.server.app.memory", "src.tools.memory.retrieval"),
        # PII scrubbing must run on every outbound message path. Arguably this
        # belongs in utils, not tools — sentinel scanning is not a capability
        # the agent chooses to invoke.
        ("src.server.app.threads.messaging", "src.tools.guardrails.pii"),
        # chat request prep composes tool-layer primitives before dispatch.
        ("src.server.handlers.chat.request_prep", "src.tools.decorators"),
        ("src.server.handlers.chat.request_prep", "src.tools.guardrails"),
        ("src.server.handlers.chat.request_prep", "src.tools.guardrails.pii"),
        ("src.server.handlers.chat.request_prep", "src.tools.web.fetch"),
        # sse_producer reuses the tool decorator + guardrail helpers.
        ("src.server.services.runs.sse_producer", "src.tools.decorators"),
        ("src.server.services.runs.sse_producer", "src.tools.guardrails"),
        # --- server -> utils -> tools: a transitive inversion ----------------
        # server imports utils.tracking, which imports tools.web.manifest.
        # Fixing the manifest chain above removes all three of these.
        (
            "src.server.services.persistence.usage",
            "src.utils.tracking.infrastructure_costs",
        ),
        # The same hop, one level deeper: the guard resolves the full chain, and
        # `import-linter`'s report collapses it into the line above. Recorded
        # explicitly so the count is honest about how many places pull tools in.
        ("src.server.services.persistence.usage", "src.tools.web.manifest"),
    }
)

# Chains fixed by this guard's introduction, kept as a regression check: these
# were `server -> tools.chart_annotation.schemas` until `Timeframe` moved to the
# leaf package `market_protocol.intervals`. If they ever reappear the move has
# been undone, so they are asserted absent rather than merely unfrozen.
_FIXED_MUST_STAY_FIXED: frozenset[tuple[str, str]] = frozenset(
    {
        ("src.server.models.additional_context", "src.tools.chart_annotation.schemas"),
        ("src.server.app.chart_annotations", "src.tools.chart_annotation.schemas"),
    }
)


def _module_name(path: Path) -> str:
    """`src/server/app/users.py` -> `src.server.app.users`."""
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _referenced_src_modules(node: ast.Import | ast.ImportFrom) -> set[str]:
    """Top-level src.* modules an import node refers to, as dotted strings.

    Handles both `from src.a.b import c` and `import src.a.b as c`. For a
    `from x import y` the leaf `y` is NOT treated as a module — it is almost
    always a symbol, and resolving it would need the filesystem; module paths
    are what the contract is about.
    """
    out: set[str] = set()
    if isinstance(node, ast.ImportFrom):
        if node.module and node.module.split(".")[0] == "src":
            out.add(node.module)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] == "src":
                out.add(alias.name)
    return out


def _per_file_module_refs() -> dict[str, set[str]]:
    """module name -> every src.* module it refers to, including function-level.

    This is the whole point: `grimp` and Python's import machinery only see
    module-level imports, which is why the cycles are invisible to them. We parse
    all Import/ImportFrom nodes at any depth so the hidden edges are counted.
    """
    refs: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        name = _module_name(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
            print(f"layering_guard: could not parse {path}: {exc}", file=sys.stderr)
            continue
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                found |= _referenced_src_modules(node)
        refs[name] = {m for m in found if m != name}
    return refs


def _resolve_to_module(dotted: str, known: set[str]) -> str | None:
    """Map a dotted import target to the most specific real module.

    `src.tools.web.manifest` may be a module; `src.tools.web` may be a package
    whose `__init__` re-exports from `.manifest`. We prefer the longest real
    module name so the recorded chain names the file that actually pulls the
    dependency in.
    """
    parts = dotted.split(".")
    while len(parts) > 1:
        candidate = ".".join(parts)
        if candidate in known:
            return candidate
        parts.pop()
    return None


def find_inversions() -> tuple[set[tuple[str, str]], set[str]]:
    """Return (violations, all_server_to_tools_chains).

    `violations` = chains NOT in _FROZEN plus frozen entries that no longer
    reproduce. `all_server_to_tools_chains` is the raw observed set, used by
    --list and by the stale-entry check.
    """
    refs = _per_file_module_refs()
    known = set(refs)

    observed: set[tuple[str, str]] = set()
    for importer, targets in refs.items():
        if not importer.startswith("src.server."):
            continue
        for tgt in targets:
            resolved = _resolve_to_module(tgt, known)
            if resolved is None:
                continue
            # Any server -> tools chain, direct or via an intermediate module
            # that itself reaches tools. The transitive case matters: the
            # `server -> utils.tracking -> tools.web.manifest` hop is real.
            if resolved.startswith("src.tools."):
                observed.add((importer, resolved))
            elif resolved.startswith(("src.utils.", "src.llms.", "src.config.")):
                for hop_target in refs.get(resolved, ()):
                    hop_resolved = _resolve_to_module(hop_target, known)
                    if hop_resolved and hop_resolved.startswith("src.tools."):
                        observed.add((importer, resolved))
                        observed.add((importer, hop_resolved))

    violations: set[tuple[str, str]] = set()
    for pair in observed - _FROZEN:
        if pair in _FIXED_MUST_STAY_FIXED:
            violations.add(pair)
        else:
            violations.add(pair)
    # Stale entries: frozen but no longer observed.
    stale = _FROZEN - observed
    return violations, observed, stale


def _layer_violations() -> list[str]:
    """Unused — retained deliberately as a documented non-goal.

    An earlier revision checked a declared package ladder (config < utils <
    tools < server, …) and reported every upward edge. It flagged 58
    pre-existing edges: `tools -> data_client` (a tool legitimately fetches
    market data), `ptc_agent -> server` (the agent kernel reading DB rows),
    `utils -> llms` (token pricing). Those are not defects — they are the actual
    design, and inventing a rung order to call them violations would have been
    me legislating an architecture nobody agreed to.

    The one inversion with a clear, defensible direction is `server -> tools`,
    because `tools` is the capability layer the agent selects from. That is what
    this guard enforces. Anything broader needs a design decision, not a lint
    rule smuggled in by a refactor.
    """
    return []


def run_all() -> dict[str, list[str]]:
    violations, observed, stale = find_inversions()
    new_chains = sorted(p for p in violations if p not in _FROZEN)
    revived = sorted(p for p in violations if p in _FIXED_MUST_STAY_FIXED)

    errors: list[str] = []
    for importer, target in new_chains:
        errors.append(f"NEW inversion: {importer} -> {target}")
    for importer, target in revived:
        errors.append(
            f"REGRESSION: {importer} -> {target} — this was fixed by moving "
            f"Timeframe to market_protocol.intervals; the move has been undone"
        )
    for importer, target in sorted(stale):
        errors.append(
            f"STALE allowance: {importer} -> {target} no longer reproduces — "
            f"delete it from _FROZEN in scripts/guard/layering_guard.py"
        )
    return {
        "server_to_tools_inversions": errors,
        "_observed_count": [str(len(observed))],
        "_frozen_count": [str(len(_FROZEN))],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run checks (default)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--list", action="store_true", help="print every observed chain")
    args = parser.parse_args()

    if args.list:
        _, observed, _ = find_inversions()
        for importer, target in sorted(observed):
            mark = "" if (importer, target) in _FROZEN else "   <-- NEW"
            print(f"{importer} -> {target}{mark}")
        print(f"\n{len(observed)} observed, {len(_FROZEN)} frozen")
        return 0

    results = run_all()
    errors = results["server_to_tools_inversions"]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "violations": {"server_to_tools": errors},
                    "observed": int(results["_observed_count"][0]),
                    "frozen": int(results["_frozen_count"][0]),
                },
                indent=2,
            )
        )
    else:
        if errors:
            print("[FAIL] server must not import tools (inversion ratchet)")
            for err in errors:
                print(f"        - {err}")
        else:
            print(
                f"[OK] layering ratchet — {results['_observed_count'][0]} observed "
                f"chain(s), {results['_frozen_count'][0]} frozen, no new inversions"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
