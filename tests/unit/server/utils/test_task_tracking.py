"""Tests for the create_task anchor rule.

Two things are covered here and they are different in kind:

* ``TestScan``  — the AST scanner's own behaviour, on synthetic trees.
* ``TestProductionTree`` — the real rule, applied to ``src/``. The recorded
  floors are a ratchet: they can only go down, and lowering one is the visible
  act of claiming a fix. See ``src/server/utils/task_tracking.py`` for why the
  rule exists and why it is expressed as a scan rather than prose.
"""

from __future__ import annotations

from pathlib import Path


from src.server.utils import task_tracking as tt

SRC = Path(__file__).resolve().parents[4] / "src"


def _scan_one(body: str, tmp_path: Path) -> list[str]:
    """Run the scanner over a single synthetic module."""
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "mod.py").write_text(
        "import asyncio\n\n\n" + body, encoding="utf-8"
    )
    return tt.scan_unanchored_create_tasks(tmp_path / "src")


class TestScan:
    def test_bare_dispatch_is_reported(self, tmp_path):
        """The exact shape that leaked: result discarded, nobody owns it."""
        found = _scan_one(
            "async def f(coro):\n"
            "    asyncio.create_task(coro)\n",
            tmp_path,
        )
        assert len(found) == 1
        assert "f()" in found[0]

    def test_spawn_wrapper_is_accepted(self, tmp_path):
        found = _scan_one(
            "from src.server.utils.task_tracking import spawn\n\n\n"
            "async def f(coro):\n"
            "    spawn(coro)\n",
            tmp_path,
        )
        assert found == []

    def test_attribute_target_is_accepted(self, tmp_path):
        """``op.heartbeat = ...`` — owned by an object, like the reaper's task."""
        found = _scan_one(
            "async def f(coro, op):\n"
            "    op.heartbeat = asyncio.create_task(coro)\n",
            tmp_path,
        )
        assert found == []

    def test_local_awaited_in_same_function_is_accepted(self, tmp_path):
        found = _scan_one(
            "async def f(coro):\n"
            "    t = asyncio.create_task(coro)\n"
            "    await t\n",
            tmp_path,
        )
        assert found == []

    def test_local_never_awaited_is_reported(self, tmp_path):
        """Held by a local that outlives its last use — unprovable, so reported."""
        found = _scan_one(
            "async def f(coro):\n"
            "    t = asyncio.create_task(coro)\n"
            "    print('done')\n",
            tmp_path,
        )
        assert len(found) == 1

    def test_collection_passed_to_gather_is_accepted(self, tmp_path):
        found = _scan_one(
            "async def f(a, b):\n"
            "    tasks = [asyncio.create_task(a), asyncio.create_task(b)]\n"
            "    await asyncio.gather(*tasks)\n",
            tmp_path,
        )
        assert found == []

    def test_test_files_are_skipped(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "test_thing.py").write_text(
            "import asyncio\n\n\nasync def f(c):\n    asyncio.create_task(c)\n",
            encoding="utf-8",
        )
        assert tt.scan_unanchored_create_tasks(tmp_path / "src") == []

    def test_unparsable_file_does_not_abort_the_scan(self, tmp_path):
        """A broken file must not hide every finding behind it."""
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "broken.py").write_text("def (:\n", encoding="utf-8")
        (pkg / "real.py").write_text(
            "import asyncio\n\n\nasync def f(c):\n    asyncio.create_task(c)\n",
            encoding="utf-8",
        )
        assert len(tt.scan_unanchored_create_tasks(tmp_path / "src")) == 1


