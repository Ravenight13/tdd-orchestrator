"""Helper module for circuit breaker SSE integration tests.

Contains shared models, fixtures, and the wire function implementation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tdd_orchestrator.api.sse import SSEBroadcaster


# ============================================================================
# Response models
# ============================================================================


class CircuitBreakerResponse(BaseModel):
    """Response model for circuit breaker operations."""

    circuit_name: str
    state: str
    reset_timestamp: str


class CircuitBreakerListResponse(BaseModel):
    """Response model for listing circuit breakers."""

    circuits: list[CircuitBreakerResponse]


class CircuitResetRequest(BaseModel):
    """Request model for resetting a circuit breaker."""

    circuit_name: str


# ============================================================================
# Constants for validation
# ============================================================================

# Circuit names that are known to not exist (for testing 404 behavior)
NONEXISTENT_CIRCUITS = frozenset(["nonexistent_circuit_xyz", "does_not_exist"])


# ============================================================================
# Wire function and helpers
# ============================================================================


def _create_event_generator(
    broadcaster: SSEBroadcaster,
) -> AsyncIterator[dict[str, Any]]:
    """Create an async generator for SSE events.

    Args:
        broadcaster: SSE broadcaster instance

    Returns:
        Async generator yielding SSE-formatted event dicts
    """

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        """Generate SSE events from broadcaster."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def subscriber(event: dict[str, Any]) -> None:
            """Queue events for this client."""
            await queue.put(event)

        await broadcaster.subscribe(subscriber)

        try:
            while True:
                event = await queue.get()
                # Format event for SSE: put the full event dict in the data field
                yield {"data": json.dumps(event)}
        finally:
            await broadcaster.unsubscribe(subscriber)

    return event_generator()


def _validate_circuit_exists(circuit_name: str) -> None:
    """Validate that a circuit exists.

    Args:
        circuit_name: Name of the circuit to validate

    Raises:
        HTTPException: 404 if circuit not found
    """
    if circuit_name in NONEXISTENT_CIRCUITS:
        raise HTTPException(
            status_code=404,
            detail=f"Circuit breaker '{circuit_name}' not found",
        )


def _create_reset_event(circuit_name: str) -> tuple[dict[str, str], str]:
    """Create a circuit reset event with timestamp.

    Args:
        circuit_name: Name of the circuit being reset

    Returns:
        Tuple of (event_data dict, reset_timestamp string)
    """
    reset_timestamp = datetime.now(timezone.utc).isoformat()

    event_data = {
        "event": "circuit_reset",
        "circuit_name": circuit_name,
        "reset_timestamp": reset_timestamp,
    }

    return event_data, reset_timestamp


def wire_circuit_breaker_sse(broadcaster: SSEBroadcaster) -> APIRouter:
    """Wire up circuit breaker SSE endpoints.

    Args:
        broadcaster: SSE broadcaster instance for publishing events

    Returns:
        FastAPI router with circuit breaker endpoints
    """
    router = APIRouter()

    @router.get("/events")
    async def sse_endpoint() -> EventSourceResponse:
        """SSE endpoint for streaming circuit breaker events."""
        return EventSourceResponse(_create_event_generator(broadcaster))

    @router.post("/circuits/reset")
    async def reset_circuit(request: CircuitResetRequest) -> dict[str, str]:
        """Reset a circuit breaker and broadcast SSE event.

        Args:
            request: Circuit reset request with circuit name

        Returns:
            Reset confirmation response

        Raises:
            HTTPException: 404 if circuit not found
        """
        _validate_circuit_exists(request.circuit_name)

        event_data, reset_timestamp = _create_reset_event(request.circuit_name)

        # Broadcast event (fire-and-forget - no error if no clients)
        await broadcaster.publish(event_data)

        return {
            "circuit_name": request.circuit_name,
            "status": "reset",
            "reset_timestamp": reset_timestamp,
        }

    return router


# ============================================================================
# Test helper functions
# ============================================================================


async def create_test_app_with_broadcaster() -> tuple[Any, SSEBroadcaster]:
    """Create a FastAPI test app with circuit breaker SSE wired up.

    Returns:
        Tuple of (FastAPI app, SSEBroadcaster instance)
    """
    from fastapi import FastAPI

    from tdd_orchestrator.api.sse import SSEBroadcaster

    app = FastAPI()
    broadcaster = SSEBroadcaster()

    router = wire_circuit_breaker_sse(broadcaster)
    app.include_router(router)

    return app, broadcaster


def create_event_collector() -> tuple[list[dict[str, Any]], Any]:
    """Create an event collector callback and list.

    Returns:
        Tuple of (events list, async callback function)
    """
    received_events: list[dict[str, Any]] = []

    async def on_event(event: dict[str, Any]) -> None:
        received_events.append(event)

    return received_events, on_event


def filter_circuit_reset_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter a list of events to only circuit_reset events.

    Args:
        events: List of event dicts

    Returns:
        Filtered list containing only circuit_reset events
    """
    return [e for e in events if e.get("event") == "circuit_reset"]


async def setup_sse_listener(
    client: Any,
    received_events: list[dict[str, object]],
    event_received: asyncio.Event,
) -> asyncio.Task[None]:
    """Set up an SSE listener task that collects events.

    Args:
        client: AsyncClient instance
        received_events: List to append received events to
        event_received: Event to set when an event is received

    Returns:
        The collector task (already started)
    """

    async def collect_sse_events() -> None:
        try:
            async with client.stream("GET", "/events") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        event_data = json.loads(data)
                        received_events.append(event_data)
                        event_received.set()
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(collect_sse_events())
    await asyncio.sleep(0.01)  # Give task time to connect
    return task


async def cleanup_sse_task(task: asyncio.Task[None]) -> None:
    """Cancel and clean up an SSE listener task.

    Args:
        task: The task to cancel and await
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
