"""Tests for SSEBroadcaster slow consumer detection and cleanup."""

import asyncio
from typing import Any

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


class TestSSEBroadcasterSlowConsumerDetection:
    """Tests for slow consumer detection that drops subscribers with full queues."""

    @pytest.mark.asyncio
    async def test_slow_subscriber_removed_when_queue_full_during_publish(self) -> None:
        """
        GIVEN an SSEBroadcaster with a connected subscriber whose asyncio.Queue
              has maxsize=1 and is already full
        WHEN publish() is called with a new event
        THEN the slow subscriber is automatically removed from the broadcaster's
             subscriber set and the publish completes without raising QueueFull
        """
        broadcaster = SSEBroadcaster()

        # Create a queue with maxsize=1 and fill it
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        initial_event = SSEEvent(event="init", data="initial")
        await slow_queue.put(initial_event)

        # Subscribe with the already-full queue
        broadcaster.subscribe(slow_queue)

        # Verify subscriber is registered
        assert broadcaster.subscriber_count == 1

        # Publish a new event - should not raise QueueFull
        new_event = SSEEvent(event="test", data="new message")
        await broadcaster.publish(new_event)

        # Slow subscriber should be removed
        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_only_slow_subscriber_removed_healthy_subscribers_receive_event(self) -> None:
        """
        GIVEN an SSEBroadcaster with three subscribers where one has a full queue
              and two have capacity
        WHEN publish() is called
        THEN the two healthy subscribers receive the event via their queues and
             the slow subscriber is removed, leaving exactly two subscribers registered
        """
        broadcaster = SSEBroadcaster()

        # Create two healthy queues with capacity
        healthy_queue_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        healthy_queue_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        # Create a slow queue that's already full
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(event="filler", data="blocking"))

        # Subscribe all three
        broadcaster.subscribe(healthy_queue_1)
        broadcaster.subscribe(healthy_queue_2)
        broadcaster.subscribe(slow_queue)

        assert broadcaster.subscriber_count == 3

        # Publish event
        test_event = SSEEvent(event="message", data="hello")
        await broadcaster.publish(test_event)

        # Only slow subscriber should be removed
        assert broadcaster.subscriber_count == 2

        # Healthy subscribers should have received the event
        received_1 = await healthy_queue_1.get()
        received_2 = await healthy_queue_2.get()

        assert received_1.event == "message"
        assert received_1.data == "hello"
        assert received_2.event == "message"
        assert received_2.data == "hello"

    @pytest.mark.asyncio
    async def test_removed_slow_consumer_not_sent_to_on_subsequent_publish(self) -> None:
        """
        GIVEN an SSEBroadcaster with a subscriber whose queue becomes full
        WHEN the slow consumer is detected and removed during publish()
        THEN subsequent publish() calls no longer attempt to send to the removed
             subscriber and the remaining subscribers continue receiving events normally
        """
        broadcaster = SSEBroadcaster()

        # Create a healthy queue and a slow queue
        healthy_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)

        # Fill the slow queue
        await slow_queue.put(SSEEvent(event="filler", data="blocking"))

        broadcaster.subscribe(healthy_queue)
        broadcaster.subscribe(slow_queue)

        assert broadcaster.subscriber_count == 2

        # First publish - should remove slow consumer
        event_1 = SSEEvent(event="first", data="message 1")
        await broadcaster.publish(event_1)

        assert broadcaster.subscriber_count == 1

        # Drain the healthy queue
        received = await healthy_queue.get()
        assert received.data == "message 1"

        # Second publish - should only go to healthy subscriber
        event_2 = SSEEvent(event="second", data="message 2")
        await broadcaster.publish(event_2)

        # Healthy subscriber should still receive events
        received_2 = await healthy_queue.get()
        assert received_2.data == "message 2"

        # Slow queue should still only have original filler event (never got event_2)
        assert slow_queue.qsize() == 1
        filler = await slow_queue.get()
        assert filler.data == "blocking"
        assert slow_queue.empty()

    @pytest.mark.asyncio
    async def test_no_subscribers_removed_when_all_have_capacity(self) -> None:
        """
        GIVEN an SSEBroadcaster with all subscribers having available queue capacity
        WHEN publish() is called with an event
        THEN all subscribers receive the event and no subscribers are removed
             (zero false positives in slow consumer detection)
        """
        broadcaster = SSEBroadcaster()

        # Create multiple healthy queues with plenty of capacity
        queue_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)
        queue_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)
        queue_3: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)

        broadcaster.subscribe(queue_1)
        broadcaster.subscribe(queue_2)
        broadcaster.subscribe(queue_3)

        assert broadcaster.subscriber_count == 3

        # Publish multiple events
        for i in range(5):
            event = SSEEvent(event="ping", data=f"message {i}")
            await broadcaster.publish(event)

        # All subscribers should still be registered
        assert broadcaster.subscriber_count == 3

        # All queues should have received all 5 events
        assert queue_1.qsize() == 5
        assert queue_2.qsize() == 5
        assert queue_3.qsize() == 5

        # Verify content of messages
        for i in range(5):
            msg_1 = await queue_1.get()
            msg_2 = await queue_2.get()
            msg_3 = await queue_3.get()

            assert msg_1.data == f"message {i}"
            assert msg_2.data == f"message {i}"
            assert msg_3.data == f"message {i}"

    @pytest.mark.asyncio
    async def test_publish_succeeds_with_zero_subscribers_after_slow_removal(self) -> None:
        """
        GIVEN an SSEBroadcaster with a single subscriber whose queue is full
        WHEN publish() removes it as a slow consumer
        THEN the broadcaster's subscriber count is 0 and a subsequent publish()
             with no subscribers completes successfully without error
        """
        broadcaster = SSEBroadcaster()

        # Create and fill a single slow queue
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(event="filler", data="blocking"))

        broadcaster.subscribe(slow_queue)
        assert broadcaster.subscriber_count == 1

        # Publish - should remove the slow consumer
        event_1 = SSEEvent(event="test", data="first")
        await broadcaster.publish(event_1)

        # Subscriber count should now be 0
        assert broadcaster.subscriber_count == 0

        # Subsequent publish with no subscribers should complete without error
        event_2 = SSEEvent(event="test", data="second")
        await broadcaster.publish(event_2)  # Should not raise

        # Still zero subscribers
        assert broadcaster.subscriber_count == 0


