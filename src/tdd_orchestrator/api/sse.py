"""Server-Sent Events (SSE) broadcaster with graceful shutdown."""

import asyncio
from dataclasses import dataclass


@dataclass
class SSEEvent:
    """Represents a Server-Sent Event."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None


class SSEBroadcaster:
    """Thread-safe SSE broadcaster with graceful shutdown support."""

    def __init__(self) -> None:
        """Initialize the SSE broadcaster."""
        self._subscribers: set[asyncio.Queue[SSEEvent | None]] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._shutdown: bool = False

    async def subscribe(self) -> asyncio.Queue[SSEEvent | None]:
        """Subscribe a new client and return their queue.

        If broadcaster is already shut down, returns a queue with sentinel value.

        Returns:
            asyncio.Queue containing SSEEvent or None (sentinel).
        """
        async with self._lock:
            queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

            if self._shutdown:
                # Already shut down, immediately send sentinel
                queue.put_nowait(None)
            else:
                # Add to active subscribers
                self._subscribers.add(queue)

            return queue

    async def unsubscribe(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        """Unsubscribe a client by removing their queue.

        Args:
            queue: The queue to remove from subscribers.
        """
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: SSEEvent) -> None:
        """Publish an event to all subscribers.

        If broadcaster is shut down, this is a no-op.

        Args:
            event: The SSE event to broadcast.
        """
        async with self._lock:
            if self._shutdown:
                # No-op after shutdown
                return

            # Create a copy of subscribers to iterate safely
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Skip if queue is full
                    pass

    async def shutdown(self) -> None:
        """Gracefully shutdown the broadcaster.

        Sends sentinel value (None) to all subscribers and clears the subscriber set.
        Multiple calls to shutdown are idempotent.
        """
        async with self._lock:
            if self._shutdown:
                # Already shut down, idempotent
                return

            self._shutdown = True

            # Send sentinel to all subscribers
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    # Queue is full - drain it and add sentinel
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    # Now put the sentinel
                    queue.put_nowait(None)

            # Clear all subscribers
            self._subscribers.clear()
