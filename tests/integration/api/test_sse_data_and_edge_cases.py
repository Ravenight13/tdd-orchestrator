"""Integration tests for SSE data structures and edge cases.

Tests verify SSE data structures and handle edge cases like
empty data, unsubscription, and event ordering.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.api.sse import (
    SSEBroadcaster,
    SSEEvent,
    SSEEventData,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
