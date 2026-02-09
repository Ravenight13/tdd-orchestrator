"""Server-Sent Events (SSE) broadcaster for fan-out publish-subscribe pattern."""

import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class SSEEvent:
    """Represents a Server-Sent Event."""

    data: str
    event: Optional[str] = None
    id: Optional[str] = None


class SSEBroadcaster:
    """Broadcaster for Server-Sent Events with subscribe/unsubscribe and fan-out publish."""

    def __init__(self) -> None:
        """Initialize the broadcaster with an empty list of subscribers."""
        self._subscribers: list[asyncio.Queue[SSEEvent]] = []

    @property
    def subscriber_count(self) -> int:
        """Return the current number of active subscribers."""
        return len(self._subscribers)

    def subscribe(self, queue: asyncio.Queue[SSEEvent]) -> None:
        """
        Subscribe a client queue to receive events.

        Args:
            queue: The asyncio.Queue that will receive published events.
        """
        self._subscribers.append(queue)

    def unsubscribe(self, queue: asyncio.Queue[SSEEvent]) -> None:
        """
        Unsubscribe a client from receiving events.

        Args:
            queue: The queue to remove from subscribers. If not found, no error is raised.
        """
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def publish(self, event: SSEEvent) -> None:
        """
        Publish an event to all subscribers, removing slow consumers with full queues.

        Args:
            event: The event data to broadcast to all subscribers.

        Note:
            Uses put_nowait for non-blocking delivery. If a queue is full,
            that subscriber is automatically removed from the subscriber list.
        """
        to_remove: list[asyncio.Queue[SSEEvent]] = []

        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Mark slow consumer for removal
                to_remove.append(queue)

        # Remove slow consumers
        for queue in to_remove:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass
