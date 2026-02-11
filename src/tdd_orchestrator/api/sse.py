"""Server-Sent Events (SSE) broadcaster with graceful shutdown."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Coroutine, overload


@dataclass
class SSEEventData:
    """Data payload for SSE events."""

    task_id: str
    status: str


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


class _SSESubscription:
    """Async iterator wrapper for SSE event queue."""

    def __init__(self, queue: asyncio.Queue[SSEEvent | None], broadcaster: "SSEBroadcaster") -> None:
        """Initialize the subscription.

        Args:
            queue: The event queue to iterate over.
            broadcaster: The broadcaster that owns this subscription.
        """
        self._queue: asyncio.Queue[SSEEvent | None] = queue
        self._broadcaster: SSEBroadcaster = broadcaster

    def __aiter__(self) -> AsyncIterator[SSEEvent]:
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> SSEEvent:
        """Get the next event from the queue.

        Returns:
            The next SSEEvent.

        Raises:
            StopAsyncIteration: When None sentinel is received.
        """
        event = await self._queue.get()
        if event is None:
            raise StopAsyncIteration
        return event

    @property
    def queue(self) -> asyncio.Queue[SSEEvent | None]:
        """Get the underlying queue."""
        return self._queue


class SSEBroadcaster:
    """Thread-safe SSE broadcaster with graceful shutdown support."""

    def __init__(self, heartbeat_interval: float | None = None) -> None:
        """Initialize the SSE broadcaster.

        Args:
            heartbeat_interval: Optional interval in seconds for sending heartbeats.
                               If provided, a background task will send heartbeat events.
        """
        self._subscribers: set[asyncio.Queue[SSEEvent | None]] = set()
        self._subscribers_generic: set[asyncio.Queue[Any]] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._shutdown: bool = False
        self._heartbeat_interval: float | None = heartbeat_interval
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Start heartbeat task if interval is provided
        if self._heartbeat_interval is not None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

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

    @overload
    def subscribe(self) -> _SSESubscription: ...

    @overload
    def subscribe(self, queue: asyncio.Queue[SSEEvent]) -> asyncio.Queue[SSEEvent]: ...

    def subscribe(
        self, queue: asyncio.Queue[SSEEvent] | None = None
    ) -> _SSESubscription | asyncio.Queue[SSEEvent]:
        """Subscribe a new client with optional queue parameter.

        When called without arguments: creates and returns a new async iterator subscription.
        When called with a queue: synchronously adds the queue to subscribers.

        Args:
            queue: Optional queue to subscribe. If provided, it's added to subscribers.

        Returns:
            If no queue: new _SSESubscription async iterator.
            If queue provided: the same queue that was added.
        """
        if queue is not None:
            # Add provided queue to SSEEvent subscribers (sync path)
            self._subscribers.add(queue)  # type: ignore[arg-type]
            return queue
        else:
            # New behavior: create queue and return async iterator wrapper
            new_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
            self._subscribers.add(new_queue)
            return _SSESubscription(new_queue, self)

    async def unsubscribe(self, subscription: _SSESubscription | asyncio.Queue[SSEEvent]) -> None:
        """Unsubscribe a client by removing their subscription or queue.

        Args:
            subscription: The subscription or queue to remove from subscribers.
        """
        if isinstance(subscription, _SSESubscription):
            # Extract the queue from the subscription
            queue = subscription.queue
            self._subscribers.discard(queue)
        else:
            # Handle raw queue (legacy path)
            self._subscribers_generic.discard(subscription)

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
        """Async implementation of SSEEvent publishing.

        Detects slow consumers whose queues are full and removes them automatically.

        Args:
            event: The SSE event to broadcast.
        """
        slow_consumers: list[asyncio.Queue[SSEEvent | None]] = []

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Mark this queue as a slow consumer to be removed
                slow_consumers.append(queue)

        # Remove all slow consumers from subscribers
        for queue in slow_consumers:
            self._subscribers.discard(queue)

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

    async def _heartbeat_loop(self) -> None:
        """Background task that sends periodic heartbeat events to all subscribers."""
        if self._heartbeat_interval is None:
            return

        while not self._shutdown:
            try:
                await asyncio.sleep(self._heartbeat_interval)

                if self._shutdown:
                    break

                # Send heartbeat event to all subscribers
                heartbeat_event = SSEEvent(event="heartbeat", data="")
                await self.publish(heartbeat_event)

            except asyncio.CancelledError:
                break
            except Exception:
                # Continue on any other error
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

            # Cancel heartbeat task if running
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

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


class CircuitBreaker:
    """Circuit breaker that publishes SSE events when it trips."""

    def __init__(self, broadcaster: SSEBroadcaster) -> None:
        """Initialize the circuit breaker with a broadcaster.

        Args:
            broadcaster: The SSE broadcaster to publish events to.
        """
        self._broadcaster: SSEBroadcaster = broadcaster

    async def trip(self, breaker_name: str, new_state: str) -> None:
        """Trip the circuit breaker and publish an SSE event.

        Args:
            breaker_name: The name of the breaker that tripped.
            new_state: The new state of the breaker.
        """
        event_data = {"breaker_name": breaker_name, "new_state": new_state}
        event = SSEEvent(event="circuit_breaker_tripped", data=json.dumps(event_data))
        await self._broadcaster.publish(event)


def wire_circuit_breaker_sse(broadcaster: SSEBroadcaster) -> CircuitBreaker:
    """Wire a circuit breaker to publish events through the broadcaster.

    Args:
        broadcaster: The SSE broadcaster to wire to.

    Returns:
        A circuit breaker instance wired to the broadcaster.
    """
    return CircuitBreaker(broadcaster)
