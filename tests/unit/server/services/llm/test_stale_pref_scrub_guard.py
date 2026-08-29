"""The stale-model-preference scrubber must not act on an empty catalog.

Regression: ``resolvable()`` asks the manifest whether a model name still
exists. When the manifest fails to load, every name answers "no" and the
scrubber deletes the user's whole model preference set through a merge-upsert
that keeps no copy. There is no undo, so the guard is the fix.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.llm.availability import _cleanup_stale_model_preferences

STORED_PREFS = {
    "preferred_model": "some-model",
    "preferred_flash_model": "some-flash",
    "fetch_model": "some-fetch",
    "compaction_model": "some-compaction",
    "fallback_models": ["fallback-a", "fallback-b"],
    "profiles": {"some-model": {"reasoning_effort": "high"}},
}


def _catalog(names):
    mc = MagicMock()
    mc.llm_config = {n: {"model_id": n} for n in names}
    mc.get_model_config.side_effect = lambda n: mc.llm_config.get(n)
    return mc


async def _run(catalog_names):
    upsert = AsyncMock()
    with (
        patch("src.llms.llm.LLM.get_model_config", return_value=_catalog(catalog_names)),
        patch(
            "src.server.services.llm.config.get_model_preference",
            AsyncMock(return_value=dict(STORED_PREFS)),
        ),
        patch("src.server.database.user.invalidate_user_prefs_cache", AsyncMock()),
        patch("src.server.database.user.upsert_user_preferences", upsert),
        patch("ptc_agent.agent.graph.invalidate_user_profile_cache", AsyncMock()),
    ):
        removed = await _cleanup_stale_model_preferences("user-1")
    return removed, upsert


@pytest.mark.asyncio
async def test_empty_manifest_scrubs_nothing_and_writes_nothing():
    """The destructive case. An empty catalog means "not loaded", not "all gone"."""
    removed, upsert = await _run([])
    assert removed == []
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_loaded_manifest_still_scrubs_what_really_vanished():
    """The guard must not disable the feature it is protecting."""
    removed, upsert = await _run(["something-else"])
    assert removed, "a populated catalog should still scrub names it does not contain"
    upsert.assert_awaited_once()
    written = upsert.await_args.kwargs["other_preference"]
    assert written["preferred_model"] is None
