"""Tests for SSE bridge wiring circuit breaker callbacks."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from tdd_orchestrator.api.sse_bridge import wire_circuit_breaker_sse


class TestWireCircuitBreakerSSE:
    """Tests for wire_circuit_breaker_sse function."""

    def test_registers_callback_on_metrics_collector(self) -> None:
        """GIVEN an SSEBroadcaster and MetricsCollector, WHEN wire_circuit_breaker_sse is called, THEN a callback is registered."""
        broadcaster = MagicMock()
        collector = MagicMock()
        collector.on_circuit_breaker_state_change = MagicMock()

        wire_circuit_breaker_sse(broadcaster, collector)

        collector.on_circuit_breaker_state_change.assert_called_once()
        registered_callback = collector.on_circuit_breaker_state_change.call_args[0][0]
        assert callable(registered_callback)

    def test_callback_triggers_sse_broadcast_with_correct_event_type(self) -> None:
        """GIVEN wire_circuit_breaker_sse has been called, WHEN circuit breaker state changes, THEN SSE event is broadcast with type 'circuit_breaker_state_changed'."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t1",
            "old_state": "closed",
            "new_state": "open",
            "failure_count": 5,
        }
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        assert call_args[1]["event_type"] == "circuit_breaker_state_changed"

    def test_callback_broadcasts_json_data_with_required_fields(self) -> None:
        """GIVEN wire_circuit_breaker_sse has been called, WHEN callback fires, THEN JSON data contains task_id, old_state, new_state, failure_count, and ISO-8601 timestamp."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t1",
            "old_state": "closed",
            "new_state": "open",
            "failure_count": 5,
        }
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        data_str = call_args[1]["data"]
        data = json.loads(data_str)

        assert data["task_id"] == "t1"
        assert data["old_state"] == "closed"
        assert data["new_state"] == "open"
        assert data["failure_count"] == 5
        assert "timestamp" in data
        # Validate ISO-8601 format by parsing it
        datetime.fromisoformat(data["timestamp"])

    def test_multiple_clients_receive_circuit_breaker_event(self) -> None:
        """GIVEN two SSE clients are connected, WHEN circuit breaker transitions, THEN both clients receive the event."""
        broadcaster = MagicMock()
        broadcast_calls: list[dict[str, Any]] = []

        def mock_broadcast(**kwargs: Any) -> None:
            broadcast_calls.append(kwargs)

        broadcaster.broadcast = MagicMock(side_effect=mock_broadcast)
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t2",
            "old_state": "open",
            "new_state": "half_open",
            "failure_count": 0,
        }
        registered_callback(payload)

        # The broadcaster is called once; it's the broadcaster's job to send to all clients
        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        data = json.loads(call_args[1]["data"])
        assert data["new_state"] == "half_open"

    def test_callback_completes_without_error_when_no_clients_connected(self) -> None:
        """GIVEN no SSE clients are connected, WHEN callback fires, THEN it completes without error."""
        broadcaster = MagicMock()
        # Simulate no clients - broadcast succeeds but does nothing
        broadcaster.broadcast = MagicMock(return_value=None)
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t3",
            "old_state": "half_open",
            "new_state": "closed",
            "failure_count": 0,
        }
        # Should not raise
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()

    def test_callback_catches_broadcast_exception_and_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """GIVEN broadcast raises an exception, WHEN callback fires, THEN exception is caught and warning is logged."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock(side_effect=RuntimeError("disconnected transport"))
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t4",
            "old_state": "closed",
            "new_state": "open",
            "failure_count": 3,
        }

        with caplog.at_level(logging.WARNING):
            # Should not raise despite broadcast exception
            registered_callback(payload)

        # Verify warning was logged
        assert any(
            "warning" in record.levelname.lower() or record.levelno == logging.WARNING
            for record in caplog.records
        )

    def test_callback_does_not_propagate_exception_to_metrics_collector(self) -> None:
        """GIVEN broadcast raises exception, WHEN callback fires, THEN error does not propagate."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock(side_effect=RuntimeError("transport error"))
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t5",
            "old_state": "open",
            "new_state": "half_open",
            "failure_count": 5,
        }

        # This should not raise - exception should be caught internally
        try:
            registered_callback(payload)
            exception_raised = False
        except Exception:
            exception_raised = True

        assert exception_raised is False


class TestWireCircuitBreakerSSEEdgeCases:
    """Edge case tests for wire_circuit_breaker_sse."""

    def test_callback_handles_empty_task_id(self) -> None:
        """GIVEN payload with empty task_id, WHEN callback fires, THEN event is still broadcast."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "",
            "old_state": "closed",
            "new_state": "open",
            "failure_count": 1,
        }
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        data = json.loads(call_args[1]["data"])
        assert data["task_id"] == ""

    def test_callback_handles_zero_failure_count(self) -> None:
        """GIVEN payload with failure_count=0, WHEN callback fires, THEN event contains failure_count=0."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t6",
            "old_state": "open",
            "new_state": "closed",
            "failure_count": 0,
        }
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        data = json.loads(call_args[1]["data"])
        assert data["failure_count"] == 0

    def test_callback_handles_high_failure_count(self) -> None:
        """GIVEN payload with high failure_count, WHEN callback fires, THEN event contains correct count."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payload = {
            "task_id": "t7",
            "old_state": "half_open",
            "new_state": "open",
            "failure_count": 999999,
        }
        registered_callback(payload)

        broadcaster.broadcast.assert_called_once()
        call_args = broadcaster.broadcast.call_args
        data = json.loads(call_args[1]["data"])
        assert data["failure_count"] == 999999

    def test_multiple_state_changes_trigger_multiple_broadcasts(self) -> None:
        """GIVEN wire_circuit_breaker_sse called, WHEN multiple state changes occur, THEN multiple events broadcast."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        payloads = [
            {"task_id": "t8", "old_state": "closed", "new_state": "open", "failure_count": 5},
            {"task_id": "t8", "old_state": "open", "new_state": "half_open", "failure_count": 5},
            {"task_id": "t8", "old_state": "half_open", "new_state": "closed", "failure_count": 0},
        ]

        for payload in payloads:
            registered_callback(payload)

        assert broadcaster.broadcast.call_count == 3

    def test_timestamp_is_recent(self) -> None:
        """GIVEN callback fires, WHEN event is created, THEN timestamp is within reasonable time window."""
        broadcaster = MagicMock()
        broadcaster.broadcast = MagicMock()
        collector = MagicMock()
        registered_callback: Any = None

        def capture_callback(cb: Any) -> None:
            nonlocal registered_callback
            registered_callback = cb

        collector.on_circuit_breaker_state_change = MagicMock(side_effect=capture_callback)

        wire_circuit_breaker_sse(broadcaster, collector)

        assert registered_callback is not None

        before = datetime.now(timezone.utc)
        payload = {
            "task_id": "t9",
            "old_state": "closed",
            "new_state": "open",
            "failure_count": 1,
        }
        registered_callback(payload)
        after = datetime.now(timezone.utc)

        call_args = broadcaster.broadcast.call_args
        data = json.loads(call_args[1]["data"])
        event_time = datetime.fromisoformat(data["timestamp"])

        # Timestamp should be between before and after
        assert before <= event_time <= after
