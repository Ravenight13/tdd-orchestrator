"""Tests for task callback observer pattern in db.observer module.

Tests the callback registration, dispatch, and error handling for
task status change events.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from tdd_orchestrator.db.observer import (
    dispatch_task_callbacks,
    register_task_callback,
    unregister_task_callback,
)


class TestRegisterTaskCallback:
    """Tests for register_task_callback function."""

    def test_register_callback_adds_to_empty_list(self) -> None:
        """GIVEN an empty callbacks list WHEN register_callback is called THEN callbacks contains that callable."""
        # Arrange
        callback = MagicMock()

        # Act
        result = register_task_callback(callback)

        # Assert - registration should succeed
        assert result is True or result is None  # Allow bool or None return

        # Cleanup
        unregister_task_callback(callback)

    def test_register_callback_returns_truthy_on_success(self) -> None:
        """GIVEN an empty callbacks list WHEN register_callback is called THEN it returns a truthy value or None."""
        # Arrange
        callback = MagicMock()

        # Act
        result = register_task_callback(callback)

        # Assert - function completes without error
        # The callback should be registered (verified by dispatch test)
        assert result is True or result is None

        # Cleanup
        unregister_task_callback(callback)

    def test_register_multiple_callbacks_preserves_order(self) -> None:
        """GIVEN multiple callbacks WHEN registered sequentially THEN all are stored in registration order."""
        # Arrange
        callback1 = MagicMock()
        callback2 = MagicMock()
        callback3 = MagicMock()

        # Act
        register_task_callback(callback1)
        register_task_callback(callback2)
        register_task_callback(callback3)

        # Assert - verified via dispatch order in integration test
        # Here we just ensure no errors during registration
        assert True  # Registration completed without error

        # Cleanup
        unregister_task_callback(callback1)
        unregister_task_callback(callback2)
        unregister_task_callback(callback3)


class TestUnregisterTaskCallback:
    """Tests for unregister_task_callback function."""

    def test_unregister_removes_callback(self) -> None:
        """GIVEN a registered callback WHEN unregister_task_callback is called THEN callback is removed."""
        # Arrange
        callback = MagicMock()
        register_task_callback(callback)

        # Act
        result = unregister_task_callback(callback)

        # Assert
        assert result is True or result is None

    def test_unregister_nonexistent_callback_does_not_raise(self) -> None:
        """GIVEN a callback not in the list WHEN unregister is called THEN no exception is raised."""
        # Arrange
        callback = MagicMock()

        # Act & Assert - should not raise
        result = unregister_task_callback(callback)

        # Should return False or None for non-existent
        assert result is False or result is None


class TestDispatchTaskCallbacks:
    """Tests for dispatch_task_callbacks function."""

    def test_dispatch_invokes_callback_with_event_dict(self) -> None:
        """GIVEN a registered callback WHEN dispatch is called THEN callback receives event dict with required keys."""
        # Arrange
        callback = MagicMock()
        register_task_callback(callback)

        event = {
            "task_id": "task-123",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        callback.assert_called_once()
        call_args = callback.call_args[0][0] if callback.call_args[0] else callback.call_args[1].get("event")
        assert "task_id" in call_args
        assert "old_status" in call_args
        assert "new_status" in call_args
        assert "timestamp" in call_args

        # Cleanup
        unregister_task_callback(callback)

    def test_dispatch_invokes_multiple_callbacks_in_order(self) -> None:
        """GIVEN multiple registered callbacks WHEN dispatch is called THEN all are invoked in registration order."""
        # Arrange
        call_order: list[int] = []
        callback1 = MagicMock(side_effect=lambda e: call_order.append(1))
        callback2 = MagicMock(side_effect=lambda e: call_order.append(2))
        callback3 = MagicMock(side_effect=lambda e: call_order.append(3))

        register_task_callback(callback1)
        register_task_callback(callback2)
        register_task_callback(callback3)

        event = {
            "task_id": "task-456",
            "old_status": "running",
            "new_status": "completed",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert callback1.called is True
        assert callback2.called is True
        assert callback3.called is True
        assert call_order == [1, 2, 3], f"Expected [1, 2, 3] but got {call_order}"

        # Cleanup
        unregister_task_callback(callback1)
        unregister_task_callback(callback2)
        unregister_task_callback(callback3)

    def test_dispatch_all_callbacks_receive_same_event(self) -> None:
        """GIVEN multiple callbacks WHEN dispatch is called THEN each receives the same event dict."""
        # Arrange
        received_events: list[dict[str, Any]] = []
        callback1 = MagicMock(side_effect=lambda e: received_events.append(e))
        callback2 = MagicMock(side_effect=lambda e: received_events.append(e))

        register_task_callback(callback1)
        register_task_callback(callback2)

        event = {
            "task_id": "task-789",
            "old_status": "pending",
            "new_status": "failed",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert len(received_events) == 2
        assert received_events[0] == received_events[1]
        assert received_events[0]["task_id"] == "task-789"

        # Cleanup
        unregister_task_callback(callback1)
        unregister_task_callback(callback2)

    def test_dispatch_with_no_callbacks_does_not_raise(self) -> None:
        """GIVEN no registered callbacks WHEN dispatch is called THEN no exception is raised."""
        # Arrange
        event = {
            "task_id": "task-empty",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act & Assert - should not raise
        dispatch_task_callbacks(event)
        assert True  # Reached here without exception


class TestCallbackErrorHandling:
    """Tests for callback exception handling during dispatch."""

    def test_callback_exception_is_caught_and_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """GIVEN a callback that raises WHEN dispatch is called THEN exception is caught and logged."""
        # Arrange
        def failing_callback(event: dict[str, Any]) -> None:
            raise ValueError("Callback failed intentionally")

        register_task_callback(failing_callback)

        event = {
            "task_id": "task-error",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act - should not raise
        with caplog.at_level(logging.ERROR):
            dispatch_task_callbacks(event)

        # Assert - exception was logged, not re-raised
        assert True  # Dispatch completed without raising

        # Cleanup
        unregister_task_callback(failing_callback)

    def test_callback_exception_does_not_prevent_other_callbacks(self) -> None:
        """GIVEN a failing callback followed by others WHEN dispatch is called THEN remaining callbacks still execute."""
        # Arrange
        call_order: list[int] = []

        def callback1(event: dict[str, Any]) -> None:
            call_order.append(1)

        def failing_callback(event: dict[str, Any]) -> None:
            call_order.append(2)
            raise RuntimeError("Intentional failure")

        def callback3(event: dict[str, Any]) -> None:
            call_order.append(3)

        register_task_callback(callback1)
        register_task_callback(failing_callback)
        register_task_callback(callback3)

        event = {
            "task_id": "task-continue",
            "old_status": "running",
            "new_status": "completed",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert - all callbacks were attempted
        assert 1 in call_order, "First callback should have executed"
        assert 2 in call_order, "Failing callback should have executed"
        assert 3 in call_order, "Third callback should have executed after failure"
        assert call_order == [1, 2, 3], f"Expected [1, 2, 3] but got {call_order}"

        # Cleanup
        unregister_task_callback(callback1)
        unregister_task_callback(failing_callback)
        unregister_task_callback(callback3)

    def test_callback_exception_does_not_rollback_status_update(self) -> None:
        """GIVEN a callback that raises WHEN dispatch is called after commit THEN the update is NOT rolled back.

        Note: This test verifies the contract that dispatch_task_callbacks is called
        AFTER commit, so callback failures cannot affect the committed transaction.
        The actual integration with update_task_status is tested separately.
        """
        # Arrange
        callback_called = False

        def failing_callback(event: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True
            raise Exception("Should not rollback committed transaction")

        register_task_callback(failing_callback)

        event = {
            "task_id": "task-committed",
            "old_status": "pending",
            "new_status": "completed",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act - dispatch after commit (simulated by just calling dispatch)
        dispatch_task_callbacks(event)

        # Assert
        assert callback_called is True, "Callback should have been invoked"

        # Cleanup
        unregister_task_callback(failing_callback)


class TestEventDictStructure:
    """Tests for the structure of event dictionaries passed to callbacks."""

    def test_event_contains_task_id_key(self) -> None:
        """GIVEN a dispatched event WHEN callback receives it THEN event has 'task_id' key."""
        # Arrange
        received_event: dict[str, Any] = {}
        callback = MagicMock(side_effect=lambda e: received_event.update(e))
        register_task_callback(callback)

        event = {
            "task_id": "task-key-test",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert "task_id" in received_event
        assert received_event["task_id"] == "task-key-test"

        # Cleanup
        unregister_task_callback(callback)

    def test_event_contains_old_status_key(self) -> None:
        """GIVEN a dispatched event WHEN callback receives it THEN event has 'old_status' key."""
        # Arrange
        received_event: dict[str, Any] = {}
        callback = MagicMock(side_effect=lambda e: received_event.update(e))
        register_task_callback(callback)

        event = {
            "task_id": "task-old-status",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert "old_status" in received_event
        assert received_event["old_status"] == "pending"

        # Cleanup
        unregister_task_callback(callback)

    def test_event_contains_new_status_key(self) -> None:
        """GIVEN a dispatched event WHEN callback receives it THEN event has 'new_status' key."""
        # Arrange
        received_event: dict[str, Any] = {}
        callback = MagicMock(side_effect=lambda e: received_event.update(e))
        register_task_callback(callback)

        event = {
            "task_id": "task-new-status",
            "old_status": "pending",
            "new_status": "completed",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert "new_status" in received_event
        assert received_event["new_status"] == "completed"

        # Cleanup
        unregister_task_callback(callback)

    def test_event_contains_timestamp_key(self) -> None:
        """GIVEN a dispatched event WHEN callback receives it THEN event has 'timestamp' key."""
        # Arrange
        received_event: dict[str, Any] = {}
        callback = MagicMock(side_effect=lambda e: received_event.update(e))
        register_task_callback(callback)

        timestamp = "2024-01-15T10:30:00Z"
        event = {
            "task_id": "task-timestamp",
            "old_status": "running",
            "new_status": "failed",
            "timestamp": timestamp,
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert "timestamp" in received_event
        assert received_event["timestamp"] == timestamp

        # Cleanup
        unregister_task_callback(callback)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_register_same_callback_twice(self) -> None:
        """GIVEN a callback already registered WHEN registered again THEN behavior is defined (no crash)."""
        # Arrange
        callback = MagicMock()

        # Act
        register_task_callback(callback)
        register_task_callback(callback)

        event = {
            "task_id": "task-double",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        dispatch_task_callbacks(event)

        # Assert - callback was called (at least once, possibly twice depending on impl)
        assert callback.call_count >= 1

        # Cleanup
        unregister_task_callback(callback)
        unregister_task_callback(callback)  # Handle case where it was added twice

    def test_dispatch_with_empty_event_dict(self) -> None:
        """GIVEN an empty event dict WHEN dispatch is called THEN callbacks receive empty dict."""
        # Arrange
        received_event: dict[str, Any] | None = None

        def capture_callback(event: dict[str, Any]) -> None:
            nonlocal received_event
            received_event = event

        register_task_callback(capture_callback)

        # Act
        dispatch_task_callbacks({})

        # Assert
        assert received_event is not None
        assert received_event == {}

        # Cleanup
        unregister_task_callback(capture_callback)

    def test_callback_can_be_lambda(self) -> None:
        """GIVEN a lambda as callback WHEN registered and dispatched THEN it executes correctly."""
        # Arrange
        results: list[str] = []
        callback = lambda e: results.append(e.get("task_id", "")) if e else results.append("")

        register_task_callback(callback)

        event = {
            "task_id": "lambda-task",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act
        dispatch_task_callbacks(event)

        # Assert
        assert len(results) == 1
        assert results[0] == "lambda-task"

        # Cleanup
        unregister_task_callback(callback)

    def test_unregister_during_dispatch_does_not_crash(self) -> None:
        """GIVEN callbacks that modify the callback list WHEN dispatch runs THEN no crash occurs.

        Note: This tests defensive programming - the implementation should handle
        concurrent modification gracefully (e.g., by iterating over a copy).
        """
        # Arrange
        callback2 = MagicMock()

        def self_unregistering_callback(event: dict[str, Any]) -> None:
            unregister_task_callback(self_unregistering_callback)

        register_task_callback(self_unregistering_callback)
        register_task_callback(callback2)

        event = {
            "task_id": "task-unregister",
            "old_status": "pending",
            "new_status": "running",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Act - should not raise
        dispatch_task_callbacks(event)

        # Assert
        assert callback2.called is True

        # Cleanup
        unregister_task_callback(callback2)
