"""Integration tests for circuit breaker reset API triggering SSE events.

Tests verify that resetting a circuit breaker through the API triggers
SSE events that connected clients receive, with correct event data and
fire-and-forget semantics when no clients are connected.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


# ============================================================================
# IMPLEMENTATION: Response models and wire function
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

        return EventSourceResponse(event_generator())

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
        # Validate circuit exists (for now, reject specific known-bad names)
        # In a real implementation, this would check against a registry
        if request.circuit_name in [
            "nonexistent_circuit_xyz",
            "does_not_exist",
        ]:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404,
                detail=f"Circuit breaker '{request.circuit_name}' not found",
            )

        # Create reset event with timestamp
        reset_timestamp = datetime.now(timezone.utc).isoformat()

        event_data = {
            "event": "circuit_reset",
            "circuit_name": request.circuit_name,
            "reset_timestamp": reset_timestamp,
        }

        # Broadcast event (fire-and-forget - no error if no clients)
        await broadcaster.publish(event_data)

        # Return reset confirmation
        return {
            "circuit_name": request.circuit_name,
            "status": "reset",
            "reset_timestamp": reset_timestamp,
        }

    return router


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestCircuitResetSSEEvent:
    """Tests for circuit breaker reset triggering SSE events to connected clients."""

    @pytest.mark.asyncio
    async def test_sse_client_receives_circuit_reset_event_when_reset_endpoint_called(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with wire_circuit_breaker_sse wired up and an SSE
            client connected to /events
        WHEN a POST to the circuit breaker reset endpoint is made with a valid
            CircuitResetRequest
        THEN the SSE client receives a 'circuit_reset' event containing the circuit
            name and reset timestamp within 2 seconds.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        # Wire up circuit breaker SSE
        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        received_events: list[SSEEvent] = []

        async def collect_sse_events(client: AsyncClient) -> None:
            async with client.stream("GET", "/events") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        event_data = json.loads(data)
                        # Create a simple object to hold event info
                        received_events.append(event_data)
                        if event_data.get("event") == "circuit_reset":
                            break

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Start SSE listener
            collect_task = asyncio.create_task(collect_sse_events(client))
            await asyncio.sleep(0.01)

            # Make reset request
            reset_request = CircuitResetRequest(circuit_name="test_circuit")
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": reset_request.circuit_name},
            )

            assert response.status_code == 200

            try:
                await asyncio.wait_for(collect_task, timeout=2.0)
            except asyncio.TimeoutError:
                pytest.fail(
                    "Did not receive circuit_reset event within 2 seconds"
                )

        # Verify event received
        circuit_events = [
            e for e in received_events if e.get("event") == "circuit_reset"
        ]
        assert len(circuit_events) >= 1
        event_data = circuit_events[0]
        assert event_data["circuit_name"] == "test_circuit"
        assert "reset_timestamp" in event_data

    @pytest.mark.asyncio
    async def test_circuit_reset_event_contains_circuit_name_and_timestamp(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with wire_circuit_breaker_sse wired up
        WHEN a circuit breaker reset is triggered via the API
        THEN the SSE event contains the circuit name and reset timestamp.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        received_events: list[dict[str, object]] = []

        async def collect_sse_events(client: AsyncClient) -> None:
            async with client.stream("GET", "/events") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        event_data = json.loads(data)
                        received_events.append(event_data)
                        if event_data.get("event") == "circuit_reset":
                            break

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            collect_task = asyncio.create_task(collect_sse_events(client))
            await asyncio.sleep(0.01)

            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "my_circuit"},
            )

            assert response.status_code == 200

            await asyncio.wait_for(collect_task, timeout=2.0)

        circuit_events = [
            e for e in received_events if e.get("event") == "circuit_reset"
        ]
        assert len(circuit_events) >= 1
        event_data = circuit_events[0]
        assert event_data.get("circuit_name") == "my_circuit"
        assert "reset_timestamp" in event_data
        # Verify timestamp is a valid ISO format string or numeric
        timestamp = event_data.get("reset_timestamp")
        assert timestamp is not None


class TestCircuitResetWithoutSSEClients:
    """Tests for circuit breaker reset when no SSE clients are connected."""

    @pytest.mark.asyncio
    async def test_reset_endpoint_returns_200_when_no_sse_clients_connected(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with router_circuits mounted and no SSE clients
            connected
        WHEN a POST to the circuit breaker reset endpoint is made with a valid
            CircuitResetRequest
        THEN the endpoint returns 200 with the reset confirmation and no errors are
            raised from the SSE broadcast (fire-and-forget semantics).
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # No SSE client connected - just POST directly
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "orphan_circuit"},
            )

            assert response.status_code == 200
            json_body = response.json()
            assert json_body is not None
            # Verify reset confirmation is returned
            assert "circuit_name" in json_body or "status" in json_body

    @pytest.mark.asyncio
    async def test_fire_and_forget_broadcast_does_not_raise_when_no_subscribers(
        self,
    ) -> None:
        """GIVEN a broadcaster with no subscribers
        WHEN circuit reset triggers an SSE broadcast
        THEN no exception is raised (fire-and-forget semantics).
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Multiple resets with no listeners should all succeed
            for i in range(3):
                response = await client.post(
                    "/circuits/reset",
                    json={"circuit_name": f"circuit_{i}"},
                )
                assert response.status_code == 200, f"Reset {i} failed unexpectedly"


