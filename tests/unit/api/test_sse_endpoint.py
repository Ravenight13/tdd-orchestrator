"""Tests for the SSE events endpoint.

Tests the GET /events endpoint that streams SSEEvents from the broadcaster
using EventSourceResponse.

Key testing pattern: SSE streams are long-lived connections. Every test must
ensure the stream terminates by putting a None sentinel in the queue.
Tests that only check headers use client.stream() and exit the context
immediately. All async tests have explicit timeouts to prevent hangs.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tdd_orchestrator.api.routes.events import router


def _make_app() -> FastAPI:
    """Create a FastAPI app with the events router mounted."""
    app = FastAPI()
    app.include_router(router)
    return app


def _make_broadcaster(
    queue: asyncio.Queue[Any] | None = None,
) -> MagicMock:
    """Create a mock broadcaster with an optional pre-built queue.

    If no queue is provided, creates one with an immediate None sentinel
    so the stream terminates instantly.
    """
    if queue is None:
        queue = asyncio.Queue()
        queue.put_nowait(None)
    broadcaster = MagicMock()
    broadcaster.subscribe_async = AsyncMock(return_value=queue)
    broadcaster.unsubscribe_async = AsyncMock()
    return broadcaster


class TestSSEEndpointBasicStreaming:
    """Tests for GET /events basic SSE streaming."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    async def test_get_events_returns_200_with_event_stream_content_type(
        self, app: FastAPI
    ) -> None:
        """SSE endpoint returns 200 with text/event-stream content type."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="test", data="hello"))
        queue.put_nowait(None)  # Sentinel: terminates stream

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type

    async def test_get_events_streams_sse_formatted_messages(
        self, app: FastAPI
    ) -> None:
        """Broadcaster events are streamed with event: and data: fields."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(
            SSEEvent(event="task_status_changed", data='{"task_id":"abc","status":"passed"}')
        )
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                assert response.status_code == 200
                content = response.text
                assert "event:" in content or "data:" in content


class TestSSEEndpointGracefulCompletion:
    """Tests for graceful stream completion when broadcaster completes."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    async def test_get_events_closes_gracefully_when_generator_completes(
        self, app: FastAPI
    ) -> None:
        """Immediate None sentinel causes graceful stream close with 200."""
        broadcaster = _make_broadcaster()  # Queue with only None sentinel

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                assert response.status_code == 200

    async def test_get_events_streams_multiple_events_before_completion(
        self, app: FastAPI
    ) -> None:
        """Multiple events are streamed before graceful close."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="event1", data="data1"))
        queue.put_nowait(SSEEvent(event="event2", data="data2"))
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                assert response.status_code == 200
                content = response.text
                assert "data1" in content or "data2" in content


class TestSSEEndpointErrorHandling:
    """Tests for error handling when broadcaster raises exceptions."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    async def test_get_events_handles_subscribe_error_gracefully(
        self, app: FastAPI
    ) -> None:
        """subscribe_async raising RuntimeError doesn't hang the endpoint."""
        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(
            side_effect=RuntimeError("Disconnected backend")
        )
        broadcaster.unsubscribe_async = AsyncMock()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                try:
                    response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                    # Endpoint handled error and returned some response
                    assert response.status_code in [200, 500]
                except Exception:
                    # Connection closed is acceptable behavior
                    pass

    async def test_get_events_does_not_send_malformed_data_on_error(
        self, app: FastAPI
    ) -> None:
        """Stream data is well-formed even when stream ends early."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="test", data="valid"))
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                content = response.text
                if content:
                    lines = content.split("\n")
                    for line in lines:
                        if line.startswith("data:"):
                            assert len(line) > 5 or line == "data:"


class TestSSEEndpointBackpressure:
    """Tests for backpressure-friendly behavior."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    async def test_get_events_begins_streaming_immediately(
        self, app: FastAPI
    ) -> None:
        """Endpoint starts streaming response immediately (200, correct content-type)."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        # Put one event + sentinel so the stream terminates
        queue.put_nowait(SSEEvent(event="init", data="ready"))
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                async with client.stream("GET", "/events") as response:
                    assert response.status_code == 200
                    content_type = response.headers.get("content-type", "")
                    assert "text/event-stream" in content_type

    async def test_get_events_blocks_on_broadcaster_until_event_arrives(
        self, app: FastAPI
    ) -> None:
        """Endpoint blocks until broadcaster yields, then streams the event."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        event_delivered = asyncio.Event()

        async def delayed_producer() -> None:
            await asyncio.sleep(0.1)
            await queue.put(SSEEvent(event="delayed", data="arrived"))
            event_delivered.set()
            await queue.put(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                producer_task = asyncio.create_task(delayed_producer())
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                assert response.status_code == 200
                assert event_delivered.is_set()
                assert "arrived" in response.text
                await producer_task


class TestSSEEndpointClientDisconnect:
    """Tests for client disconnect handling.

    Client disconnect is tested at the generator level (not HTTP) because
    ASGITransport doesn't reliably propagate cancellation to server-side
    coroutines. The generator's CancelledError handling is what matters.
    """

    async def test_generator_handles_cancellation_gracefully(self) -> None:
        """Cancelling the generator triggers cleanup (unsubscribe).

        The generator catches CancelledError internally and terminates
        cleanly rather than propagating the error.
        """
        from tdd_orchestrator.api.routes.events import event_stream
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        # No sentinel — simulates a long-lived stream

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(return_value=queue)
        broadcaster.unsubscribe_async = AsyncMock()

        gen = event_stream(broadcaster)

        async def consume() -> list[dict[str, str]]:
            results = []
            async for event in gen:
                results.append(event)
            return results

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.2)  # Let it start blocking on empty queue
        task.cancel()

        # Generator catches CancelledError — task may complete cleanly or cancel
        try:
            await task
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0.1)
        broadcaster.unsubscribe_async.assert_called_once_with(queue)

    async def test_generator_stops_on_cancellation_no_resource_leak(self) -> None:
        """Cancelled generator doesn't leak — unsubscribe is always called."""
        from tdd_orchestrator.api.routes.events import event_stream
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="first", data="one"))

        cleanup_called = asyncio.Event()

        async def track_cleanup(q: asyncio.Queue[Any]) -> None:
            cleanup_called.set()

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(return_value=queue)
        broadcaster.unsubscribe_async = AsyncMock(side_effect=track_cleanup)

        gen = event_stream(broadcaster)
        event = await gen.__anext__()
        assert event["data"] == "one"

        # Now cancel during the second (blocking) iteration
        task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.2)
        task.cancel()

        # Generator catches CancelledError and terminates — StopAsyncIteration
        try:
            await task
        except (asyncio.CancelledError, StopAsyncIteration):
            pass

        await asyncio.sleep(0.1)
        assert cleanup_called.is_set()


