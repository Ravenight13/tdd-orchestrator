"""Integration tests for SSE heartbeat functionality.

Tests verify that SSE connections receive keep-alive heartbeats
and remain open during idle periods.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from tdd_orchestrator.api.sse import (
    SSEBroadcaster,
    SSEEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
                wait_for_heartbeat(subscriber), timeout=15.0
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
        monitor_task = asyncio.create_task(monitor_connection(subscriber))

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
