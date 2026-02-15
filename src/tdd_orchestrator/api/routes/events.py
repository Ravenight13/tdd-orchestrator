"""SSE events endpoint for streaming task status updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from tdd_orchestrator.api.sse import SSEEvent

logger = logging.getLogger(__name__)

router = APIRouter()


def get_broadcaster_dep() -> Any:
    """Get the broadcaster dependency.

    This function is designed to be patchable in tests.
    It imports and calls the actual dependency at runtime.

    Returns:
        The SSEBroadcaster instance.
    """
    from tdd_orchestrator.api.dependencies import get_broadcaster_dep as _get_broadcaster_dep
    return _get_broadcaster_dep()


async def event_stream(broadcaster: Any) -> AsyncGenerator[dict[str, str], None]:
    """Generate SSE events from the broadcaster.

    Args:
        broadcaster: The SSEBroadcaster instance.

    Yields:
        Dict with 'event' and 'data' keys for EventSourceResponse.
    """
    queue: asyncio.Queue[SSEEvent | None] | None = None
    try:
        # Subscribe to broadcaster
        queue = await broadcaster.subscribe_async()

        # Stream events until sentinel (None) is received
        while True:
            # Use wait_for with a short timeout to allow cancellation checks
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                # Keep-alive: yield nothing but allow loop to check for cancellation
                continue

            if event is None:
                # Sentinel value - stream is complete
                break

            # Yield event in format expected by EventSourceResponse
            yield {
                "event": event.event or "message",
                "data": event.data,
            }

    except asyncio.CancelledError:
        # Client disconnected - don't re-raise, let cleanup run
        logger.debug("SSE client disconnected")
    except Exception as e:
        logger.error(f"Error in SSE event stream: {e}")
        # Clean termination on error
    finally:
        # Cleanup: unsubscribe from broadcaster
        if queue is not None:
            try:
                # Use shield to protect cleanup from cancellation
                await asyncio.shield(broadcaster.unsubscribe_async(queue))
            except Exception as cleanup_error:
                logger.warning(f"Error during SSE cleanup: {cleanup_error}")


@router.get("/events")
async def get_events(request: Request) -> EventSourceResponse:
    """Stream SSE events from the broadcaster.

    Args:
        request: The FastAPI request (for accessing app state if needed).

    Returns:
        EventSourceResponse that streams SSE-formatted events.
    """
    broadcaster = get_broadcaster_dep()
    return EventSourceResponse(event_stream(broadcaster))
