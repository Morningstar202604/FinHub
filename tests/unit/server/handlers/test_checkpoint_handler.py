"""
Tests for src/server/handlers/checkpoint_handler.py

Covers:
- get_thread_turns: turn boundary detection, branch walking, HITL resume
- get_retry_checkpoint: checkpoint validation, auto-detection
- Missing checkpoint handling
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cp_tuple(
    checkpoint_id: str,
    parent_checkpoint_id: str | None = None,
    source: str = "loop",
    pending_writes: list | None = None,
):
    """Build a minimal checkpoint tuple matching the structure used by LangGraph."""
    config = {"configurable": {"checkpoint_id": checkpoint_id}}
    parent_config = None
    if parent_checkpoint_id:
        parent_config = {"configurable": {"checkpoint_id": parent_checkpoint_id}}
    return SimpleNamespace(
        config=config,
        parent_config=parent_config,
        metadata={"source": source},
        pending_writes=pending_writes or [],
    )


# ---------------------------------------------------------------------------
# get_thread_turns
# ---------------------------------------------------------------------------


class TestGetThreadTurns:
    """Tests for get_thread_turns."""

    @pytest.mark.asyncio
    async def test_empty_checkpoints_returns_empty_response(self):
        mock_checkpointer = AsyncMock()

        async def empty_alist(config):
            return
            yield  # noqa: unreachable — makes this an async generator

        mock_checkpointer.alist = empty_alist

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            result = await get_thread_turns("t1")

        assert result.thread_id == "t1"
        assert result.turns == []
        assert result.retry_checkpoint_id is None

    @pytest.mark.asyncio
    async def test_single_input_turn(self):
        """One source=input checkpoint should produce one turn."""
        cp1 = _make_cp_tuple("cp-1", source="input")  # Turn 0

        mock_checkpointer = AsyncMock()

        async def alist(config):
            yield cp1

        mock_checkpointer.alist = alist

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            result = await get_thread_turns("t1")

        assert len(result.turns) == 1
        assert result.turns[0].turn_index == 0
        assert result.turns[0].regenerate_checkpoint_id == "cp-1"
        assert result.retry_checkpoint_id == "cp-1"

    @pytest.mark.asyncio
    async def test_multiple_turns_with_loop_checkpoints(self):
        """Two input checkpoints with loop checkpoints in between."""
        # Newest first (as alist returns)
        cp4 = _make_cp_tuple("cp-4", parent_checkpoint_id="cp-3", source="loop")
        cp3 = _make_cp_tuple("cp-3", parent_checkpoint_id="cp-2", source="input")
        cp2 = _make_cp_tuple("cp-2", parent_checkpoint_id="cp-1", source="loop")
        cp1 = _make_cp_tuple("cp-1", source="input")

        mock_checkpointer = AsyncMock()

        async def alist(config):
            for cp in [cp4, cp3, cp2, cp1]:
                yield cp

        mock_checkpointer.alist = alist

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            result = await get_thread_turns("t1")

        assert len(result.turns) == 2
        assert result.turns[0].turn_index == 0
        assert result.turns[0].regenerate_checkpoint_id == "cp-1"
        assert result.turns[1].turn_index == 1
        assert result.turns[1].regenerate_checkpoint_id == "cp-3"
        # edit_checkpoint_id for turn 1 is the parent of the input checkpoint
        assert result.turns[1].edit_checkpoint_id == "cp-2"
        assert result.retry_checkpoint_id == "cp-4"

    @pytest.mark.asyncio
    async def test_hitl_resume_detected_as_turn(self):
        """A checkpoint with __resume__ in pending_writes is treated as a turn boundary."""
        cp2 = _make_cp_tuple(
            "cp-2",
            parent_checkpoint_id="cp-1",
            source="loop",
            pending_writes=[("task-1", "__resume__", {"decisions": [{"type": "approve"}]})],
        )
        cp1 = _make_cp_tuple("cp-1", source="input")

        mock_checkpointer = AsyncMock()

        async def alist(config):
            for cp in [cp2, cp1]:
                yield cp

        mock_checkpointer.alist = alist

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            result = await get_thread_turns("t1")

        # Two turns: source=input at cp-1 and HITL resume at cp-2
        assert len(result.turns) == 2
        assert result.turns[1].regenerate_checkpoint_id == "cp-2"
        # HITL resume turns have no edit_checkpoint_id (only source=input turns do)
        assert result.turns[1].edit_checkpoint_id is None

    @pytest.mark.asyncio
    async def test_checkpointer_error_raises_500(self):
        mock_checkpointer = AsyncMock()

        async def alist_error(config):
            raise RuntimeError("DB connection failed")
            yield  # noqa

        mock_checkpointer.alist = alist_error

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            with pytest.raises(HTTPException) as exc_info:
                await get_thread_turns("t1")
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_branch_tip_checkpoint_id_parameter(self):
        """When branch_tip_checkpoint_id is provided, it is used as the branch tip."""
        cp3 = _make_cp_tuple("cp-3", parent_checkpoint_id="cp-2", source="loop")
        cp2 = _make_cp_tuple("cp-2", parent_checkpoint_id="cp-1", source="input")
        cp1 = _make_cp_tuple("cp-1", source="input")

        mock_checkpointer = AsyncMock()

        async def alist(config):
            for cp in [cp3, cp2, cp1]:
                yield cp

        mock_checkpointer.alist = alist

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_thread_turns

            # Use cp-2 as branch tip (skips cp-3)
            result = await get_thread_turns("t1", branch_tip_checkpoint_id="cp-2")

        # retry_checkpoint_id should be the branch tip, not the newest
        assert result.retry_checkpoint_id == "cp-2"


# ---------------------------------------------------------------------------
# get_retry_checkpoint
# ---------------------------------------------------------------------------


class TestGetRetryCheckpoint:
    """Tests for get_retry_checkpoint."""

    @pytest.mark.asyncio
    async def test_explicit_checkpoint_id_validated(self):
        mock_checkpointer = AsyncMock()
        mock_checkpointer.aget_tuple = AsyncMock(
            return_value=_make_cp_tuple("cp-42")
        )

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1", "checkpoint_id": "cp-42"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_retry_checkpoint

            result = await get_retry_checkpoint("t1", checkpoint_id="cp-42")

        assert result == "cp-42"

    @pytest.mark.asyncio
    async def test_explicit_checkpoint_id_not_found_raises_404(self):
        mock_checkpointer = AsyncMock()
        mock_checkpointer.aget_tuple = AsyncMock(return_value=None)

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1", "checkpoint_id": "missing"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_retry_checkpoint

            with pytest.raises(HTTPException) as exc_info:
                await get_retry_checkpoint("t1", checkpoint_id="missing")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auto_detect_returns_latest(self):
        mock_checkpointer = AsyncMock()
        mock_checkpointer.aget_tuple = AsyncMock(
            return_value=_make_cp_tuple("cp-latest")
        )

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_retry_checkpoint

            result = await get_retry_checkpoint("t1")

        assert result == "cp-latest"

    @pytest.mark.asyncio
    async def test_auto_detect_no_checkpoints_raises_404(self):
        mock_checkpointer = AsyncMock()
        mock_checkpointer.aget_tuple = AsyncMock(return_value=None)

        with (
            patch(
                "src.server.handlers.checkpoint_handler.get_checkpointer",
                return_value=mock_checkpointer,
            ),
            patch(
                "src.server.handlers.checkpoint_handler.build_checkpoint_config",
                return_value={"configurable": {"thread_id": "t1"}},
            ),
        ):
            from src.server.handlers.checkpoint_handler import get_retry_checkpoint

            with pytest.raises(HTTPException) as exc_info:
                await get_retry_checkpoint("t1")
            assert exc_info.value.status_code == 404
