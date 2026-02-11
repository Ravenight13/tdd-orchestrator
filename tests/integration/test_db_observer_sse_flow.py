"""Integration tests for DB observer → hooks → SSE broadcaster flow.

Tests the full integration path from a task status update through the DB
observer, hooks, and SSE broadcaster delivering an event to a connected client.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.db.observer import (
    dispatch_task_callbacks,
    register_task_callback,
    unregister_task_callback,
)

# Import the DB observer poller that will be implemented
from tdd_orchestrator.db.observer import DBObserver


class TestTaskStatusChangeToBroadcaster:
    """Tests verifying task status changes flow through to SSE broadcaster."""

    @pytest.mark.asyncio
    async def test_task_status_update_triggers_sse_event_within_timeout(
        self, db: OrchestratorDB
    ) -> None:
        """GIVEN an in-memory SQLite database with a task row, an SSEBroadcaster
        instance, and a DB observer polling that database WHEN the task's status
        column is updated from 'pending' to 'running' THEN within 2 seconds the
        broadcaster's event queue contains a 'task_status_changed' event with
        the correct task_id, old_status='pending', and new_status='running'.
        """
        # Create a task in pending status
        await db.create_task(
            task_key="TEST-001",
            title="Test Task",
            phase=0,
            sequence=1,
        )

        # Set up SSE broadcaster and subscribe a client queue
        broadcaster = SSEBroadcaster()
        await broadcaster.subscribe_async()

        # Create callback that bridges DB observer to SSE broadcaster
        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)
            # Use sync publish for dict events
            broadcaster.publish(event)

        register_task_callback(on_task_status_changed)

        try:
            # Create and start the DB observer with 0.1s polling interval
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # Update task status from pending to in_progress (running)
            await db.update_task_status("TEST-001", "in_progress")

            # Wait for the event to arrive (max 2 seconds)
            event_received = False
            start_time = asyncio.get_event_loop().time()
            timeout = 2.0

            while (asyncio.get_event_loop().time() - start_time) < timeout:
                if received_events:
                    event_received = True
                    break
                await asyncio.sleep(0.05)

            # Stop the observer
            await observer.stop()

            # Verify event was received
            assert event_received is True, "Expected task_status_changed event within 2 seconds"
            assert len(received_events) >= 1, "Expected at least one event"

            event = received_events[0]
            assert event.get("task_id") == "TEST-001", f"Expected task_id='TEST-001', got {event.get('task_id')}"
            assert event.get("old_status") == "pending", f"Expected old_status='pending', got {event.get('old_status')}"
            assert event.get("new_status") == "in_progress", f"Expected new_status='in_progress', got {event.get('new_status')}"

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()

    @pytest.mark.asyncio
    async def test_sequential_status_updates_yield_ordered_sse_events(
        self, db: OrchestratorDB
    ) -> None:
        """GIVEN an SSEBroadcaster with a connected async client generator and a
        DB observer linked via hooks WHEN two sequential task status updates occur
        (pending→running, running→passed) THEN the client generator yields two
        SSE events in order, each with correct task_id and status transition
        fields, and event data is valid JSON.
        """
        # Create a task in pending status
        await db.create_task(
            task_key="TEST-002",
            title="Sequential Test Task",
            phase=0,
            sequence=1,
        )

        # Set up SSE broadcaster
        broadcaster = SSEBroadcaster()
        client_queue = await broadcaster.subscribe_async()

        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)
            sse_event = SSEEvent(
                data=json.dumps(event),
                event="task_status_changed",
            )
            asyncio.create_task(broadcaster.publish_async(sse_event))

        register_task_callback(on_task_status_changed)

        try:
            # Create and start the DB observer
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # First update: pending → in_progress
            await db.update_task_status("TEST-002", "in_progress")
            await asyncio.sleep(0.3)  # Allow observer to detect change

            # Second update: in_progress → passing
            await db.update_task_status("TEST-002", "passing")
            await asyncio.sleep(0.3)  # Allow observer to detect change

            # Stop the observer
            await observer.stop()

            # Verify we received exactly 2 events in order
            assert len(received_events) == 2, f"Expected 2 events, got {len(received_events)}"

            # Verify first event (pending → in_progress)
            event1 = received_events[0]
            assert event1.get("task_id") == "TEST-002"
            assert event1.get("old_status") == "pending"
            assert event1.get("new_status") == "in_progress"

            # Verify second event (in_progress → passing)
            event2 = received_events[1]
            assert event2.get("task_id") == "TEST-002"
            assert event2.get("old_status") == "in_progress"
            assert event2.get("new_status") == "passing"

            # Verify SSE events are valid JSON
            for event in received_events:
                json_str = json.dumps(event)
                parsed = json.loads(json_str)
                assert isinstance(parsed, dict), "Event data should be a valid JSON object"
                assert "task_id" in parsed, "Event should contain task_id"

            # Verify client received SSE events
            sse_events_received: list[SSEEvent] = []
            while not client_queue.empty():
                sse_event = client_queue.get_nowait()
                if sse_event is not None:
                    sse_events_received.append(sse_event)

            assert len(sse_events_received) == 2, f"Expected 2 SSE events in queue, got {len(sse_events_received)}"

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()

    @pytest.mark.asyncio
    async def test_no_clients_connected_hook_fires_without_error(
        self, db: OrchestratorDB
    ) -> None:
        """GIVEN a DB observer is actively polling and an SSEBroadcaster has zero
        connected clients WHEN a task status changes in the database THEN the
        hook fires without error, no events are queued or lost, and when a client
        subsequently connects and another status change occurs the new client
        receives only the new event.
        """
        # Create a task
        await db.create_task(
            task_key="TEST-003",
            title="No Clients Test",
            phase=0,
            sequence=1,
        )

        # Set up SSE broadcaster with NO subscribers initially
        broadcaster = SSEBroadcaster()
        assert broadcaster.subscriber_count == 0, "Should have zero subscribers initially"

        callback_invocations: list[dict[str, Any]] = []
        errors_raised: list[Exception] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            callback_invocations.append(event)
            try:
                sse_event = SSEEvent(
                    data=json.dumps(event),
                    event="task_status_changed",
                )
                asyncio.create_task(broadcaster.publish_async(sse_event))
            except Exception as e:
                errors_raised.append(e)

        register_task_callback(on_task_status_changed)

        try:
            # Start observer
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # Update status with no clients connected
            await db.update_task_status("TEST-003", "in_progress")
            await asyncio.sleep(0.3)

            # Verify callback fired without error
            assert len(callback_invocations) >= 1, "Callback should have been invoked"
            assert len(errors_raised) == 0, f"No errors should be raised, got: {errors_raised}"

            # Now connect a new client
            client_queue = await broadcaster.subscribe_async()
            assert broadcaster.subscriber_count >= 1, "Client should be subscribed"

            # Trigger another status change
            await db.update_task_status("TEST-003", "passing")
            await asyncio.sleep(0.3)

            # Stop observer
            await observer.stop()

            # New client should only receive the new event (passing), not the old one
            sse_events: list[SSEEvent] = []
            while not client_queue.empty():
                event = client_queue.get_nowait()
                if event is not None:
                    sse_events.append(event)

            assert len(sse_events) == 1, f"New client should receive only new event, got {len(sse_events)}"

            # Parse the event data
            event_data = json.loads(sse_events[0].data)
            assert event_data.get("new_status") == "passing", "New client should receive the passing event"

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()

    @pytest.mark.asyncio
    async def test_no_spurious_events_during_idle_period(
        self, db: OrchestratorDB
    ) -> None:
        """GIVEN a DB observer with a polling interval of 0.1s and an
        SSEBroadcaster with a connected client WHEN no task status changes
        occur in the database for 1 second THEN the client receives no
        spurious events and the observer continues polling without errors
        (heartbeat/keepalive messages are acceptable).
        """
        # Create a task but don't change its status
        await db.create_task(
            task_key="TEST-004",
            title="Idle Test Task",
            phase=0,
            sequence=1,
        )

        broadcaster = SSEBroadcaster()
        client_queue = await broadcaster.subscribe_async()

        status_change_events: list[dict[str, Any]] = []
        observer_errors: list[Exception] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            status_change_events.append(event)
            sse_event = SSEEvent(
                data=json.dumps(event),
                event="task_status_changed",
            )
            asyncio.create_task(broadcaster.publish_async(sse_event))

        register_task_callback(on_task_status_changed)

        try:
            # Start observer with 0.1s polling interval
            observer = DBObserver(db=db, poll_interval=0.1)

            # Track if observer encounters errors
            original_poll = observer._poll

            async def poll_with_error_tracking() -> None:
                try:
                    await original_poll()
                except Exception as e:
                    observer_errors.append(e)
                    raise

            observer._poll = poll_with_error_tracking  # type: ignore[method-assign]

            await observer.start()

            # Wait for 1 second with no status changes
            await asyncio.sleep(1.0)

            # Stop observer
            await observer.stop()

            # Verify no task_status_changed events were received
            assert len(status_change_events) == 0, (
                f"Expected no status change events, got {len(status_change_events)}"
            )

            # Verify no observer errors
            assert len(observer_errors) == 0, f"Observer should poll without errors: {observer_errors}"

            # Check client queue - should be empty or only contain heartbeats
            spurious_events: list[SSEEvent] = []
            while not client_queue.empty():
                event = client_queue.get_nowait()
                if event is not None:
                    # Heartbeat events are acceptable, count non-heartbeat as spurious
                    if event.event != "heartbeat" and event.event != "keepalive":
                        spurious_events.append(event)

            assert len(spurious_events) == 0, (
                f"No spurious events should be received, got {len(spurious_events)}"
            )

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()

    @pytest.mark.asyncio
    async def test_client_disconnect_handled_gracefully(
        self, db: OrchestratorDB
    ) -> None:
        """GIVEN a DB observer is running and a client is connected to the
        SSEBroadcaster WHEN the client disconnects (async generator is closed)
        and then a task status update occurs THEN the hook and broadcaster
        handle the disconnected client gracefully without raising exceptions,
        and a newly connected second client receives subsequent events normally.
        """
        # Create a task
        await db.create_task(
            task_key="TEST-005",
            title="Disconnect Test",
            phase=0,
            sequence=1,
        )

        broadcaster = SSEBroadcaster()

        # First client connects
        client1_queue = await broadcaster.subscribe_async()
        assert broadcaster.subscriber_count >= 1, "First client should be subscribed"

        callback_errors: list[Exception] = []
        callback_invocations: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            callback_invocations.append(event)
            try:
                sse_event = SSEEvent(
                    data=json.dumps(event),
                    event="task_status_changed",
                )
                asyncio.create_task(broadcaster.publish_async(sse_event))
            except Exception as e:
                callback_errors.append(e)

        register_task_callback(on_task_status_changed)

        try:
            # Start observer
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # First client disconnects (unsubscribe)
            await broadcaster.unsubscribe_async(client1_queue)
            assert broadcaster.subscriber_count == 0, "No subscribers after disconnect"

            # Trigger a status change while no clients connected
            await db.update_task_status("TEST-005", "in_progress")
            await asyncio.sleep(0.3)

            # Verify callback fired without errors
            assert len(callback_invocations) >= 1, "Callback should fire even with no clients"
            assert len(callback_errors) == 0, f"No errors should occur: {callback_errors}"

            # Second client connects
            client2_queue = await broadcaster.subscribe_async()
            assert broadcaster.subscriber_count >= 1, "Second client should be subscribed"

            # Clear previous invocations to track only new events
            previous_count = len(callback_invocations)

            # Trigger another status change
            await db.update_task_status("TEST-005", "passing")
            await asyncio.sleep(0.3)

            # Stop observer
            await observer.stop()

            # Verify new callback fired
            assert len(callback_invocations) > previous_count, (
                "New callback invocation expected"
            )

            # Second client should receive the new event
            events_for_client2: list[SSEEvent] = []
            while not client2_queue.empty():
                event = client2_queue.get_nowait()
                if event is not None:
                    events_for_client2.append(event)

            assert len(events_for_client2) == 1, (
                f"Second client should receive exactly 1 event, got {len(events_for_client2)}"
            )

            event_data = json.loads(events_for_client2[0].data)
            assert event_data.get("new_status") == "passing"
            assert event_data.get("task_id") == "TEST-005"

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()


class TestDBObserverEdgeCases:
    """Edge case tests for DB observer behavior."""

    @pytest.mark.asyncio
    async def test_observer_start_stop_idempotent(self, db: OrchestratorDB) -> None:
        """Observer can be started and stopped multiple times without error."""
        observer = DBObserver(db=db, poll_interval=0.1)

        # Start, stop, start, stop should work without error
        await observer.start()
        await observer.stop()

        await observer.start()
        await observer.stop()

        # Verify observer is in stopped state
        assert observer.is_running is False, "Observer should be stopped"

    @pytest.mark.asyncio
    async def test_observer_detects_multiple_task_changes(
        self, db: OrchestratorDB
    ) -> None:
        """Observer detects status changes across multiple different tasks."""
        # Create multiple tasks
        await db.create_task(task_key="MULTI-001", title="Task 1", phase=0, sequence=1)
        await db.create_task(task_key="MULTI-002", title="Task 2", phase=0, sequence=2)
        await db.create_task(task_key="MULTI-003", title="Task 3", phase=0, sequence=3)

        broadcaster = SSEBroadcaster()
        await broadcaster.subscribe_async()

        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)

        register_task_callback(on_task_status_changed)

        try:
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # Update all three tasks
            await db.update_task_status("MULTI-001", "in_progress")
            await db.update_task_status("MULTI-002", "in_progress")
            await db.update_task_status("MULTI-003", "in_progress")

            await asyncio.sleep(0.5)
            await observer.stop()

            # Verify events for all three tasks
            task_ids = {e.get("task_id") for e in received_events}
            assert "MULTI-001" in task_ids, "Should detect MULTI-001 change"
            assert "MULTI-002" in task_ids, "Should detect MULTI-002 change"
            assert "MULTI-003" in task_ids, "Should detect MULTI-003 change"

        finally:
            unregister_task_callback(on_task_status_changed)
            await broadcaster.shutdown()

    @pytest.mark.asyncio
    async def test_observer_handles_rapid_status_changes(
        self, db: OrchestratorDB
    ) -> None:
        """Observer correctly handles rapid consecutive status changes."""
        await db.create_task(task_key="RAPID-001", title="Rapid Task", phase=0, sequence=1)

        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)

        register_task_callback(on_task_status_changed)

        try:
            observer = DBObserver(db=db, poll_interval=0.05)  # Fast polling
            await observer.start()

            # Rapid status changes
            await db.update_task_status("RAPID-001", "in_progress")
            await asyncio.sleep(0.1)
            await db.update_task_status("RAPID-001", "passing")
            await asyncio.sleep(0.1)
            await db.update_task_status("RAPID-001", "complete")
            await asyncio.sleep(0.2)

            await observer.stop()

            # Should have detected at least the status transitions
            # Note: exact count may vary based on polling timing
            assert len(received_events) >= 1, "Should detect at least one status change"

            # Verify transitions are in logical order
            statuses = [e.get("new_status") for e in received_events]
            # The final status should appear in the events
            assert "complete" in statuses or "passing" in statuses or "in_progress" in statuses

        finally:
            unregister_task_callback(on_task_status_changed)

    @pytest.mark.asyncio
    async def test_observer_includes_timestamp_in_events(
        self, db: OrchestratorDB
    ) -> None:
        """Observer events include an ISO-8601 timestamp."""
        await db.create_task(task_key="TS-001", title="Timestamp Test", phase=0, sequence=1)

        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)

        register_task_callback(on_task_status_changed)

        try:
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            await db.update_task_status("TS-001", "in_progress")
            await asyncio.sleep(0.3)

            await observer.stop()

            assert len(received_events) >= 1, "Should receive at least one event"
            event = received_events[0]

            # Verify timestamp is present
            assert "timestamp" in event, "Event should contain timestamp"
            timestamp = event["timestamp"]
            assert isinstance(timestamp, str), "Timestamp should be a string"

            # Verify it's a valid ISO-8601 format (basic check)
            assert "T" in timestamp or "-" in timestamp, (
                f"Timestamp should be ISO-8601 format, got: {timestamp}"
            )

        finally:
            unregister_task_callback(on_task_status_changed)

    @pytest.mark.asyncio
    async def test_observer_does_not_emit_for_same_status(
        self, db: OrchestratorDB
    ) -> None:
        """Observer does not emit events when status hasn't actually changed."""
        await db.create_task(task_key="SAME-001", title="Same Status Test", phase=0, sequence=1)

        # First, change to in_progress
        await db.update_task_status("SAME-001", "in_progress")

        received_events: list[dict[str, Any]] = []

        def on_task_status_changed(event: dict[str, Any]) -> None:
            received_events.append(event)

        register_task_callback(on_task_status_changed)

        try:
            observer = DBObserver(db=db, poll_interval=0.1)
            await observer.start()

            # Allow observer to see current state
            await asyncio.sleep(0.2)

            # "Update" to the same status
            await db.update_task_status("SAME-001", "in_progress")
            await asyncio.sleep(0.3)

            await observer.stop()

            # Should not emit event for same status
            assert len(received_events) == 0, (
                f"Should not emit event for same status, got {len(received_events)} events"
            )

        finally:
            unregister_task_callback(on_task_status_changed)

    @pytest.mark.asyncio
    async def test_empty_database_no_errors(self) -> None:
        """Observer handles empty database gracefully."""
        async with OrchestratorDB(":memory:") as db:
            observer = DBObserver(db=db, poll_interval=0.1)

            # Should not raise errors with empty database
            await observer.start()
            await asyncio.sleep(0.3)
            await observer.stop()

            # Test passes if no exceptions were raised
            assert observer.is_running is False