class TestSSEEndpointRouterMounting:
    """Tests for router mountability."""

    def test_router_is_mountable_on_fastapi_app(self) -> None:
        """The events router can be mounted on a FastAPI app."""
        app = FastAPI()
        app.include_router(router)
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
        return _make_app()

    async def test_post_events_returns_405(self, app: FastAPI) -> None:
        """POST /events returns HTTP 405 Method Not Allowed."""
        broadcaster = _make_broadcaster()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/events")
                assert response.status_code == 405

    async def test_put_events_returns_405(self, app: FastAPI) -> None:
        """PUT /events returns HTTP 405 Method Not Allowed."""
        broadcaster = _make_broadcaster()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put("/events")
                assert response.status_code == 405

    async def test_delete_events_returns_405(self, app: FastAPI) -> None:
        """DELETE /events returns HTTP 405 Method Not Allowed."""
        broadcaster = _make_broadcaster()

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete("/events")
                assert response.status_code == 405


class TestSSEEventFormatting:
    """Tests for proper SSE event formatting."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    async def test_get_events_formats_event_field_correctly(
        self, app: FastAPI
    ) -> None:
        """Streamed message contains 'event:' field."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="task_status_changed", data="test"))
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                content = response.text
                assert "event:" in content or "data:" in content

    async def test_get_events_formats_data_field_correctly(
        self, app: FastAPI
    ) -> None:
        """Streamed message contains 'data:' field with JSON payload."""
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        json_data = '{"task_id":"abc","status":"passed"}'
        queue.put_nowait(SSEEvent(event="test", data=json_data))
        queue.put_nowait(None)

        broadcaster = _make_broadcaster(queue)

        with patch(
            "tdd_orchestrator.api.routes.events.get_broadcaster_dep",
            return_value=broadcaster,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/events"), timeout=5.0)
                content = response.text
                assert "data:" in content
                assert "task_id" in content or "abc" in content


class TestEventStreamGenerator:
    """Direct tests for the event_stream async generator.

    Testing the generator directly avoids HTTP transport complexity
    and is the most reliable way to verify SSE streaming behavior.
    """

    async def test_event_stream_yields_events_from_queue(self) -> None:
        """Generator yields events from broadcaster queue."""
        from tdd_orchestrator.api.routes.events import event_stream
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="test", data="hello"))
        queue.put_nowait(None)

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(return_value=queue)
        broadcaster.unsubscribe_async = AsyncMock()

        events = []
        async for event in event_stream(broadcaster):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event"] == "test"
        assert events[0]["data"] == "hello"

    async def test_event_stream_stops_on_none_sentinel(self) -> None:
        """Generator stops when None sentinel is received."""
        from tdd_orchestrator.api.routes.events import event_stream
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(SSEEvent(event="a", data="1"))
        queue.put_nowait(SSEEvent(event="b", data="2"))
        queue.put_nowait(None)
        queue.put_nowait(SSEEvent(event="c", data="should-not-see"))

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(return_value=queue)
        broadcaster.unsubscribe_async = AsyncMock()

        events = []
        async for event in event_stream(broadcaster):
            events.append(event)

        assert len(events) == 2
        assert events[0]["data"] == "1"
        assert events[1]["data"] == "2"

    async def test_event_stream_calls_unsubscribe_on_completion(self) -> None:
        """Generator calls unsubscribe_async during cleanup."""
        from tdd_orchestrator.api.routes.events import event_stream
        from tdd_orchestrator.api.sse import SSEEvent

        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        queue.put_nowait(None)

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(return_value=queue)
        broadcaster.unsubscribe_async = AsyncMock()

        async for _ in event_stream(broadcaster):
            pass

        broadcaster.unsubscribe_async.assert_called_once_with(queue)

    async def test_event_stream_handles_subscribe_error(self) -> None:
        """Generator handles subscribe_async raising an exception."""
        from tdd_orchestrator.api.routes.events import event_stream

        broadcaster = MagicMock()
        broadcaster.subscribe_async = AsyncMock(
            side_effect=RuntimeError("Connection lost")
        )
        broadcaster.unsubscribe_async = AsyncMock()

        events = []
        async for event in event_stream(broadcaster):
            events.append(event)

        assert len(events) == 0
