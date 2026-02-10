"""Server-Sent Events (SSE) broadcaster with graceful shutdown."""

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class SSEEvent:
    """Represents a Server-Sent Event."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def serialize(self) -> str:
        """Serialize the event to SSE wire protocol format.

        Returns:
            str: The formatted SSE message with trailing blank line.
        """
        lines: list[str] = []

        # Order: id, event, retry, data (per SSE spec recommendations)
        if self.id is not None:
            lines.append(f"id: {self.id}")

        if self.event is not None:
            lines.append(f"event: {self.event}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # Handle multi-line data: each line gets its own "data: " prefix
        data_lines = self.data.split("\n")
        for line in data_lines:
            lines.append(f"data: {line}")

        # Join with newlines and add trailing blank line (double newline)
        return "\n".join(lines) + "\n\n"


class SSEBroadcaster:
    """Thread-safe SSE broadcaster with graceful shutdown support."""

    def __init__(self) -> None:
        """Initialize the SSE broadcaster."""
        self._subscribers: set[asyncio.Queue[SSEEvent | None]] = set()
        self._subscribers_generic: set[asyncio.Queue[Any]] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._shutdown: bool = False

    @property
    def subscriber_count(self) -> int:
        """Return the total number of active subscribers."""
        return len(self._subscribers) + len(self._subscribers_generic)

    def subscribe(self) -> asyncio.Queue[Any]:
        """Subscribe a new client and return their queue (synchronous version).

        Returns:
            asyncio.Queue for receiving events.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscribers_generic.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a client by removing their queue (synchronous version).

        Args:
            queue: The queue to remove from subscribers.
        """
        self._subscribers_generic.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers (synchronous version).

        Args:
            event: The event dictionary to broadcast.
        """
        # Broadcast to generic subscribers
        for queue in list(self._subscribers_generic):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Silently drop if queue is full
                pass

    async def subscribe_async(self) -> asyncio.Queue[SSEEvent | None]:
        """Subscribe a new client and return their queue (async version for SSEEvent).

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

    async def unsubscribe_async(self, queue: asyncio.Queue[SSEEvent | None]) -> None:
        """Unsubscribe a client by removing their queue (async version).

        Args:
            queue: The queue to remove from subscribers.
        """
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish_async(self, event: SSEEvent) -> None:
        """Publish an event to all subscribers (async version for SSEEvent).

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
