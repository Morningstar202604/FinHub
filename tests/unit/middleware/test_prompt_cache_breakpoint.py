"""Integration test: prompt cache breakpoint placement across the middleware chain.

Verifies that the system message ends up with 4 content blocks in the correct
order, and that only the skills block (block index 1) carries cache_control —
the breakpoint that Anthropic uses for prefix caching.

Middleware chain (first = outermost = runs first):
    SkillsMiddleware  →  appends skills manifest (block 1)
    AnthropicPromptCachingMiddleware  →  tags LAST block it sees with cache_control
    WorkspaceContextMiddleware  →  appends agent.md (block 2)
    RuntimeContextMiddleware  →  appends time + profile (block 3)

Expected final system message blocks:
    [0] static system prompt         — no cache_control
    [1] skills manifest              — cache_control (breakpoint)
    [2] agent.md                     — no cache_control
    [3] current_time + user_profile  — no cache_control
"""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_anthropic.chat_models import ChatAnthropic
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.messages import SystemMessage

from ptc_agent.agent.middleware._utils import append_to_system_message
from ptc_agent.agent.middleware.runtime_context import RuntimeContextMiddleware
from ptc_agent.agent.middleware.workspace_context import WorkspaceContextMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_request(system_prompt: str) -> ModelRequest:
    """Create a ModelRequest with a mock ChatAnthropic model."""
    model = MagicMock(spec=ChatAnthropic)
    return ModelRequest(
        model=model,
        messages=[],
        system_prompt=system_prompt,
    )


def _fake_skills_middleware():
    """Simulate SkillsMiddleware by appending a skills manifest block."""

    class FakeSkillsMiddleware:
        async def awrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
        ) -> ModelResponse:
            new_sys = append_to_system_message(
                request.system_message,
                "<skills_manifest>\n- skill_a\n- skill_b\n</skills_manifest>",
            )
            return await handler(request.override(system_message=new_sys))

    return FakeSkillsMiddleware()