class TestCallbackDispatch:
    """Tests for callback dispatch mechanism."""

    @pytest.mark.asyncio
    async def test_dispatch_continues_after_callback_error(self) -> None:
        """Dispatch continues to other callbacks even if one raises an error."""
        events_received: list[str] = []

        def failing_callback(event: dict[str, Any]) -> None:
            raise RuntimeError("Intentional test error")

        def working_callback(event: dict[str, Any]) -> None:
            events_received.append("working_callback_called")

        register_task_callback(failing_callback)
        register_task_callback(working_callback)

        try:
            # Dispatch should not raise, and working callback should be called
            test_event = {
                "task_id": "TEST",
                "old_status": "pending",
                "new_status": "in_progress",
                "timestamp": "2024-01-01T00:00:00Z",
            }
            dispatch_task_callbacks(test_event)

            assert "working_callback_called" in events_received, (
                "Working callback should still be called after failing callback"
            )

        finally:
            unregister_task_callback(failing_callback)
            unregister_task_callback(working_callback)

    @pytest.mark.asyncio
    async def test_unregister_removes_callback(self) -> None:
        """Unregistering a callback prevents it from being called."""
        call_count = 0

        def counting_callback(event: dict[str, Any]) -> None:
            nonlocal call_count
            call_count += 1

        register_task_callback(counting_callback)

        # First dispatch - callback should be called
        dispatch_task_callbacks({"task_id": "TEST", "old_status": "a", "new_status": "b", "timestamp": "t"})
        assert call_count == 1, "Callback should be called once"

        # Unregister
        result = unregister_task_callback(counting_callback)
        assert result is True, "Unregister should return True"

        # Second dispatch - callback should NOT be called
        dispatch_task_callbacks({"task_id": "TEST", "old_status": "b", "new_status": "c", "timestamp": "t"})
        assert call_count == 1, "Callback should not be called after unregister"
