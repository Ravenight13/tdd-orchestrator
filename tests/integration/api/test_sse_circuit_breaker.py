"""Integration tests for circuit breaker SSE event propagation.

Tests verify that circuit breaker events propagate through SSE to
subscribed clients with correct event types and data.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.api.sse import (
    SSEBroadcaster,
    SSEEvent,
    wire_circuit_breaker_sse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
        collect_task = asyncio.create_task(collect_events(subscriber))
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
        collect_task = asyncio.create_task(collect_events(subscriber))
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