def _compose_middleware(middlewares, final_handler):
    """Compose middlewares: first in list = outermost = runs first.

    Each middleware wraps the next, producing a single callable that
    processes the request through the full chain.
    """

    async def chain(request: ModelRequest) -> ModelResponse:
        return await final_handler(request)

    # Build from innermost to outermost
    for mw in reversed(middlewares):
        outer_handler = chain

        async def wrapper(req, *, _mw=mw, _h=outer_handler):
            return await _mw.awrap_model_call(req, _h)

        chain = wrapper

    return chain


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestPromptCacheBreakpoint:
    """Verify cache_control breakpoint placement across the full middleware chain."""

    @pytest.mark.asyncio
    async def test_block_ordering_and_breakpoint(self):
        """Cache breakpoint should be on the skills block (block 1 only)."""
        # 1. Build the middleware chain in the same order as agent.py
        skills_mw = _fake_skills_middleware()
        caching_mw = AnthropicPromptCachingMiddleware(
            unsupported_model_behavior="ignore"
        )

        # Mock session for WorkspaceContextMiddleware
        session = MagicMock()
        session.get_agent_md = AsyncMock(return_value="# My Workspace\nResearch notes")
        session.conversation_id = "ws-test"
        workspace_mw = WorkspaceContextMiddleware(session=session)

        runtime_mw = RuntimeContextMiddleware(
            current_time="3:42 PM EST, Monday, April 5, 2026",
            user_profile={"name": "Alice", "timezone": "US/Eastern", "locale": "en-US"},
        )

        # Capture the final request that would go to the model
        captured_request = {}

        async def capture_handler(request: ModelRequest) -> ModelResponse:
            captured_request["request"] = request
            return MagicMock()  # dummy response

        # Compose: first = outermost = runs first
        chain = _compose_middleware(
            [skills_mw, caching_mw, workspace_mw, runtime_mw],
            capture_handler,
        )

        # 2. Create initial request with static system prompt
        request = _make_model_request("You are LangAlpha Agent, a research agent.")

        # 3. Run through the chain
        await chain(request)

        # 4. Inspect the final system message
        final_request = captured_request["request"]
        sys_msg = final_request.system_message
        assert sys_msg is not None, "System message should not be None"

        content = sys_msg.content
        assert isinstance(content, list), f"Expected list of blocks, got {type(content)}"
        assert len(content) == 4, (
            f"Expected 4 content blocks (static + skills + agent.md + runtime), "
            f"got {len(content)}"
        )

        # Block 0: Static system prompt — no cache_control
        block0 = content[0]
        assert isinstance(block0, dict), f"Block 0 should be dict, got {type(block0)}"
        assert "You are LangAlpha Agent" in block0["text"]
        assert "cache_control" not in block0, (
            "Block 0 (static prompt) should NOT have cache_control"
        )

        # Block 1: Skills manifest — HAS cache_control (the breakpoint)
        block1 = content[1]
        assert isinstance(block1, dict), f"Block 1 should be dict, got {type(block1)}"
        assert "skills_manifest" in block1["text"]
        assert "cache_control" in block1, (
            "Block 1 (skills) MUST have cache_control — this is the breakpoint"
        )
        assert block1["cache_control"]["type"] == "ephemeral"

        # Block 2: agent.md — no cache_control
        block2 = content[2]
        assert isinstance(block2, dict), f"Block 2 should be dict, got {type(block2)}"
        assert "agentmd" in block2["text"]
        assert "cache_control" not in block2, (
            "Block 2 (agent.md) should NOT have cache_control"
        )

        # Block 3: Runtime context (time + profile) — no cache_control
        block3 = content[3]
        assert isinstance(block3, dict), f"Block 3 should be dict, got {type(block3)}"
        assert "time_awareness" in block3["text"]
        assert "3:42 PM EST" in block3["text"]
        assert "user_profile" in block3["text"]
        assert "Alice" in block3["text"]
        assert "cache_control" not in block3, (
            "Block 3 (runtime context) should NOT have cache_control"
        )

    @pytest.mark.asyncio
    async def test_breakpoint_stable_across_different_times(self):
        """Changing current_time should NOT affect which block has cache_control."""
        skills_mw = _fake_skills_middleware()
        caching_mw = AnthropicPromptCachingMiddleware(
            unsupported_model_behavior="ignore"
        )

        session = MagicMock()
        session.get_agent_md = AsyncMock(return_value="# Notes")
        session.conversation_id = "ws-test"
        workspace_mw = WorkspaceContextMiddleware(session=session)

        captured_blocks = []

        for time_str in [
            "3:42 PM EST, Monday, April 5, 2026",
            "3:43 PM EST, Monday, April 5, 2026",
            "10:00 AM PST, Tuesday, April 6, 2026",
        ]:
            runtime_mw = RuntimeContextMiddleware(
                current_time=time_str,
                user_profile={"name": "Bob", "timezone": "UTC", "locale": "en-US"},
            )

            captured = {}

            async def capture(req, _c=captured):
                _c["req"] = req
                return MagicMock()

            chain = _compose_middleware(
                [skills_mw, caching_mw, workspace_mw, runtime_mw],
                capture,
            )
            await chain(_make_model_request("Static system prompt."))

            blocks = captured["req"].system_message.content
            captured_blocks.append(blocks)

        # All three runs should have cache_control on block 1 only
        for i, blocks in enumerate(captured_blocks):
            assert len(blocks) == 4, f"Run {i}: expected 4 blocks"
            assert "cache_control" not in blocks[0], f"Run {i}: block 0 should not be cached"
            assert "cache_control" in blocks[1], f"Run {i}: block 1 must be cached"
            assert "cache_control" not in blocks[2], f"Run {i}: block 2 should not be cached"
            assert "cache_control" not in blocks[3], f"Run {i}: block 3 should not be cached"

        # The static prefix (blocks 0 and 1 text) should be identical across runs
        for i in range(1, len(captured_blocks)):
            assert captured_blocks[0][0]["text"] == captured_blocks[i][0]["text"], (
                f"Run {i}: static prompt block should be identical"
            )
            # Block 1 text (skills) should also be identical
            assert captured_blocks[0][1]["text"] == captured_blocks[i][1]["text"], (
                f"Run {i}: skills block should be identical"
            )

    @pytest.mark.asyncio
    async def test_no_user_profile_omits_profile_from_runtime_block(self):
        """Without user_profile, runtime context block should still have time_awareness."""
        skills_mw = _fake_skills_middleware()
        caching_mw = AnthropicPromptCachingMiddleware(
            unsupported_model_behavior="ignore"
        )

        session = MagicMock()
        session.get_agent_md = AsyncMock(return_value="# Notes")
        session.conversation_id = "ws-test"
        workspace_mw = WorkspaceContextMiddleware(session=session)

        runtime_mw = RuntimeContextMiddleware(
            current_time="12:00 PM UTC, Monday, April 5, 2026",
            user_profile=None,
        )

        captured = {}

        async def capture(req):
            captured["req"] = req
            return MagicMock()

        chain = _compose_middleware(
            [skills_mw, caching_mw, workspace_mw, runtime_mw],
            capture,
        )
        await chain(_make_model_request("Static prompt."))

        blocks = captured["req"].system_message.content
        assert len(blocks) == 4, f"Expected 4 blocks, got {len(blocks)}"

        # Block 3 should have time but NOT user_profile
        block3 = blocks[3]
        assert "time_awareness" in block3["text"]
        assert "user_profile" not in block3["text"]

        # Breakpoint still on block 1
        assert "cache_control" in blocks[1]
        assert "cache_control" not in blocks[3]
