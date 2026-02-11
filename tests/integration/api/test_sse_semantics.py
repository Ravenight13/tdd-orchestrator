"""Integration tests for SSE fire-and-forget semantics.

Tests verify that SSE events follow fire-and-forget semantics with
no replay or backlog for late subscribers.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.api.sse import (
    SSEBroadcaster,
    SSEEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
        collect_task = asyncio.create_task(collect_events(subscriber))
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