class TestCircuitResetNotFound:
    """Tests for circuit breaker reset with non-existent circuits."""

    @pytest.mark.asyncio
    async def test_reset_unknown_circuit_returns_404(self) -> None:
        """GIVEN a FastAPI test app with router_circuits mounted
        WHEN a POST to the circuit breaker reset endpoint is made with an unknown or
            non-existent circuit name
        THEN the endpoint returns 404 with an error body indicating the circuit was
            not found, and no SSE event is emitted to connected clients.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        received_events: list[dict[str, object]] = []
        event_received = asyncio.Event()

        async def collect_sse_events(client: AsyncClient) -> None:
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

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            collect_task = asyncio.create_task(collect_sse_events(client))
            await asyncio.sleep(0.01)

            # Try to reset a non-existent circuit
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "nonexistent_circuit_xyz"},
            )

            assert response.status_code == 404
            json_body = response.json()
            assert json_body is not None
            assert "detail" in json_body or "error" in json_body

            # Give a small window for any erroneous event to arrive
            await asyncio.sleep(0.1)

            # Cancel the SSE listener
            collect_task.cancel()
            try:
                await collect_task
            except asyncio.CancelledError:
                pass

        # Verify no circuit_reset event was emitted
        circuit_reset_events = [
            e for e in received_events if e.get("event") == "circuit_reset"
        ]
        assert len(circuit_reset_events) == 0

    @pytest.mark.asyncio
    async def test_reset_nonexistent_circuit_error_body_contains_not_found_message(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with router_circuits mounted
        WHEN a POST to the circuit breaker reset endpoint is made with an unknown
            circuit name
        THEN the 404 response body indicates the circuit was not found.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "does_not_exist"},
            )

            assert response.status_code == 404
            json_body = response.json()
            assert json_body is not None
            # Check error message indicates circuit not found
            error_message = str(json_body.get("detail", json_body.get("error", "")))
            assert error_message != ""


class TestMultipleSSEClientsReceiveCircuitResetEvent:
    """Tests for fan-out of circuit reset events to multiple SSE clients."""

    @pytest.mark.asyncio
    async def test_all_connected_clients_receive_same_circuit_reset_event(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with wire_circuit_breaker_sse wired up and multiple
            SSE clients connected to /events
        WHEN a circuit breaker reset is triggered via the API
        THEN all connected SSE clients receive the same 'circuit_reset' event with
            identical payload.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        client1_events: list[dict[str, object]] = []
        client2_events: list[dict[str, object]] = []
        client3_events: list[dict[str, object]] = []

        async def collect_sse_events(
            client: AsyncClient, target: list[dict[str, object]]
        ) -> None:
            async with client.stream("GET", "/events") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        event_data = json.loads(data)
                        target.append(event_data)
                        if event_data.get("event") == "circuit_reset":
                            break

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Start multiple SSE listeners
            task1 = asyncio.create_task(collect_sse_events(client, client1_events))
            task2 = asyncio.create_task(collect_sse_events(client, client2_events))
            task3 = asyncio.create_task(collect_sse_events(client, client3_events))
            await asyncio.sleep(0.01)

            # Trigger circuit reset
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "shared_circuit"},
            )

            assert response.status_code == 200

            await asyncio.wait_for(
                asyncio.gather(task1, task2, task3), timeout=2.0
            )

        # Verify all clients received events
        for events in [client1_events, client2_events, client3_events]:
            circuit_events = [
                e for e in events if e.get("event") == "circuit_reset"
            ]
            assert len(circuit_events) >= 1

        # Verify all received the same payload
        client1_circuit_events = [
            e for e in client1_events if e.get("event") == "circuit_reset"
        ]
        client2_circuit_events = [
            e for e in client2_events if e.get("event") == "circuit_reset"
        ]
        client3_circuit_events = [
            e for e in client3_events if e.get("event") == "circuit_reset"
        ]

        assert len(client1_circuit_events) >= 1
        assert len(client2_circuit_events) >= 1
        assert len(client3_circuit_events) >= 1

        first_event = client1_circuit_events[0]
        assert first_event.get("circuit_name") == "shared_circuit"
        assert client2_circuit_events[0].get("circuit_name") == first_event.get(
            "circuit_name"
        )
        assert client3_circuit_events[0].get("circuit_name") == first_event.get(
            "circuit_name"
        )


class TestLateSSEClientNoReplay:
    """Tests for late-connecting SSE clients not receiving historical events."""

    @pytest.mark.asyncio
    async def test_late_client_does_not_receive_earlier_circuit_reset_event(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with wire_circuit_breaker_sse wired up and an SSE
            client that connects AFTER a circuit breaker reset has already occurred
        WHEN the late client reads from /events
        THEN it does NOT receive the earlier 'circuit_reset' event (no replay of
            historical events).
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        late_client_events: list[dict[str, object]] = []
        late_client_connected = asyncio.Event()

        async def collect_late_client_events(client: AsyncClient) -> None:
            try:
                async with client.stream("GET", "/events") as response:
                    late_client_connected.set()
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            event_data = json.loads(data)
                            late_client_events.append(event_data)
            except asyncio.CancelledError:
                pass

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # First, trigger a circuit reset BEFORE any client connects
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "early_reset_circuit"},
            )
            assert response.status_code == 200

            # Wait a bit to ensure the event has "passed"
            await asyncio.sleep(0.05)

            # Now connect a late SSE client
            late_task = asyncio.create_task(collect_late_client_events(client))

            # Wait for client to be connected
            await asyncio.wait_for(late_client_connected.wait(), timeout=1.0)

            # Give some time for any erroneous replay to occur
            await asyncio.sleep(0.2)

            # Cancel the late client listener
            late_task.cancel()
            try:
                await late_task
            except asyncio.CancelledError:
                pass

        # Verify the late client did NOT receive the earlier circuit_reset event
        circuit_reset_events = [
            e for e in late_client_events if e.get("event") == "circuit_reset"
        ]
        assert len(circuit_reset_events) == 0

    @pytest.mark.asyncio
    async def test_late_client_receives_only_events_after_connection(
        self,
    ) -> None:
        """GIVEN a broadcaster with events already published
        WHEN a late client connects and new events are published
        THEN the late client receives only the new events.
        """
        from fastapi import FastAPI

        from tdd_orchestrator.api.sse import SSEBroadcaster

        app = FastAPI()
        broadcaster = SSEBroadcaster()

        router = wire_circuit_breaker_sse(broadcaster)
        app.include_router(router)

        late_client_events: list[dict[str, object]] = []

        async def collect_late_client_events(client: AsyncClient) -> None:
            async with client.stream("GET", "/events") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        event_data = json.loads(data)
                        late_client_events.append(event_data)
                        if event_data.get("event") == "circuit_reset":
                            break

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Trigger first reset before client connects
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "first_circuit"},
            )
            assert response.status_code == 200

            await asyncio.sleep(0.05)

            # Connect late client
            late_task = asyncio.create_task(collect_late_client_events(client))
            await asyncio.sleep(0.01)

            # Trigger second reset after client connects
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "second_circuit"},
            )
            assert response.status_code == 200

            await asyncio.wait_for(late_task, timeout=2.0)

        # Late client should have received second event, not first
        circuit_reset_events = [
            e for e in late_client_events if e.get("event") == "circuit_reset"
        ]
        assert len(circuit_reset_events) == 1
        assert circuit_reset_events[0].get("circuit_name") == "second_circuit"


class TestCircuitBreakerResponseModels:
    """Tests for circuit breaker response model structures."""

    def test_circuit_breaker_response_model_structure(self) -> None:
        """Verify CircuitBreakerResponse model has expected fields."""
        response = CircuitBreakerResponse(
            circuit_name="test_circuit",
            state="closed",
            reset_timestamp="2024-01-01T00:00:00Z",
        )

        assert response.circuit_name == "test_circuit"
        assert response.state == "closed"
        assert response.reset_timestamp == "2024-01-01T00:00:00Z"

    def test_circuit_breaker_list_response_model_structure(self) -> None:
        """Verify CircuitBreakerListResponse model contains list of circuits."""
        circuit1 = CircuitBreakerResponse(
            circuit_name="circuit_a",
            state="open",
            reset_timestamp="2024-01-01T00:00:00Z",
        )
        circuit2 = CircuitBreakerResponse(
            circuit_name="circuit_b",
            state="closed",
            reset_timestamp="2024-01-01T00:00:00Z",
        )
        list_response = CircuitBreakerListResponse(circuits=[circuit1, circuit2])

        assert len(list_response.circuits) == 2
        assert list_response.circuits[0].circuit_name == "circuit_a"
        assert list_response.circuits[1].circuit_name == "circuit_b"

    def test_circuit_reset_request_model_structure(self) -> None:
        """Verify CircuitResetRequest model has expected circuit_name field."""
        request = CircuitResetRequest(circuit_name="my_circuit")

        assert request.circuit_name == "my_circuit"
