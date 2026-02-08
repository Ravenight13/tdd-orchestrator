"""Tests for decomposer error handling and resilience.

Tests malformed LLM response handling and Claude Agent SDK
subscription error recovery scenarios.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tdd_orchestrator.decomposition import ParsedSpec
from tdd_orchestrator.decomposition.config import DecompositionConfig
from tdd_orchestrator.decomposition.decomposer import (
    LLMDecompositionError,
    LLMDecomposer,
)
from tdd_orchestrator.decomposition.llm_client import (
    LLMClientError,
    LLMResponseParseError,
    MockLLMClient,
    SubscriptionErrorSimulator,
)


class TestMalformedLLMResponses:
    """Test decomposer resilience to malformed LLM responses."""

    @pytest.mark.asyncio
    async def test_llm_returns_extra_fields(self) -> None:
        """Test that decomposer ignores unexpected fields from LLM."""
        # Pass 2 response with extra unexpected fields
        response_with_extra = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": 5,
                    "estimated_lines": 50,
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": ["TestComponent"],
                    # Extra fields that should be ignored
                    "extra_field": "should be ignored",
                    "unexpected_data": {"nested": "value"},
                    "random_number": 42,
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_extra,
                "acceptance criteria": '["Criterion 1", "Criterion 2"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        tasks = await decomposer.decompose(parsed_spec)

        # Should succeed and ignore extra fields
        assert len(tasks) == 1
        assert tasks[0].title == "Test task"
        assert tasks[0].goal == "Test goal"
        # Verify extra fields are not in to_dict() output
        task_dict = tasks[0].to_dict()
        assert "extra_field" not in task_dict
        assert "unexpected_data" not in task_dict
        assert "random_number" not in task_dict

    @pytest.mark.asyncio
    async def test_llm_returns_wrong_types(self) -> None:
        """Test that decomposer handles type mismatches gracefully."""
        # Pass 2 response with wrong types
        response_with_wrong_types = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": "not-a-number",  # Should be int
                    "estimated_lines": "also-not-a-number",  # Should be int
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": "single-string",  # Should be list
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_wrong_types,
                "acceptance criteria": '["Criterion 1"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        # Currently, the decomposer accepts type mismatches without validation
        # This test documents the current behavior (not strict type checking)
        tasks = await decomposer.decompose(parsed_spec)

        # System currently allows wrong types to pass through
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Test task"
        assert task.goal == "Test goal"
        # CURRENT BEHAVIOR: Wrong types are not rejected
        # estimated_tests is still a string (not converted to int)
        assert task.estimated_tests == "not-a-number"  # Type mismatch accepted
        assert task.estimated_lines == "also-not-a-number"  # Type mismatch accepted
        # components might be converted to list or remain as string
        # This documents that type validation is not currently enforced

    @pytest.mark.asyncio
    async def test_llm_returns_null_values(self) -> None:
        """Test that decomposer handles null values in optional fields."""
        # Pass 2 response with null values
        response_with_nulls = json.dumps(
            [
                {
                    "title": "Test task",
                    "goal": "Test goal",
                    "estimated_tests": 5,
                    "estimated_lines": 50,
                    "test_file": "test.py",
                    "impl_file": "impl.py",
                    "components": None,  # Optional field with null
                    "phase": None,  # Optional field with null
                }
            ]
        )

        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [{"cycle_number": 1, "cycle_title": "Test", "phase": "Core"}]
                ),
                "Decompose this TDD cycle": response_with_nulls,
                "acceptance criteria": '["Criterion 1", "Criterion 2"]',
            }
        )
        decomposer = LLMDecomposer(client=client)
        parsed_spec = ParsedSpec(raw_content="test spec")

        tasks = await decomposer.decompose(parsed_spec)

        # Should handle null values gracefully
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Test task"
        # Null components should default to empty list
        assert task.components == [] or task.components is None
        # Null phase should default to 0 or None
        assert isinstance(task.phase, int) or task.phase is None


class TestSubscriptionErrorRecovery:
    """Tests for decomposer handling of Claude Agent SDK subscription errors.

    IMPORTANT: We use subscription-based auth via 'claude login', NOT API keys.
    These tests simulate subscription-model errors, not API key errors.

    Key differences from API key testing:
    - No 401/403 HTTP errors (subscription uses session auth)
    - No 429 rate limits (subscription uses monthly quotas)
    - Errors wrapped as LLMClientError by ClaudeAgentSDKClient
    """

    @pytest.mark.asyncio
    async def test_session_expired_suggests_relogin(self) -> None:
        """Verify session expiration error suggests 'claude login'."""
        client = SubscriptionErrorSimulator(error_type="session_expired")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention re-authentication via claude login
        assert "session" in error_msg or "login" in error_msg or "expired" in error_msg

    @pytest.mark.asyncio
    async def test_quota_exceeded_indicates_monthly_limit(self) -> None:
        """Verify quota exceeded error indicates monthly subscription limit."""
        client = SubscriptionErrorSimulator(error_type="quota_exceeded")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention quota/subscription, NOT rate limit
        assert "quota" in error_msg or "subscription" in error_msg or "monthly" in error_msg

    @pytest.mark.asyncio
    async def test_sdk_not_installed_helpful_message(self) -> None:
        """Verify SDK not installed error provides helpful guidance."""
        client = SubscriptionErrorSimulator(error_type="sdk_not_installed")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        # Should mention SDK installation or claude login
        assert "sdk" in error_msg or "claude" in error_msg or "installed" in error_msg

    @pytest.mark.asyncio
    async def test_timeout_propagates_correctly(self) -> None:
        """Verify timeout errors are propagated appropriately."""
        client = SubscriptionErrorSimulator(error_type="timeout")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, asyncio.TimeoutError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connection_error_handled_gracefully(self) -> None:
        """Verify network errors don't crash decomposer."""
        client = SubscriptionErrorSimulator(error_type="connection_error")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, ConnectionError)):
            await decomposer.decompose(ParsedSpec(raw_content="test"))

    @pytest.mark.asyncio
    async def test_malformed_response_uses_fallback(self) -> None:
        """Verify malformed model response falls back to existing cycles."""
        client = SubscriptionErrorSimulator(error_type="malformed_response")
        decomposer = LLMDecomposer(client=client)

        # Spec with existing TDD cycles for fallback
        spec = ParsedSpec(
            raw_content="test",
            tdd_cycles=[
                {
                    "cycle_number": 1,
                    "title": "Fallback Cycle",
                    "components": ["FallbackComponent"],
                }
            ],
        )

        # Should fall back to existing cycles when model returns garbage
        cycles = await decomposer._extract_cycles(spec)
        assert len(cycles) == 1
        assert cycles[0]["title"] == "Fallback Cycle"

    @pytest.mark.asyncio
    async def test_model_unavailable_error_clear(self) -> None:
        """Verify model unavailable error is clear about the issue."""
        client = SubscriptionErrorSimulator(error_type="model_unavailable")
        decomposer = LLMDecomposer(client=client)

        with pytest.raises((LLMDecompositionError, LLMClientError)) as exc_info:
            await decomposer.decompose(ParsedSpec(raw_content="test"))

        error_msg = str(exc_info.value).lower()
        assert "unavailable" in error_msg or "model" in error_msg

    @pytest.mark.asyncio
    async def test_partial_response_handled(self) -> None:
        """Verify truncated responses from model don't crash decomposer."""
        client = SubscriptionErrorSimulator(error_type="partial_response")
        decomposer = LLMDecomposer(client=client)

        # Should raise parse error or fall back, not crash
        with pytest.raises((LLMDecompositionError, LLMResponseParseError)):
            await decomposer.decompose(ParsedSpec(raw_content="test"))

    @pytest.mark.asyncio
    async def test_metrics_track_subscription_errors(self) -> None:
        """Verify decomposition metrics track subscription errors."""
        client = SubscriptionErrorSimulator(error_type="quota_exceeded")
        decomposer = LLMDecomposer(client=client)

        try:
            await decomposer.decompose(ParsedSpec(raw_content="test"))
        except Exception:
            pass  # Expected to fail

        metrics = decomposer.get_metrics()
        assert len(metrics.errors) > 0

    @pytest.mark.asyncio
    async def test_call_limit_prevents_runaway_usage(self) -> None:
        """Verify LLM call limit prevents excessive subscription usage."""
        # Mock that always returns valid response (simulating working subscription)
        client = MockLLMClient(
            responses={
                "extract TDD cycles": json.dumps(
                    [
                        {
                            "cycle_number": i,
                            "cycle_title": f"Cycle {i}",
                            "components": [],
                        }
                        for i in range(1, 20)
                    ]
                ),  # 19 cycles would use many calls
                "Cycle": json.dumps(
                    [
                        {
                            "title": "Task",
                            "goal": "Goal",
                            "estimated_tests": 5,
                            "estimated_lines": 20,
                            "test_file": "t.py",
                            "impl_file": "i.py",
                            "components": [],
                        }
                    ]
                ),
                "acceptance criteria": json.dumps(["AC"]),
            }
        )

        # Very low limit to protect subscription quota
        config = DecompositionConfig(
            max_total_llm_calls=5,
            max_cycles_per_spec=20,
        )
        decomposer = LLMDecomposer(client=client, config=config)

        # Decomposer logs warnings but doesn't raise when limit hit
        await decomposer.decompose(ParsedSpec(raw_content="test"))

        # Should have errors in metrics about exceeding limit
        metrics = decomposer.get_metrics()
        assert len(metrics.errors) > 0
        assert any("limit" in err.lower() for err in metrics.errors)
