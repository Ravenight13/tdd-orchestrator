"""Integration tests for SSE event broadcasting.

Tests verify that publishing SSE events through the broadcaster reaches
subscribed clients via the /events SSE endpoint.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

# These imports will fail until implementation exists - this is expected for TDD
from tdd_orchestrator.api.sse import (
    SSEBroadcaster,
    SSEEvent,
    SSEEventData,
    wire_circuit_breaker_sse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class TestSSEBroadcasterBasicDelivery:
    """Tests for basic SSE event delivery to subscribed clients."""

    @pytest.mark.asyncio
    async def test_subscribed_client_receives_published_event_within_timeout(self) -> None:
        """GIVEN a broadcaster with a subscribed client
        WHEN an SSEEvent is published
        THEN the client receives the event within 2 seconds.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                break  # Only need one event

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))  # type: ignore[arg-type]

        # Allow subscription to be established
        await asyncio.sleep(0.01)

        # Publish the event
        event_data = SSEEventData(task_id="t1", status="passed")
        event = SSEEvent(event="task_status_changed", data=json.dumps(event_data.__dict__))
        await broadcaster.publish(event)

        # Wait for event with timeout
        try:
            await asyncio.wait_for(collect_task, timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail("Client did not receive event within 2 seconds")

        assert len(received_events) == 1
        assert received_events[0].event == "task_status_changed"

        parsed_data = json.loads(received_events[0].data)
        assert parsed_data["task_id"] == "t1"
        assert parsed_data["status"] == "passed"

    @pytest.mark.asyncio
    async def test_event_data_payload_matches_published_content(self) -> None:
        """GIVEN a broadcaster with a subscribed client
        WHEN an SSEEvent with JSON data is published
        THEN the received data payload matches exactly.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)

        expected_data = {"task_id": "t1", "status": "passed", "extra_field": "value"}
        event = SSEEvent(event="task_status_changed", data=json.dumps(expected_data))
        await broadcaster.publish(event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        assert len(received_events) == 1
        parsed_data = json.loads(received_events[0].data)
        assert parsed_data == expected_data


class TestCircuitBreakerSSEIntegration:
    """Tests for circuit breaker events propagating through SSE."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_trip_sends_event_to_subscriber(self) -> None:
        """GIVEN a broadcaster wired to circuit breaker events
        WHEN a circuit breaker trips
        THEN the subscriber receives a circuit_breaker_tripped event.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                if event.event == "circuit_breaker_tripped":
                    break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)

        # Wire up circuit breaker to broadcaster
        circuit_breaker = wire_circuit_breaker_sse(broadcaster)

        # Trigger the circuit breaker trip
        await circuit_breaker.trip(breaker_name="task_failure", new_state="open")

        try:
            await asyncio.wait_for(collect_task, timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail("Did not receive circuit_breaker_tripped event within 2 seconds")

        circuit_events = [e for e in received_events if e.event == "circuit_breaker_tripped"]
        assert len(circuit_events) >= 1

        event_data = json.loads(circuit_events[0].data)
        assert event_data["breaker_name"] == "task_failure"
        assert event_data["new_state"] == "open"

    @pytest.mark.asyncio
    async def test_circuit_breaker_event_contains_required_fields(self) -> None:
        """GIVEN a wired circuit breaker
        WHEN it trips
        THEN the event contains breaker name and new state.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                if event.event == "circuit_breaker_tripped":
                    break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)

        circuit_breaker = wire_circuit_breaker_sse(broadcaster)
        await circuit_breaker.trip(breaker_name="test_breaker", new_state="half_open")

        await asyncio.wait_for(collect_task, timeout=2.0)

        circuit_events = [e for e in received_events if e.event == "circuit_breaker_tripped"]
        assert len(circuit_events) >= 1

        event_data = json.loads(circuit_events[0].data)
        assert "breaker_name" in event_data
        assert "new_state" in event_data
        assert event_data["breaker_name"] == "test_breaker"
        assert event_data["new_state"] == "half_open"


