"""
Tests for ptc_agent.core.sandbox.retry — async_retry_with_backoff utility.

Covers:
- Succeeds on first try
- Retries on transient errors (SAFE policy)
- UNSAFE policy raises SandboxTransientError immediately
- Non-transient errors raise immediately
- on_transient callback invoked
- Total timeout exceeded
- Max retries exceeded
"""

import pytest

from ptc_agent.core.sandbox.ptc_sandbox import SandboxTransientError
from ptc_agent.core.sandbox.retry import RetryPolicy, async_retry_with_backoff


class TestAsyncRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        async def ok():
            return "success"

        result = await async_retry_with_backoff(
            ok,
            retry_policy=RetryPolicy.SAFE,
            is_transient=lambda _: True,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("reset")
            return "ok"

        result = await async_retry_with_backoff(
            flaky,
            retry_policy=RetryPolicy.SAFE,
            is_transient=lambda e: isinstance(e, ConnectionError),
            initial_delay_s=0.01,
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_unsafe_policy_no_retry(self):
        """UNSAFE policy raises SandboxTransientError on first transient error."""
        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("reset")

        with pytest.raises(SandboxTransientError, match="unsafe"):
            await async_retry_with_backoff(
                fail,
                retry_policy=RetryPolicy.UNSAFE,
                is_transient=lambda e: isinstance(e, ConnectionError),
            )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_non_transient_error_raises_immediately(self):
        """Non-transient errors should propagate without retry."""
        call_count = 0

        async def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad argument")

        with pytest.raises(ValueError, match="bad argument"):
            await async_retry_with_backoff(
                bad,
                retry_policy=RetryPolicy.SAFE,
                is_transient=lambda e: isinstance(e, ConnectionError),
            )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_on_transient_callback_called(self):
        callback_called = False

        async def on_transient():
            nonlocal callback_called
            callback_called = True

        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("reset")
            return "ok"

        result = await async_retry_with_backoff(
            flaky,
            retry_policy=RetryPolicy.SAFE,
            is_transient=lambda e: isinstance(e, ConnectionError),
            on_transient=on_transient,
            initial_delay_s=0.01,
        )
        assert result == "ok"
        assert callback_called is True

    @pytest.mark.asyncio
    async def test_total_timeout_exceeded(self):
        """Should raise SandboxTransientError when total_timeout is exceeded."""
        async def always_fail():
            raise ConnectionError("timeout test")

        with pytest.raises(SandboxTransientError, match="timed out"):
            await async_retry_with_backoff(
                always_fail,
                retry_policy=RetryPolicy.SAFE,
                is_transient=lambda e: isinstance(e, ConnectionError),
                total_timeout=0.0,  # Immediate timeout
                retries=5,
            )

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Should raise SandboxTransientError after exhausting retries."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        with pytest.raises(SandboxTransientError, match="after retries"):
            await async_retry_with_backoff(
                always_fail,
                retry_policy=RetryPolicy.SAFE,
                is_transient=lambda e: isinstance(e, ConnectionError),
                retries=3,
                initial_delay_s=0.01,
                total_timeout=60.0,
            )
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_on_transient_callback_called_only_once(self):
        """on_transient should be called at most once even with multiple retries."""
        callback_count = 0

        async def on_transient():
            nonlocal callback_count
            callback_count += 1

        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ConnectionError("reset")
            return "ok"

        result = await async_retry_with_backoff(
            flaky,
            retry_policy=RetryPolicy.SAFE,
            is_transient=lambda e: isinstance(e, ConnectionError),
            on_transient=on_transient,
            initial_delay_s=0.01,
        )
        assert result == "ok"
        assert callback_count == 1

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        """func should receive positional and keyword args."""
        async def add(a, b, multiplier=1):
            return (a + b) * multiplier

        result = await async_retry_with_backoff(
            add,
            3,
            4,
            retry_policy=RetryPolicy.SAFE,
            is_transient=lambda _: False,
            multiplier=2,
        )
        assert result == 14