class TestSSEBroadcasterSlowConsumerEdgeCases:
    """Edge cases for slow consumer detection."""

    @pytest.mark.asyncio
    async def test_publish_to_empty_broadcaster_succeeds(self) -> None:
        """Publishing to a broadcaster with no subscribers should succeed."""
        broadcaster = SSEBroadcaster()

        assert broadcaster.subscriber_count == 0

        event = SSEEvent(event="test", data="hello")
        await broadcaster.publish(event)  # Should not raise

        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_multiple_slow_consumers_all_removed(self) -> None:
        """When multiple consumers are slow, all should be removed."""
        broadcaster = SSEBroadcaster()

        # Create multiple slow queues (all full)
        slow_queues: list[asyncio.Queue[SSEEvent]] = []
        for i in range(3):
            q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
            await q.put(SSEEvent(event="filler", data=f"blocking {i}"))
            slow_queues.append(q)
            broadcaster.subscribe(q)

        # One healthy queue
        healthy_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        broadcaster.subscribe(healthy_queue)

        assert broadcaster.subscriber_count == 4

        # Publish - should remove all 3 slow consumers
        event = SSEEvent(event="test", data="message")
        await broadcaster.publish(event)

        # Only healthy subscriber remains
        assert broadcaster.subscriber_count == 1

        # Healthy queue received the event
        received = await healthy_queue.get()
        assert received.data == "message"

    @pytest.mark.asyncio
    async def test_queue_at_max_capacity_minus_one_receives_event(self) -> None:
        """A queue with exactly one slot available should receive the event."""
        broadcaster = SSEBroadcaster()

        # Create a queue with maxsize=2 and put 1 item (1 slot remaining)
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=2)
        await queue.put(SSEEvent(event="first", data="existing"))

        broadcaster.subscribe(queue)
        assert broadcaster.subscriber_count == 1

        # Publish - should succeed since there's capacity
        event = SSEEvent(event="second", data="new")
        await broadcaster.publish(event)

        # Subscriber should NOT be removed
        assert broadcaster.subscriber_count == 1

        # Queue should have both items
        assert queue.qsize() == 2

        first = await queue.get()
        second = await queue.get()
        assert first.data == "existing"
        assert second.data == "new"

    @pytest.mark.asyncio
    async def test_unbounded_queue_never_removed(self) -> None:
        """A queue with no maxsize (unbounded) should never be removed."""
        broadcaster = SSEBroadcaster()

        # Create an unbounded queue (maxsize=0 means unlimited)
        unbounded_queue: asyncio.Queue[SSEEvent] = asyncio.Queue()

        broadcaster.subscribe(unbounded_queue)

        # Publish many events
        for i in range(100):
            event = SSEEvent(event="flood", data=f"message {i}")
            await broadcaster.publish(event)

        # Subscriber should still be registered
        assert broadcaster.subscriber_count == 1

        # All events should be in the queue
        assert unbounded_queue.qsize() == 100