class TestSSEFanOutDelivery:
    """Tests for fan-out delivery to multiple concurrent subscribers."""

    @pytest.mark.asyncio
    async def test_two_concurrent_clients_receive_same_event(self) -> None:
        """GIVEN two clients subscribed to the broadcaster
        WHEN a single SSEEvent is published
        THEN both clients receive the same event.
        """
        broadcaster = SSEBroadcaster()
        received_by_client1: list[SSEEvent] = []
        received_by_client2: list[SSEEvent] = []

        async def collect_events(
            subscriber: AsyncIterator[SSEEvent], target: list[SSEEvent]
        ) -> None:
            async for event in subscriber:
                target.append(event)
                break

        subscriber1 = broadcaster.subscribe()
        subscriber2 = broadcaster.subscribe()

        task1 = asyncio.create_task(collect_events(subscriber1, received_by_client1))  # type: ignore[arg-type]
        task2 = asyncio.create_task(collect_events(subscriber2, received_by_client2))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)

        event = SSEEvent(event="test_event", data='{"message": "hello"}')
        await broadcaster.publish(event)

        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=2.0)

        assert len(received_by_client1) == 1
        assert len(received_by_client2) == 1

        assert received_by_client1[0].event == received_by_client2[0].event
        assert received_by_client1[0].data == received_by_client2[0].data
        assert received_by_client1[0].event == "test_event"
        assert received_by_client1[0].data == '{"message": "hello"}'

    @pytest.mark.asyncio
    async def test_fan_out_delivers_identical_data_to_all_clients(self) -> None:
        """GIVEN multiple concurrent subscribers
        WHEN an event is published
        THEN all clients receive identical event type and data.
        """
        broadcaster = SSEBroadcaster()
        client_results: list[list[SSEEvent]] = [[], [], []]

        async def collect_events(
            subscriber: AsyncIterator[SSEEvent], target: list[SSEEvent]
        ) -> None:
            async for event in subscriber:
                target.append(event)
                break

        subscribers = [broadcaster.subscribe() for _ in range(3)]
        tasks = [
            asyncio.create_task(collect_events(sub, client_results[i]))  # type: ignore[arg-type]
            for i, sub in enumerate(subscribers)
        ]
        await asyncio.sleep(0.01)

        test_data = {"key": "value", "number": 42}
        event = SSEEvent(event="fanout_test", data=json.dumps(test_data))
        await broadcaster.publish(event)

        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2.0)

        # All clients should have received exactly one event
        for i, result in enumerate(client_results):
            assert len(result) == 1, f"Client {i} did not receive exactly one event"

        # All events should be identical
        first_event = client_results[0][0]
        for i, result in enumerate(client_results[1:], start=1):
            assert result[0].event == first_event.event, f"Client {i} event type mismatch"
            assert result[0].data == first_event.data, f"Client {i} data mismatch"


