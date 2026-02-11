"""Integration tests for basic SSE event delivery.

Tests verify that publishing SSE events through the broadcaster reaches
subscribed clients with correct data payloads.
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
        collect_task = asyncio.create_task(collect_events(subscriber))

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
        collect_task = asyncio.create_task(collect_events(subscriber))
        await asyncio.sleep(0.01)

        expected_data = {"task_id": "t1", "status": "passed", "extra_field": "value"}
        event = SSEEvent(event="task_status_changed", data=json.dumps(expected_data))
        await broadcaster.publish(event)

        await asyncio.wait_for(collect_task, timeout=2.0)

        assert len(received_events) == 1
        parsed_data = json.loads(received_events[0].data)
        assert parsed_data == expected_data
