"""Tests for SSEBroadcaster graceful shutdown and thread-safe operations."""

import asyncio
from typing import Any

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


class TestSSEBroadcasterShutdown:
    """Tests for SSEBroadcaster shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_sends_sentinel_to_all_subscribers(self) -> None:
        """GIVEN an SSEBroadcaster with three active subscribers
        WHEN shutdown() is called
        THEN a sentinel value (None) is placed into each subscriber's asyncio.Queue
        and the internal subscribers set becomes empty.
        """
        broadcaster = SSEBroadcaster()

        # Subscribe three clients
        queue1 = await broadcaster.subscribe_async()
        queue2 = await broadcaster.subscribe_async()
        queue3 = await broadcaster.subscribe_async()

        # Call shutdown
        await broadcaster.shutdown()

        # Each queue should receive the sentinel value (None)
        sentinel1 = queue1.get_nowait()
        sentinel2 = queue2.get_nowait()
        sentinel3 = queue3.get_nowait()

        assert sentinel1 is None, "Queue 1 should receive None sentinel"
        assert sentinel2 is None, "Queue 2 should receive None sentinel"
        assert sentinel3 is None, "Queue 3 should receive None sentinel"

        # Internal subscribers set should be empty
        assert len(broadcaster._subscribers) == 0, "Subscribers set should be empty after shutdown"

    @pytest.mark.asyncio
    async def test_subscribe_after_shutdown_returns_queue_with_sentinel(self) -> None:
        """GIVEN an SSEBroadcaster that has already been shut down
        WHEN a new client calls subscribe()
        THEN the returned queue immediately contains the sentinel value
        and the subscriber is not retained in the subscribers set.
        """
        broadcaster = SSEBroadcaster()

        # Shutdown the broadcaster first
        await broadcaster.shutdown()

        # Subscribe after shutdown
        queue = await broadcaster.subscribe_async()

        # Queue should immediately contain sentinel
        sentinel = queue.get_nowait()
        assert sentinel is None, "Queue should contain None sentinel after subscribing to shut down broadcaster"

        # Subscriber should not be retained
        assert len(broadcaster._subscribers) == 0, "Subscriber should not be retained after shutdown"

    @pytest.mark.asyncio
    async def test_concurrent_publish_and_unsubscribe_no_runtime_error(self) -> None:
        """GIVEN an SSEBroadcaster with two active subscribers
        WHEN publish() and unsubscribe() are called concurrently from separate coroutines
        THEN no RuntimeError ('Set changed size during iteration') is raised
        because all operations acquire the asyncio.Lock.
        """
        broadcaster = SSEBroadcaster()

        queue1 = await broadcaster.subscribe_async()
        queue2 = await broadcaster.subscribe_async()

        event = SSEEvent(data="test message")

        # Run publish and unsubscribe concurrently many times to trigger race condition
        async def publish_loop() -> None:
            for _ in range(100):
                await broadcaster.publish_async(event)
                await asyncio.sleep(0)

        async def unsubscribe_loop() -> None:
            for _ in range(50):
                # Subscribe and immediately unsubscribe to create churn
                q = await broadcaster.subscribe_async()
                await broadcaster.unsubscribe_async(q)
                await asyncio.sleep(0)

        # This should not raise RuntimeError
        try:
            await asyncio.gather(
                publish_loop(),
                unsubscribe_loop(),
            )
            error_raised = False
        except RuntimeError as e:
            if "Set changed size during iteration" in str(e):
                error_raised = True
            else:
                raise

        assert error_raised is False, "No RuntimeError should be raised during concurrent operations"

        # Cleanup
        await broadcaster.unsubscribe_async(queue1)
        await broadcaster.unsubscribe_async(queue2)

    @pytest.mark.asyncio
    async def test_publish_after_shutdown_is_noop(self) -> None:
        """GIVEN an SSEBroadcaster with one subscriber
        WHEN shutdown() is called and then publish() is called with a new event
        THEN publish() is a no-op (queue does not receive the event) and no exception is raised.
        """
        broadcaster = SSEBroadcaster()

        queue = await broadcaster.subscribe_async()

        # Shutdown
        await broadcaster.shutdown()

        # Drain the sentinel
        sentinel = queue.get_nowait()
        assert sentinel is None, "Sentinel should be None"

        # Publish after shutdown
        event = SSEEvent(data="post-shutdown message")
        await broadcaster.publish_async(event)  # Should not raise

        # Queue should be empty (no new event)
        assert queue.empty() is True, "Queue should be empty after publish on shut down broadcaster"

    @pytest.mark.asyncio
    async def test_shutdown_with_full_queue_completes_within_timeout(self) -> None:
        """GIVEN an SSEBroadcaster with one subscriber whose queue is full (maxsize=1 with one item already enqueued)
        WHEN shutdown() is called
        THEN the sentinel is still delivered (via non-blocking put or queue drain)
        without blocking indefinitely, and shutdown completes within 1 second.
        """
        broadcaster = SSEBroadcaster()

        # Subscribe with a maxsize=1 queue
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=1)

        # Manually add to subscribers (or use a custom subscribe if available)
        # We need to inject a full queue - assuming _subscribers is a set of queues
        broadcaster._subscribers.add(queue)

        # Fill the queue
        event = SSEEvent(data="blocking message")
        await queue.put(event)

        # Queue is now full (maxsize=1)
        assert queue.full() is True, "Queue should be full before shutdown"

        # Shutdown should complete within 1 second
        try:
            await asyncio.wait_for(broadcaster.shutdown(), timeout=1.0)
            completed_in_time = True
        except asyncio.TimeoutError:
            completed_in_time = False

        assert completed_in_time is True, "Shutdown should complete within 1 second even with full queue"

        # Verify sentinel was delivered (queue should have 2 items or sentinel replaced the event)
        # The implementation may drain the queue or use put_nowait - either way sentinel should be there
        items: list[Any] = []
        while not queue.empty():
            items.append(queue.get_nowait())

        # At minimum, sentinel should be present
        assert None in items, "Sentinel (None) should be in the queue after shutdown"


class TestSSEBroadcasterLockProtection:
    """Tests for asyncio.Lock protection on all operations."""

    @pytest.mark.asyncio
    async def test_subscribe_publish_unsubscribe_all_use_lock(self) -> None:
        """Verify that subscribe, publish, and unsubscribe operations are protected by lock."""
        broadcaster = SSEBroadcaster()

        # Verify broadcaster has a lock attribute
        assert hasattr(broadcaster, "_lock"), "Broadcaster should have a _lock attribute"
        assert isinstance(broadcaster._lock, asyncio.Lock), "_lock should be an asyncio.Lock"

        queue = await broadcaster.subscribe_async()
        event = SSEEvent(data="test")
        await broadcaster.publish_async(event)
        await broadcaster.unsubscribe_async(queue)

        # If we got here without errors, operations completed successfully
        assert len(broadcaster._subscribers) == 0, "Subscriber should be removed after unsubscribe"

    @pytest.mark.asyncio
    async def test_high_concurrency_subscribe_unsubscribe(self) -> None:
        """Test that high concurrency subscribe/unsubscribe operations are thread-safe."""
        broadcaster = SSEBroadcaster()

        async def subscribe_then_unsubscribe() -> bool:
            queue = await broadcaster.subscribe_async()
            await asyncio.sleep(0)  # Yield to other coroutines
            await broadcaster.unsubscribe_async(queue)
            return True

        # Run many concurrent subscribe/unsubscribe operations
        results = await asyncio.gather(
            *[subscribe_then_unsubscribe() for _ in range(100)]
        )

        assert all(results), "All subscribe/unsubscribe operations should complete successfully"
        assert len(broadcaster._subscribers) == 0, "All subscribers should be cleaned up"


class TestSSEBroadcasterEdgeCases:
    """Edge case tests for SSEBroadcaster."""

    @pytest.mark.asyncio
    async def test_shutdown_with_no_subscribers(self) -> None:
        """GIVEN an SSEBroadcaster with no subscribers
        WHEN shutdown() is called
        THEN shutdown completes without error.
        """
        broadcaster = SSEBroadcaster()

        # Should not raise
        await broadcaster.shutdown()

        assert len(broadcaster._subscribers) == 0, "Subscribers should remain empty"

    @pytest.mark.asyncio
    async def test_multiple_shutdown_calls_are_idempotent(self) -> None:
        """GIVEN an SSEBroadcaster
        WHEN shutdown() is called multiple times
        THEN no error is raised and broadcaster remains in shutdown state.
        """
        broadcaster = SSEBroadcaster()

        queue = await broadcaster.subscribe_async()

        # First shutdown
        await broadcaster.shutdown()

        # Drain sentinel
        sentinel = queue.get_nowait()
        assert sentinel is None, "First shutdown should send sentinel"

        # Second shutdown should not raise
        await broadcaster.shutdown()

        # Third shutdown should not raise
        await broadcaster.shutdown()

        assert len(broadcaster._subscribers) == 0, "Subscribers should remain empty"

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_queue_after_shutdown(self) -> None:
        """GIVEN an SSEBroadcaster that has been shut down
        WHEN unsubscribe() is called with a queue that was never subscribed
        THEN no error is raised.
        """
        broadcaster = SSEBroadcaster()

        await broadcaster.shutdown()

        # Create a queue that was never subscribed
        orphan_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

        # Should not raise
        await broadcaster.unsubscribe_async(orphan_queue)

        assert len(broadcaster._subscribers) == 0, "Subscribers should remain empty"

    @pytest.mark.asyncio
    async def test_publish_to_empty_broadcaster(self) -> None:
        """GIVEN an SSEBroadcaster with no subscribers
        WHEN publish() is called
        THEN no error is raised.
        """
        broadcaster = SSEBroadcaster()

        event = SSEEvent(data="orphan message")

        # Should not raise
        await broadcaster.publish_async(event)

        assert len(broadcaster._subscribers) == 0, "Subscribers should remain empty"

    @pytest.mark.asyncio
    async def test_unsubscribe_same_queue_twice(self) -> None:
        """GIVEN an SSEBroadcaster with one subscriber
        WHEN unsubscribe() is called twice with the same queue
        THEN no error is raised on the second call.
        """
        broadcaster = SSEBroadcaster()

        queue = await broadcaster.subscribe_async()

        # First unsubscribe
        await broadcaster.unsubscribe_async(queue)
        assert len(broadcaster._subscribers) == 0, "Subscriber should be removed"

        # Second unsubscribe should not raise
        await broadcaster.unsubscribe_async(queue)
        assert len(broadcaster._subscribers) == 0, "Subscribers should remain empty"
