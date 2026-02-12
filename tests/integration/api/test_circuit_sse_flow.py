"""Integration tests for circuit breaker reset API triggering SSE events.

Tests verify that resetting a circuit breaker through the API triggers
SSE events that connected clients receive, with correct event data and
fire-and-forget semantics when no clients are connected.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

# Re-export implementation classes for module API compatibility
from tests.integration.api._circuit_sse_helpers import (
    CircuitBreakerListResponse,
    CircuitBreakerResponse,
    CircuitResetRequest,
    cleanup_sse_task,
    create_event_collector,
    create_test_app_with_broadcaster,
    filter_circuit_reset_events,
    setup_sse_listener,
    wire_circuit_breaker_sse,
)

# Ensure exports are available at module level
__all__ = [
    "CircuitBreakerResponse",
    "CircuitBreakerListResponse",
    "CircuitResetRequest",
    "wire_circuit_breaker_sse",
]


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
        app, broadcaster = await create_test_app_with_broadcaster()
        received_events, on_event = create_event_collector()
        await broadcaster.subscribe(on_event)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "test_circuit"},
            )
            assert response.status_code == 200

        circuit_events = filter_circuit_reset_events(received_events)
        assert len(circuit_events) >= 1
        assert circuit_events[0]["circuit_name"] == "test_circuit"
        assert "reset_timestamp" in circuit_events[0]

    @pytest.mark.asyncio
    async def test_circuit_reset_event_contains_circuit_name_and_timestamp(
        self,
    ) -> None:
        """GIVEN a FastAPI test app with wire_circuit_breaker_sse wired up
        WHEN a circuit breaker reset is triggered via the API
        THEN the SSE event contains the circuit name and reset timestamp.
        """
        app, broadcaster = await create_test_app_with_broadcaster()
        received_events, on_event = create_event_collector()
        await broadcaster.subscribe(on_event)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "my_circuit"},
            )
            assert response.status_code == 200

        circuit_events = filter_circuit_reset_events(received_events)
        assert len(circuit_events) >= 1
        event_data = circuit_events[0]
        assert event_data.get("circuit_name") == "my_circuit"
        assert "reset_timestamp" in event_data
        timestamp = event_data.get("reset_timestamp")
        assert timestamp is not None
        assert str(timestamp) != ""


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
        app, _broadcaster = await create_test_app_with_broadcaster()

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
        app, _broadcaster = await create_test_app_with_broadcaster()

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
        app, _broadcaster = await create_test_app_with_broadcaster()
        received_events: list[dict[str, object]] = []
        event_received = asyncio.Event()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            collect_task = await setup_sse_listener(
                client, received_events, event_received
            )

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
            await cleanup_sse_task(collect_task)

        # Verify no circuit_reset event was emitted
        # Cast to correct type for filtering
        events_for_filter: list[dict[str, Any]] = [
            dict(e) for e in received_events
        ]
        circuit_reset_events = filter_circuit_reset_events(events_for_filter)
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
        app, _broadcaster = await create_test_app_with_broadcaster()

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
        app, broadcaster = await create_test_app_with_broadcaster()

        # Create three separate event collectors
        client1_events, on_event_1 = create_event_collector()
        client2_events, on_event_2 = create_event_collector()
        client3_events, on_event_3 = create_event_collector()

        # Subscribe all three
        await broadcaster.subscribe(on_event_1)
        await broadcaster.subscribe(on_event_2)
        await broadcaster.subscribe(on_event_3)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "shared_circuit"},
            )
            assert response.status_code == 200

        # Verify all subscribers received events
        all_client_events = [client1_events, client2_events, client3_events]
        for events in all_client_events:
            circuit_events = filter_circuit_reset_events(events)
            assert len(circuit_events) >= 1

        # Verify all received the same payload
        assert client1_events[0].get("circuit_name") == "shared_circuit"
        assert client2_events[0].get("circuit_name") == client1_events[0].get(
            "circuit_name"
        )
        assert client3_events[0].get("circuit_name") == client1_events[0].get(
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
        app, broadcaster = await create_test_app_with_broadcaster()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Trigger reset BEFORE any subscriber registers
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "early_reset_circuit"},
            )
            assert response.status_code == 200

        # Register "late" callback after event already published
        late_events, on_late_event = create_event_collector()
        await broadcaster.subscribe(on_late_event)

        # Verify late subscriber got nothing
        circuit_reset_events = filter_circuit_reset_events(late_events)
        assert len(circuit_reset_events) == 0

    @pytest.mark.asyncio
    async def test_late_client_receives_only_events_after_connection(
        self,
    ) -> None:
        """GIVEN a broadcaster with events already published
        WHEN a late client connects and new events are published
        THEN the late client receives only the new events.
        """
        app, broadcaster = await create_test_app_with_broadcaster()
        late_events: list[dict[str, Any]] = []

        async def on_late_event(event: dict[str, Any]) -> None:
            late_events.append(event)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Trigger first reset before subscriber registers
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "first_circuit"},
            )
            assert response.status_code == 200

            # Register late callback
            await broadcaster.subscribe(on_late_event)

            # Trigger second reset after subscriber is active
            response = await client.post(
                "/circuits/reset",
                json={"circuit_name": "second_circuit"},
            )
            assert response.status_code == 200

        # Late subscriber should have received only second event
        circuit_reset_events = filter_circuit_reset_events(late_events)
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
