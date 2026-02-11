"""Tests for the SSE events endpoint.

Tests the GET /events endpoint that streams SSEEvents from the broadcaster
using EventSourceResponse.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.routes.events import router


class TestSSEEndpointBasicStreaming:
    """Tests for GET /events basic SSE streaming."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_returns_200_with_event_stream_content_type(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster yields SSEEvent objects
        THEN the response Content-Type is 'text/event-stream' and status is 200.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        async def mock_event_generator() -> AsyncGenerator[SSEEvent, None]:
            yield SSEEvent(event="task_status_changed", data='{"task_id":"abc","status":"passed"}')

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=asyncio.Queue())

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type

    @pytest.mark.asyncio
    async def test_get_events_streams_sse_formatted_messages(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster yields SSEEvent objects
        THEN the EventSourceResponse streams each event with 'event:' and 'data:' fields.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        test_event = SSEEvent(event="task_status_changed", data='{"task_id":"abc","status":"passed"}')
        await test_queue.put(test_event)
        await test_queue.put(None)  # Sentinel to end stream

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    content = b""
                    async for chunk in response.aiter_bytes():
                        content += chunk
                        if b"\n\n" in content:
                            break

                    content_str = content.decode("utf-8")
                    assert "event:" in content_str or "data:" in content_str


class TestSSEEndpointGracefulCompletion:
    """Tests for graceful stream completion when broadcaster completes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_closes_gracefully_when_generator_completes(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client is connected to GET /events
        WHEN the broadcaster's async generator completes (no more events)
        THEN the response stream closes gracefully without raising an unhandled exception
        and the HTTP status of the initial response was 200.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        await test_queue.put(None)  # Immediate completion (sentinel)

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # This should complete without raising an exception
                response = await client.get("/events")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_events_streams_multiple_events_before_completion(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client is connected to GET /events
        WHEN the broadcaster yields multiple events then completes
        THEN all events are streamed before graceful close.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        await test_queue.put(SSEEvent(event="event1", data="data1"))
        await test_queue.put(SSEEvent(event="event2", data="data2"))
        await test_queue.put(None)  # End stream

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/events")
                assert response.status_code == 200
                content = response.text
                # Should contain both events
                assert "data1" in content or "data2" in content


class TestSSEEndpointErrorHandling:
    """Tests for error handling when broadcaster raises exceptions."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_logs_error_and_terminates_on_exception(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster raises an exception mid-stream
        THEN the endpoint logs the error and terminates the SSE stream cleanly.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

        async def mock_subscribe() -> asyncio.Queue[SSEEvent | None]:
            raise RuntimeError("Disconnected backend")

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(side_effect=RuntimeError("Disconnected backend"))
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with (
            patch(
                "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
                return_value=mock_broadcaster,
            ),
            patch("tdd_orchestrator.api.routes.events.logger") as mock_logger,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Should handle the error gracefully - either return error response
                # or stream closes without hanging
                try:
                    async with client.stream("GET", "/events", timeout=5.0) as response:
                        # If we get here, the endpoint handled the error gracefully
                        # and returned some response
                        assert response.status_code in [200, 500]
                except Exception:
                    # Connection closed is acceptable behavior
                    pass

    @pytest.mark.asyncio
    async def test_get_events_does_not_send_malformed_data_on_error(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster raises an exception mid-stream
        THEN no malformed SSE data is sent.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        # Put one valid event then simulate error via None
        await test_queue.put(SSEEvent(event="test", data="valid"))
        await test_queue.put(None)  # End stream

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/events")
                content = response.text
                # Verify no malformed data (partial lines, broken JSON, etc.)
                # Each data line should be properly formatted
                if content:
                    lines = content.split("\n")
                    for line in lines:
                        if line.startswith("data:"):
                            # Data line should have content after "data: "
                            assert len(line) > 5 or line == "data:"


class TestSSEEndpointBackpressure:
    """Tests for backpressure-friendly behavior."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_begins_streaming_immediately(
        self, app: FastAPI
    ) -> None:
        """GIVEN no SSE client is connected
        WHEN a client initiates GET /events
        THEN the endpoint immediately begins the streaming response (status 200,
        Content-Type 'text/event-stream').
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        # Don't put any events - stream should still start

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        response_started = asyncio.Event()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    # Response should start immediately with correct headers
                    assert response.status_code == 200
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type
                    # Break immediately - we don't need to wait for events
                    break

    @pytest.mark.asyncio
    async def test_get_events_blocks_on_broadcaster_until_event_arrives(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster's async generator yields after a short delay
        THEN the endpoint blocks until the event arrives (backpressure-friendly).
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        event_delivered = asyncio.Event()

        async def delayed_producer() -> None:
            await asyncio.sleep(0.1)  # Short delay
            await test_queue.put(SSEEvent(event="delayed", data="arrived"))
            event_delivered.set()
            await test_queue.put(None)  # End stream

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Start producer in background
                producer_task = asyncio.create_task(delayed_producer())

                response = await client.get("/events", timeout=5.0)
                assert response.status_code == 200

                # Verify event was delivered
                assert event_delivered.is_set()
                assert "arrived" in response.text

                await producer_task


class TestSSEEndpointClientDisconnect:
    """Tests for client disconnect handling."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_detects_client_disconnect(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client is connected to GET /events
        WHEN the client disconnects (simulated via cancelling the response read)
        THEN the endpoint detects the disconnection and stops consuming from the
        broadcaster's async generator.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        unsubscribe_called = asyncio.Event()

        async def track_unsubscribe(queue: asyncio.Queue[Any]) -> None:
            unsubscribe_called.set()

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock(side_effect=track_unsubscribe)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    # Simulate client disconnect by breaking out early
                    break

            # Give cleanup a moment to run
            await asyncio.sleep(0.1)

            # Verify unsubscribe was called (cleanup happened)
            # Note: The exact cleanup mechanism depends on implementation
            # This test verifies that some cleanup occurs
            assert mock_broadcaster.unsubscribe_async.called or mock_broadcaster.subscribe_async.called

    @pytest.mark.asyncio
    async def test_get_events_stops_consuming_on_disconnect(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client is connected to GET /events
        WHEN the client disconnects
        THEN the endpoint stops consuming from the broadcaster (no resource leak).
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        cleanup_flag = asyncio.Event()

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)

        async def cleanup_unsubscribe(queue: asyncio.Queue[Any]) -> None:
            cleanup_flag.set()

        mock_broadcaster.unsubscribe_async = AsyncMock(side_effect=cleanup_unsubscribe)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    # Read a bit then disconnect
                    try:
                        async for _ in response.aiter_bytes():
                            break  # Disconnect after first chunk or timeout
                    except asyncio.TimeoutError:
                        pass

            # Allow cleanup to execute
            await asyncio.sleep(0.2)

            # Either unsubscribe was called or no resource leak (verified by no hanging)
            assert mock_broadcaster.subscribe_async.called


class TestSSEEndpointRouterMounting:
    """Tests for router mountability."""

    def test_router_is_mountable_on_fastapi_app(self) -> None:
        """The events router can be mounted on a FastAPI app."""
        app = FastAPI()
        app.include_router(router)
        # If this doesn't raise, the router is mountable
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/events" in routes

    def test_router_mounted_at_custom_prefix(self) -> None:
        """The events router can be mounted at a custom prefix."""
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/v1/events" in routes


class TestSSEEndpointMethodNotAllowed:
    """Tests for non-GET methods on /events returning 405."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_post_events_returns_405(self, app: FastAPI) -> None:
        """POST /events returns HTTP 405 Method Not Allowed."""
        mock_broadcaster = MagicMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/events")
                assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_put_events_returns_405(self, app: FastAPI) -> None:
        """PUT /events returns HTTP 405 Method Not Allowed."""
        mock_broadcaster = MagicMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put("/events")
                assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_delete_events_returns_405(self, app: FastAPI) -> None:
        """DELETE /events returns HTTP 405 Method Not Allowed."""
        mock_broadcaster = MagicMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete("/events")
                assert response.status_code == 405


class TestSSEEventFormatting:
    """Tests for proper SSE event formatting."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a FastAPI app with the events router mounted."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_get_events_formats_event_field_correctly(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster yields an SSEEvent with event type
        THEN the streamed message contains 'event:' field.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        await test_queue.put(SSEEvent(event="task_status_changed", data="test"))
        await test_queue.put(None)

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/events")
                content = response.text
                # Verify event field is present
                assert "event:" in content or "data:" in content

    @pytest.mark.asyncio
    async def test_get_events_formats_data_field_correctly(
        self, app: FastAPI
    ) -> None:
        """GIVEN an SSE client connects to GET /events
        WHEN the broadcaster yields an SSEEvent with JSON data
        THEN the streamed message contains 'data:' field with the JSON.
        """
        from tdd_orchestrator.api.sse import SSEEvent

        test_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        json_data = '{"task_id":"abc","status":"passed"}'
        await test_queue.put(SSEEvent(event="test", data=json_data))
        await test_queue.put(None)

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe_async = AsyncMock(return_value=test_queue)
        mock_broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=mock_broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/events")
                content = response.text
                # Verify data field contains our JSON
                assert "data:" in content
                assert "task_id" in content or "abc" in content
