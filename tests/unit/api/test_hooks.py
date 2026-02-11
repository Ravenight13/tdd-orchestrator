"""Tests for SSE broadcaster hooks module.

Tests the global state management for SSE broadcaster instances.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from tdd_orchestrator.api.hooks import (
    get_sse_broadcaster,
    reset_sse_broadcaster,
    set_sse_broadcaster,
)


class TestGetSseBroadcaster:
    """Tests for get_sse_broadcaster function."""

    def test_returns_none_when_no_broadcaster_set(self) -> None:
        """GIVEN no broadcaster has been set WHEN calling get_sse_broadcaster() THEN it returns None."""
        reset_sse_broadcaster()
        result = get_sse_broadcaster()
        assert result is None

    def test_returns_broadcaster_after_set(self) -> None:
        """GIVEN a broadcaster instance is passed to set_sse_broadcaster WHEN calling get_sse_broadcaster THEN it returns the same instance."""
        reset_sse_broadcaster()
        mock_broadcaster = MagicMock()
        set_sse_broadcaster(mock_broadcaster)

        result = get_sse_broadcaster()

        assert result is mock_broadcaster


class TestSetSseBroadcaster:
    """Tests for set_sse_broadcaster function."""

    def test_replaces_previous_broadcaster_with_new_instance(self) -> None:
        """GIVEN a broadcaster was previously set WHEN calling set_sse_broadcaster with a different instance THEN get_sse_broadcaster returns the new broadcaster."""
        reset_sse_broadcaster()
        first_broadcaster = MagicMock(name="first")
        second_broadcaster = MagicMock(name="second")

        set_sse_broadcaster(first_broadcaster)
        set_sse_broadcaster(second_broadcaster)

        result = get_sse_broadcaster()
        assert result is second_broadcaster
        assert result is not first_broadcaster

    def test_clears_broadcaster_when_set_to_none(self) -> None:
        """GIVEN a broadcaster was previously set WHEN calling set_sse_broadcaster(None) THEN get_sse_broadcaster returns None."""
        reset_sse_broadcaster()
        mock_broadcaster = MagicMock()
        set_sse_broadcaster(mock_broadcaster)

        set_sse_broadcaster(None)

        result = get_sse_broadcaster()
        assert result is None


class TestResetSseBroadcaster:
    """Tests for reset_sse_broadcaster function."""

    def test_clears_global_broadcaster_state(self) -> None:
        """GIVEN a broadcaster was set WHEN calling reset_sse_broadcaster THEN get_sse_broadcaster returns None."""
        mock_broadcaster = MagicMock()
        set_sse_broadcaster(mock_broadcaster)

        reset_sse_broadcaster()

        result = get_sse_broadcaster()
        assert result is None


class TestGlobalStateConsistency:
    """Tests for module-level global state consistency."""

    def test_sequential_set_and_get_calls_maintain_consistency(self) -> None:
        """GIVEN multiple sequential calls to set and get WHEN interleaved in any order THEN get always returns the most recent set value."""
        reset_sse_broadcaster()

        broadcaster_a = MagicMock(name="a")
        broadcaster_b = MagicMock(name="b")
        broadcaster_c = MagicMock(name="c")

        # Initial state
        assert get_sse_broadcaster() is None

        # Set first broadcaster
        set_sse_broadcaster(broadcaster_a)
        assert get_sse_broadcaster() is broadcaster_a

        # Multiple gets return same value
        assert get_sse_broadcaster() is broadcaster_a
        assert get_sse_broadcaster() is broadcaster_a

        # Replace with second
        set_sse_broadcaster(broadcaster_b)
        assert get_sse_broadcaster() is broadcaster_b

        # Clear
        set_sse_broadcaster(None)
        assert get_sse_broadcaster() is None

        # Set third
        set_sse_broadcaster(broadcaster_c)
        assert get_sse_broadcaster() is broadcaster_c

        # Final reset
        reset_sse_broadcaster()
        assert get_sse_broadcaster() is None

    def test_get_does_not_modify_state(self) -> None:
        """GIVEN a broadcaster is set WHEN calling get_sse_broadcaster multiple times THEN the state remains unchanged."""
        reset_sse_broadcaster()
        mock_broadcaster = MagicMock()
        set_sse_broadcaster(mock_broadcaster)

        # Call get multiple times
        result1 = get_sse_broadcaster()
        result2 = get_sse_broadcaster()
        result3 = get_sse_broadcaster()

        # All should return the same instance
        assert result1 is mock_broadcaster
        assert result2 is mock_broadcaster
        assert result3 is mock_broadcaster

    def test_set_overwrites_regardless_of_previous_value(self) -> None:
        """GIVEN any previous state WHEN calling set_sse_broadcaster THEN the new value is stored."""
        reset_sse_broadcaster()

        # From None to instance
        broadcaster1 = MagicMock(name="b1")
        set_sse_broadcaster(broadcaster1)
        assert get_sse_broadcaster() is broadcaster1

        # From instance to different instance
        broadcaster2 = MagicMock(name="b2")
        set_sse_broadcaster(broadcaster2)
        assert get_sse_broadcaster() is broadcaster2

        # From instance to None
        set_sse_broadcaster(None)
        assert get_sse_broadcaster() is None

        # From None to None (should stay None)
        set_sse_broadcaster(None)
        assert get_sse_broadcaster() is None


@pytest.fixture(autouse=True)
def cleanup_broadcaster_state() -> None:
    """Ensure broadcaster state is reset after each test."""
    reset_sse_broadcaster()
    yield  # type: ignore[misc]
    reset_sse_broadcaster()