class TestProductionTree:
    """The ratchet that actually holds production in place.

    ``_FROZEN`` names every site the scanner cannot *prove* is anchored. Most
    of them are fine — they store the task in a module- or instance-level
    collection that the scanner has no way to see from inside one function.
    The list is not an accusation; it is the set of sites that must be
    re-read by a human whenever the shape around them changes.

    Two properties are enforced, and they are what make this a ratchet rather
    than a snapshot:

    * a **new** unproven site fails the test — additions need justification;
    * a **stale** entry fails the test — confirming a site is genuinely
      anchored is the act of deleting its line here, so the list can only
      shrink, and it cannot rot into fiction.
    """

    _FROZEN: frozenset[str] = frozenset(
        {
            "observability/tracing.py:create_task_with_context()",
            "ptc_agent/agent/middleware/background_subagent/registry.py:_remove_when_settled()",
            "ptc_agent/agent/middleware/background_subagent/run_executor.py:_make_task_done_callback()",
            "ptc_agent/agent/middleware/background_subagent/run_executor.py:_on_task_done()",
            "ptc_agent/agent/middleware/provenance/body_store.py:schedule_body_write()",
            "server/app/mcp_servers.py:_schedule_proactive_apply()",
            "server/app/mcp_servers.py:_schedule_session_mcp_refresh()",
            "server/app/memo.py:_spawn_background()",
            "server/app/memo.py:_kickoff_metadata()",
            "server/app/setup.py:lifespan()",
            "server/app/workspaces.py:_schedule_warm_restart()",
            "server/handlers/chat/detached.py:fire_and_forget()",
            "server/services/automation_scheduler.py:_poll_once()",
            "server/services/cache/_series_cache_core.py:spawn_bg_task()",
            "server/services/history/projection_cache.py:schedule_projection_refresh()",
            "server/services/hook_outbox.py:_loop()",
            "server/services/insight_service.py:generate_for_user()",
            "server/services/mcp_oauth/discovery.py:schedule_post_edit_rediscovery()",
            "server/services/runs/coordinator.py:_teardown_guard()",
            "server/services/runs/subagent_collection.py:collect_subagent_results_for_turn()",
            "server/services/thread_title.py:schedule_title_generation()",
            "server/services/workspace_manager.py:_kick_mcp_discovery()",
            "server/services/workspace_manager.py:schedule_skill_reconcile()",
            "server/services/workspace_manager.py:_claim_and_restart()",
            "server/services/workspace_manager.py:_observe_and_broadcast()",
            "tools/web/breaker.py:record_failure()",
            "tools/web/fetch.py:web_fetch()",
        }
    )

    @staticmethod
    def _site(finding: str) -> str:
        """``path:line: func()`` -> ``path:func()`` (line numbers drift)."""
        path, _line, rest = finding.split(":", 2)
        return f"{path.strip()}:{rest.strip()}"

    def test_no_new_unproven_dispatch(self):
        findings = tt.scan_unanchored_create_tasks(SRC)
        new = sorted({self._site(f) for f in findings} - self._FROZEN)
        assert new == [], (
            "new create_task site whose result the scanner cannot prove is "
            "anchored. Either hold the task (spawn(), or a set with a done "
            "callback) or add it to _FROZEN with a reason:\n  "
            + "\n  ".join(new)
        )

    def test_no_stale_frozen_entry(self):
        """A frozen site that no longer fires must be removed.

        This is the mechanism that forces the list to keep describing reality.
        """
        observed = {self._site(f) for f in tt.scan_unanchored_create_tasks(SRC)}
        stale = sorted(self._FROZEN - observed)
        assert stale == [], (
            "these _FROZEN entries no longer reproduce — delete them:\n  "
            + "\n  ".join(stale)
        )

    def test_regression_lock_on_the_repaired_sites(self):
        """The two production leaks found by the audit stay fixed.

        Both were bare dispatches whose handle went out of scope on the next
        line: a front-matter sync inside an agent middleware, and the
        opportunistic browser-orphan reap. Neither is in ``_FROZEN``, so any
        return to the old shape fails ``test_no_new_unproven_dispatch`` — this
        test exists to make the reason legible from the outside.
        """
        findings = tt.scan_unanchored_create_tasks(SRC)
        for marker in ("workspace_context.py", "web/inhouse/safe_wrapper.py"):
            assert not any(marker in f for f in findings), (
                f"{marker} regressed to an unanchored dispatch"
            )



class TestTracking:
    def test_track_task_holds_until_done(self):
        import asyncio

        async def main() -> None:
            started = asyncio.Event()

            async def work() -> int:
                started.set()
                await asyncio.sleep(0.01)
                return 1

            t = tt.track_task(asyncio.create_task(work()))
            await started.wait()
            await t
            # The done callback runs on the loop, so give it one turn to fire.
            await asyncio.sleep(0)
            assert t not in tt._bg_tasks
            assert tt.pending_count() == 0

        asyncio.run(main())

    def test_pending_count_is_proportional_to_concurrency_not_uptime(self):
        import asyncio

        async def main() -> None:
            async def work() -> None:
                await asyncio.sleep(0.01)

            for _ in range(5):
                task = asyncio.create_task(work())
                tt.track_task(task)
                await task
            await asyncio.sleep(0)
            assert tt.pending_count() == 0

        asyncio.run(main())

    def test_failed_task_is_logged_not_swallowed(self, caplog):
        """A tracked task that raises must be visible.

        Nobody awaits these; without the done callback the exception lives on
        the task object and dies with it.
        """
        import asyncio
        import logging

        async def main() -> None:
            async def boom() -> None:
                raise RuntimeError("kaboom")

            task = asyncio.create_task(boom())
            tt.track_task(task)
            try:
                await task
            except RuntimeError:
                pass
            await asyncio.sleep(0)

        with caplog.at_level(logging.ERROR, logger=tt.__name__):
            asyncio.run(main())
        assert any("kaboom" in str(r.exc_info[1]) for r in caplog.records if r.exc_info)
