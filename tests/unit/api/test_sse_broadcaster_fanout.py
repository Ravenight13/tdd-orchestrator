"""Tests for SSEBroadcaster subscribe/unsubscribe and fan-out publish functionality."""

import asyncio
from typing import Any

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


class TestSSEBroadcasterSubscribe:
    """Tests for SSEBroadcaster.subscribe() functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_asyncio_queue(self) -> None:
        """GIVEN a newly created SSEBroadcaster WHEN subscribe() is called THEN it returns an asyncio.Queue instance."""
        broadcaster = SSEBroadcaster()

        queue = broadcaster.subscribe()

        assert isinstance(queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_subscribe_increases_subscriber_count(self) -> None:
        """GIVEN a newly created SSEBroadcaster WHEN subscribe() is called THEN the broadcaster's internal subscriber count increases by one."""
        broadcaster = SSEBroadcaster()
        initial_count = broadcaster.subscriber_count

        broadcaster.subscribe()

        assert broadcaster.subscriber_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_multiple_subscribes_increase_count_correctly(self) -> None:
        """GIVEN a SSEBroadcaster WHEN subscribe() is called multiple times THEN subscriber count increases accordingly."""
        broadcaster = SSEBroadcaster()

        broadcaster.subscribe()
        broadcaster.subscribe()
        broadcaster.subscribe()

        assert broadcaster.subscriber_count == 3


class TestSSEBroadcasterPublish:
    """Tests for SSEBroadcaster.publish() fan-out functionality."""

    @pytest.mark.asyncio
    async def test_publish_sends_event_to_all_subscribers(self) -> None:
        """GIVEN an SSEBroadcaster with 3 subscribers WHEN publish(event) is called with a dict payload THEN all 3 subscriber queues receive the same event object."""
        broadcaster = SSEBroadcaster()
        queue1 = broadcaster.subscribe()
        queue2 = broadcaster.subscribe()
        queue3 = broadcaster.subscribe()
        event: dict[str, Any] = {"type": "test", "data": "hello"}

        broadcaster.publish(event)

        received1 = queue1.get_nowait()
        received2 = queue2.get_nowait()
        received3 = queue3.get_nowait()

        assert received1 == event
        assert received2 == event
        assert received3 == event

    @pytest.mark.asyncio
    async def test_publish_uses_put_nowait_nonblocking(self) -> None:
        """GIVEN an SSEBroadcaster with subscribers WHEN publish(event) is called THEN events are delivered via non-blocking put_nowait."""
        broadcaster = SSEBroadcaster()
        queue = broadcaster.subscribe()
        event: dict[str, Any] = {"type": "test"}

        # publish should complete immediately without awaiting
        broadcaster.publish(event)

        # Queue should have the event immediately available
        assert queue.qsize() == 1
        assert queue.get_nowait() == event

    @pytest.mark.asyncio
    async def test_publish_with_zero_subscribers_no_error(self) -> None:
        """GIVEN an SSEBroadcaster with 0 subscribers WHEN publish(event) is called THEN no error is raised and the method completes successfully."""
        broadcaster = SSEBroadcaster()
        event: dict[str, Any] = {"type": "test", "data": "ignored"}

        # Should not raise any exception
        broadcaster.publish(event)

        assert broadcaster.subscriber_count == 0


class TestSSEBroadcasterUnsubscribe:
    """Tests for SSEBroadcaster.unsubscribe() functionality."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscriber(self) -> None:
        """GIVEN an SSEBroadcaster with subscribers WHEN unsubscribe(queue) is called THEN subscriber count decreases."""
        broadcaster = SSEBroadcaster()
        queue1 = broadcaster.subscribe()
        broadcaster.subscribe()
        initial_count = broadcaster.subscriber_count

        broadcaster.unsubscribe(queue1)

        assert broadcaster.subscriber_count == initial_count - 1

    @pytest.mark.asyncio
    async def test_unsubscribed_queue_does_not_receive_events(self) -> None:
        """GIVEN an SSEBroadcaster with 2 subscribers WHEN one subscriber is unsubscribed and publish(event) is called THEN only the remaining subscriber receives the event."""
        broadcaster = SSEBroadcaster()
        queue1 = broadcaster.subscribe()
        queue2 = broadcaster.subscribe()
        event: dict[str, Any] = {"type": "test", "data": "after_unsub"}

        broadcaster.unsubscribe(queue1)
        broadcaster.publish(event)

        # Unsubscribed queue should be empty
        assert queue1.empty()
        # Remaining subscriber should receive the event
        assert queue2.get_nowait() == event

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_queue_no_error(self) -> None:
        """GIVEN an SSEBroadcaster WHEN unsubscribe() is called with a queue that was never subscribed THEN no error is raised."""
        broadcaster = SSEBroadcaster()
        unrelated_queue: asyncio.Queue[Any] = asyncio.Queue()

        # Should not raise any exception
        broadcaster.unsubscribe(unrelated_queue)

        assert broadcaster.subscriber_count == 0


class TestSSEBroadcasterFullQueueHandling:
    """Tests for SSEBroadcaster handling of full subscriber queues."""

    @pytest.mark.asyncio
    async def test_publish_to_full_queue_silently_drops_event(self) -> None:
        """GIVEN a subscriber queue that is full (maxsize=1 with 1 item) WHEN publish(event) is called THEN the full queue's item is silently dropped (no QueueFull raised)."""
        broadcaster = SSEBroadcaster()
        # Create a queue with maxsize=1 and pre-fill it
        full_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        full_queue.put_nowait({"type": "old_event"})

        # Manually add the full queue as a subscriber (testing internal behavior)
        broadcaster._subscribers.add(full_queue)

        new_event: dict[str, Any] = {"type": "new_event"}

        # Should not raise asyncio.QueueFull
        broadcaster.publish(new_event)

        # Queue should still have exactly 1 item (either old or new depending on implementation)
        assert full_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_publish_to_mixed_full_and_empty_queues(self) -> None:
        """GIVEN subscribers with mixed full and non-full queues WHEN publish(event) is called THEN non-full queues receive the event and no error is raised."""
        broadcaster = SSEBroadcaster()

        # Normal subscriber
        normal_queue = broadcaster.subscribe()

        # Full queue subscriber (manually added with maxsize constraint)
        full_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        full_queue.put_nowait({"type": "blocking_event"})
        broadcaster._subscribers.add(full_queue)

        # Another normal subscriber
        normal_queue2 = broadcaster.subscribe()

        new_event: dict[str, Any] = {"type": "broadcast_event"}

        # Should not raise any exception
        broadcaster.publish(new_event)

        # Normal queues should receive the event
        assert normal_queue.get_nowait() == new_event
        assert normal_queue2.get_nowait() == new_event

        # Full queue should still have exactly 1 item
        assert full_queue.qsize() == 1


class TestSSEEvent:
    """Tests to verify SSEEvent is exported and usable."""

    def test_sse_event_is_importable(self) -> None:
        """GIVEN the sse module WHEN SSEEvent is imported THEN it should be a valid type."""
        # SSEEvent should be importable (verified by the import at top of file)
        assert SSEEvent is not None

    def test_sse_event_can_be_used_as_type_annotation(self) -> None:
        """GIVEN SSEEvent WHEN used as a type annotation THEN it should work correctly."""
        # This test ensures SSEEvent can be used for typing
        event: SSEEvent = {"event": "message", "data": "test"}  # type: ignore[assignment]
        assert event is not None
