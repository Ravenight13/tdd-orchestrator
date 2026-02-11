"""Integration tests for SSE fan-out delivery.

Tests verify that SSE events are delivered to multiple concurrent
subscribers with identical data.
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

        task1 = asyncio.create_task(collect_events(subscriber1, received_by_client1))
        task2 = asyncio.create_task(collect_events(subscriber2, received_by_client2))
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
            asyncio.create_task(collect_events(sub, client_results[i]))
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
