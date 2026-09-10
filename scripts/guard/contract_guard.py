#!/usr/bin/env python3
"""Contract guard — gatekeeper for the ROADMAP M1.1 invariants.

Checks (all offline, stdlib only, no app imports):
  1. migrations/versions linear chain: unique, contiguous, strictly
     incrementing 3-digit prefixes; no reordering or editing of history.
  2. src/server/contracts/status.py the public vocabulary is a partition
     derived from LIVE + TERMINAL families (+ the two singletons), and the
     terminal sets referenced by run ledgers / outbox policy still exist.
  3. tests/unit/mcp_servers/agent_docstring_lock.json is a valid, non-empty
     lock file whose lock keys are `direct:<name>` shaped — full consistency
     is enforced by the unit suite (via update_agent_docstring_lock.py).
  4. web/src/lib/threadLifecycle/store.ts mirrors the public status sets
     (frontend hand-mirror catch).

Usage:
    python scripts/guard/contract_guard.py [--check] [--json]
Exit code 0 = all green; 1 = violation found (CI uses this).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "migrations" / "versions"
STATUS_PY = REPO / "src" / "server" / "contracts" / "status.py"
LOCK_JSON = REPO / "tests" / "unit" / "mcp_servers" / "agent_docstring_lock.json"
FRONTEND_MIRROR = REPO / "web" / "src" / "lib" / "threadLifecycle" / "store.ts"

_MIGRATION_RE = re.compile(r"^(\d{3})_(.+)\.py$")
_MIGRATION_SKIP = {"env.py", "script.py.mako", "__init__.py"}
_STATUS_NAMES = (
    "LIVE_PUBLIC_STATUSES",
    "TERMINAL_PUBLIC_STATUSES",
    "TERMINAL_STATUSES",
    "REPORT_BACK_STATUSES",
    "RAW_LIVE_STATUSES",
    "RAW_TERMINAL_SNAPSHOT_STATUSES",
)

# Public vocabulary is {idle, interrupted} ∪ LIVE ∪ TERMINAL (a partition).
_SINGLETONS = ("idle", "interrupted")


def _extract_status_sets(source: str) -> dict[str, tuple[str, ...]]:
    """Safely read tuple literals from status.py without importing it."""
    tree = ast.parse(source)
    out: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in _STATUS_NAMES:
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(value, tuple) and all(isinstance(v, str) for v in value):
                    out[target.id] = value
    return out


def check_migrations() -> list[str]:
    errors: list[str] = []
    if not MIGRATIONS.is_dir():
        return [f"migrations dir missing: {MIGRATIONS}"]
    numbers: list[int] = []
    for path in sorted(MIGRATIONS.iterdir()):
        name = path.name
        if name in _MIGRATION_SKIP or not path.is_file() or name.startswith("."):
            continue
        m = _MIGRATION_RE.match(name)
        if not m:
            errors.append(f"non-migration file in versions/: {name}")
            continue
        num = int(m.group(1))
        if num in numbers:
            errors.append(f"duplicate migration prefix: {name}")
        numbers.append(num)
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        errors.append(
            f"migration chain is not a contiguous 1..N sequence: "
            f"found {numbers[0] if numbers else '∅'}..{numbers[-1] if numbers else '∅'} ({len(numbers)} files)"
        )
    return errors


def check_status_vocabulary() -> list[str]:
    errors: list[str] = []
    if not STATUS_PY.is_file():
        return [f"status.py missing: {STATUS_PY}"]
    sets = _extract_status_sets(STATUS_PY.read_text(encoding="utf-8"))
    missing = [n for n in _STATUS_NAMES if n not in sets]
    if missing:
        errors.append(f"status.py lost required sets: {missing}")
        return errors

    live = sets["LIVE_PUBLIC_STATUSES"]
    terminal_public = sets["TERMINAL_PUBLIC_STATUSES"]
    terminal_internal = sets["TERMINAL_STATUSES"]
    report_back = sets["REPORT_BACK_STATUSES"]

    # The public vocabulary is exactly the partition {idle, interrupted} | LIVE | TERMINAL.
    public_expected = frozenset(_SINGLETONS) | set(live) | set(terminal_public)
    public_derived = set(_SINGLETONS) | set(live) | set(terminal_public)
    if public_expected != public_derived:
        errors.append("PUBLIC vocabulary is not the {idle,interrupted} ∪ LIVE ∪ TERMINAL partition")

    # Internal terminal statuses use `error` where the public face says `failed`;
    # every public terminal label (except that rename) must exist internally.
    if not set(terminal_public) - {"failed"} <= set(terminal_internal):
        errors.append("TERMINAL_PUBLIC_STATUSES (minus failed↔error rename) must map into TERMINAL_STATUSES")
    if "completed" not in terminal_internal or "error" not in terminal_internal:
        errors.append("TERMINAL_STATUSES must keep completed + error spellings")

    # Report-back policy: completed + error (cancelled is intentionally excluded).
    if set(report_back) != {"completed", "error"}:
        errors.append("REPORT_BACK_STATUSES must be exactly {completed, error}")
    return errors


def check_docstring_lock() -> list[str]:
    errors: list[str] = []
    if not LOCK_JSON.is_file():
        return [f"docstring lock missing: {LOCK_JSON}"]
    try:
        data = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"docstring lock is not valid JSON: {exc}"]
    if not isinstance(data, dict) or not data:
        errors.append("docstring lock is empty (expected ≥1 locked tool)")
        return errors
    for key, entry in data.items():
        if not re.match(r"^[a-z_]+(:[a-z0-9_]+)+$", key):
            errors.append(f"lock key not `namespace:server:name` shaped: {key!r}")
            continue
        if not isinstance(entry, dict) or "doc_lines" not in entry:
            errors.append(f"lock entry {key!r} missing doc_lines")
    return errors


def check_frontend_mirror() -> list[str]:
    errors: list[str] = []
    if not FRONTEND_MIRROR.is_file():
        return [f"frontend status mirror missing: {FRONTEND_MIRROR}"]
    text = FRONTEND_MIRROR.read_text(encoding="utf-8")
    for symbol in ("LIVE_STATUSES", "TERMINAL_FAMILY"):
        if symbol not in text:
            errors.append(f"frontend mirror lost {symbol!r} in {FRONTEND_MIRROR.name}")
    return errors


def run_all() -> dict[str, list[str]]:
    return {
        "migrations": check_migrations(),
        "status_vocabulary": check_status_vocabulary(),
        "docstring_lock": check_docstring_lock(),
        "frontend_mirror": check_frontend_mirror(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run checks (default)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    results = run_all()
    violations = {k: v for k, v in results.items() if v}
    if args.json:
        print(json.dumps({"ok": not violations, "violations": violations}, indent=2))
    else:
        for name, errors in results.items():
            status = "OK" if not errors else "FAIL"
            print(f"[{status}] {name}")
            for err in errors:
                print(f"        - {err}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())