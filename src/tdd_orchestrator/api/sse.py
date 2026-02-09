"""Server-Sent Events (SSE) broadcaster for fan-out publish-subscribe pattern."""

import asyncio
from typing import Any, TypeAlias

# Type alias for SSE events (dict-based events)
SSEEvent: TypeAlias = dict[str, Any]


class SSEBroadcaster:
    """Broadcaster for Server-Sent Events with subscribe/unsubscribe and fan-out publish."""

    def __init__(self) -> None:
        """Initialize the broadcaster with an empty set of subscribers."""
        self._subscribers: set[asyncio.Queue[Any]] = set()

    @property
    def subscriber_count(self) -> int:
        """Return the current number of active subscribers."""
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[Any]:
        """
        Subscribe a new client to receive events.

        Returns:
            A new asyncio.Queue that will receive published events.
        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """
        Unsubscribe a client from receiving events.

        Args:
            queue: The queue to remove from subscribers. If not found, no error is raised.
        """
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """
        Publish an event to all subscribers using non-blocking fan-out.

        Args:
            event: The event data to broadcast to all subscribers.

        Note:
            Uses put_nowait for non-blocking delivery. If a queue is full,
            the event is silently dropped for that subscriber.
        """
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Silently drop events for full queues
                pass