class TestSSEHeartbeat:
    """Tests for SSE keep-alive heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_client_receives_heartbeat_within_15_seconds(self) -> None:
        """GIVEN a client connected to /events
        WHEN no events are published for 15 seconds
        THEN the client receives at least one keep-alive heartbeat.
        """
        broadcaster = SSEBroadcaster(heartbeat_interval=1.0)  # Use shorter interval for testing
        heartbeat_received = False
        connection_error = None

        async def wait_for_heartbeat(subscriber: AsyncIterator[SSEEvent]) -> bool:
            nonlocal connection_error
            try:
                async for event in subscriber:
                    # Heartbeats are typically sent as comment lines or special events
                    if event.event == "heartbeat" or event.event == ":":
                        return True
            except Exception as e:
                connection_error = e
            return False

        subscriber = broadcaster.subscribe()

        try:
            heartbeat_received = await asyncio.wait_for(
                wait_for_heartbeat(subscriber), timeout=15.0  # type: ignore[arg-type]
            )
        except asyncio.TimeoutError:
            pass  # Will check heartbeat_received below

        assert connection_error is None, f"Connection error occurred: {connection_error}"
        assert heartbeat_received is True, "No heartbeat received within 15 seconds"

    @pytest.mark.asyncio
    async def test_connection_remains_open_during_idle_period(self) -> None:
        """GIVEN a client connected to /events
        WHEN no events are published
        THEN the connection remains open without error.
        """
        broadcaster = SSEBroadcaster(heartbeat_interval=0.5)
        events_received: list[SSEEvent] = []
        connection_closed = False

        async def monitor_connection(subscriber: AsyncIterator[SSEEvent]) -> None:
            nonlocal connection_closed
            try:
                async for event in subscriber:
                    events_received.append(event)
                    if len(events_received) >= 2:
                        break
            except StopAsyncIteration:
                connection_closed = True

        subscriber = broadcaster.subscribe()
        monitor_task = asyncio.create_task(monitor_connection(subscriber))  # type: ignore[arg-type]

        # Wait for multiple heartbeats
        try:
            await asyncio.wait_for(monitor_task, timeout=3.0)
        except asyncio.TimeoutError:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        assert connection_closed is False, "Connection was unexpectedly closed"
        # Should have received heartbeats if implementation sends them
        assert len(events_received) >= 1, "Expected at least one heartbeat event"


class TestSSEFireAndForgetSemantics:
    """Tests for fire-and-forget event semantics (no replay/backlog)."""

    @pytest.mark.asyncio
    async def test_new_subscriber_does_not_receive_past_events(self) -> None:
        """GIVEN no clients are subscribed
        WHEN an event is published and then a client subscribes
        THEN the new client does NOT receive the previously published event.
        """
        broadcaster = SSEBroadcaster()

        # Publish event with no subscribers
        past_event = SSEEvent(event="past_event", data='{"id": "old"}')
        await broadcaster.publish(past_event)

        # Now subscribe
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)

        # Publish a new event
        new_event = SSEEvent(event="new_event", data='{"id": "new"}')
        await broadcaster.publish(new_event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        # Should only receive the new event, not the past one
        assert len(received_events) == 1
        assert received_events[0].event == "new_event"
        assert "old" not in received_events[0].data

    @pytest.mark.asyncio
    async def test_no_event_backlog_for_late_subscribers(self) -> None:
        """GIVEN multiple events were published before subscription
        WHEN a new client subscribes
        THEN none of the past events are replayed.
        """
        broadcaster = SSEBroadcaster()

        # Publish multiple events with no subscribers
        for i in range(5):
            event = SSEEvent(event=f"old_event_{i}", data=json.dumps({"index": i}))
            await broadcaster.publish(event)

        # Subscribe after all old events
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))
        await asyncio.sleep(0.01)

        # Publish a new event that should be received
        new_event = SSEEvent(event="current_event", data='{"fresh": true}')
        await broadcaster.publish(new_event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        # Should only have the new event
        assert len(received_events) == 1
        assert received_events[0].event == "current_event"

        # Verify none of the old events were received
        old_event_names = {f"old_event_{i}" for i in range(5)}
        received_event_names = {e.event for e in received_events}
        assert old_event_names.isdisjoint(received_event_names), "Received old events unexpectedly"


class TestSSEEventDataStructure:
    """Tests for SSEEvent and SSEEventData data structures."""

    def test_sse_event_has_event_and_data_fields(self) -> None:
        """SSEEvent should have event and data fields."""
        event = SSEEvent(event="test", data='{"key": "value"}')

        assert hasattr(event, "event")
        assert hasattr(event, "data")
        assert event.event == "test"
        assert event.data == '{"key": "value"}'

    def test_sse_event_data_has_task_fields(self) -> None:
        """SSEEventData should have task_id and status fields."""
        event_data = SSEEventData(task_id="t1", status="passed")

        assert hasattr(event_data, "task_id")
        assert hasattr(event_data, "status")
        assert event_data.task_id == "t1"
        assert event_data.status == "passed"

    def test_sse_event_data_serializes_to_json(self) -> None:
        """SSEEventData should be serializable to JSON."""
        event_data = SSEEventData(task_id="t1", status="failed")

        # Should be able to convert to dict and serialize
        data_dict = event_data.__dict__
        json_str = json.dumps(data_dict)

        parsed = json.loads(json_str)
        assert parsed["task_id"] == "t1"
        assert parsed["status"] == "failed"


class TestSSEBroadcasterEdgeCases:
    """Edge case tests for SSE broadcaster."""

    @pytest.mark.asyncio
    async def test_publish_with_empty_data(self) -> None:
        """GIVEN a broadcaster with a subscriber
        WHEN an event with empty data is published
        THEN the client receives the event with empty data.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent]) -> None:
            async for event in subscriber:
                received_events.append(event)
                break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber))
        await asyncio.sleep(0.01)

        event = SSEEvent(event="empty_data", data="")
        await broadcaster.publish(event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        assert len(received_events) == 1
        assert received_events[0].event == "empty_data"
        assert received_events[0].data == ""

    @pytest.mark.asyncio
    async def test_subscriber_unsubscribes_cleanly(self) -> None:
        """GIVEN a subscribed client
        WHEN the client unsubscribes
        THEN subsequent publishes don't error.
        """
        broadcaster = SSEBroadcaster()

        subscriber = broadcaster.subscribe()
        # Simulate unsubscribe by not iterating
        await broadcaster.unsubscribe(subscriber)

        # Publishing after unsubscribe should not raise
        event = SSEEvent(event="after_unsub", data="{}")
        # This should complete without error
        await broadcaster.publish(event)

        # If we got here without exception, test passes
        assert True

    @pytest.mark.asyncio
    async def test_multiple_events_delivered_in_order(self) -> None:
        """GIVEN a subscribed client
        WHEN multiple events are published
        THEN events are received in order.
        """
        broadcaster = SSEBroadcaster()
        received_events: list[SSEEvent] = []

        async def collect_events(subscriber: AsyncIterator[SSEEvent], count: int) -> None:
            collected = 0
            async for event in subscriber:
                received_events.append(event)
                collected += 1
                if collected >= count:
                    break

        subscriber = broadcaster.subscribe()
        collect_task = asyncio.create_task(collect_events(subscriber, 3))
        await asyncio.sleep(0.01)

        # Publish events in order
        for i in range(3):
            event = SSEEvent(event=f"event_{i}", data=json.dumps({"order": i}))
            await broadcaster.publish(event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        assert len(received_events) == 3
        for i, event in enumerate(received_events):
            assert event.event == f"event_{i}"
            parsed = json.loads(event.data)
            assert parsed["order"] == i
