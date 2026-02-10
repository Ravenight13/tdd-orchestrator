"""Server-Sent Events (SSE) broadcaster with graceful shutdown."""

import asyncio
from dataclasses import dataclass
from typing import Any, Coroutine, overload


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

    @property
    def subscribers(self) -> set[asyncio.Queue[SSEEvent]]:
        """Return the set of SSEEvent subscribers.

        Returns:
            Set of SSEEvent subscriber queues.
        """
        # Cast to the more specific type expected by tests
        return self._subscribers  # type: ignore[return-value]

    def subscribe(self, queue: asyncio.Queue[SSEEvent] | None = None) -> asyncio.Queue[Any]:
        """Subscribe a new client with optional queue parameter.

        When called without arguments: creates and returns a new generic queue.
        When called with a queue: synchronously adds the queue to subscribers.

        Args:
            queue: Optional queue to subscribe. If provided, it's added to subscribers.

        Returns:
            If no queue: new generic queue.
            If queue provided: the same queue that was added.
        """
        if queue is not None:
            # Add provided queue to SSEEvent subscribers (sync path)
            self._subscribers.add(queue)  # type: ignore[arg-type]
            return queue
        else:
            # Legacy behavior: create and return new generic queue
            new_queue: asyncio.Queue[Any] = asyncio.Queue()
            self._subscribers_generic.add(new_queue)
            return new_queue

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a client by removing their queue (synchronous version).

        Args:
            queue: The queue to remove from subscribers.
        """
        self._subscribers_generic.discard(queue)

    @overload
    def publish(self, event: dict[str, Any]) -> None: ...

    @overload
    def publish(self, event: SSEEvent) -> Coroutine[Any, Any, None]: ...

    def publish(self, event: SSEEvent | dict[str, Any]) -> None | Coroutine[Any, Any, None]:
        """Publish an event to all subscribers.

        For dict events: returns None (synchronous).
        For SSEEvent: returns coroutine that must be awaited.

        Args:
            event: The event to broadcast (SSEEvent or dict).

        Returns:
            None for dict events, Coroutine for SSEEvent.
        """
        if isinstance(event, dict):
            # Synchronous path for dict events (legacy)
            for queue in list(self._subscribers_generic):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Silently drop if queue is full
                    pass
            return None
        else:
            # Return coroutine for SSEEvent
            return self._publish_sse_event(event)

    async def _publish_sse_event(self, event: SSEEvent) -> None:
        """Async implementation of SSEEvent publishing with slow consumer detection.

        Args:
            event: The SSE event to broadcast.
        """
        # SSEEvent publish with slow consumer detection
        slow_consumers: list[asyncio.Queue[SSEEvent | None]] = []

        # Attempt to deliver to all subscribers
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Mark for removal
                slow_consumers.append(queue)

        # Remove slow consumers
        for slow_queue in slow_consumers:
            self._subscribers.discard(slow_queue)

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
