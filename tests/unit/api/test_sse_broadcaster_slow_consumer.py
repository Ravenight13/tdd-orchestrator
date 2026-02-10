"""Tests for SSEBroadcaster slow consumer detection and cleanup."""

import asyncio
from typing import Any

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


class TestSlowConsumerDetection:
    """Tests for automatic detection and removal of slow subscribers."""

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
        pre_fill_event = SSEEvent(event="prefill", data="blocking")
        await slow_queue.put(pre_fill_event)

        # Subscribe the slow consumer
        broadcaster.subscribe(slow_queue)
        assert len(broadcaster.subscribers) == 1

        # Publish a new event - should not raise QueueFull
        new_event = SSEEvent(event="test", data="payload")
        await broadcaster.publish(new_event)

        # Slow subscriber should be removed
        assert len(broadcaster.subscribers) == 0

    @pytest.mark.asyncio
    async def test_healthy_subscribers_receive_event_while_slow_removed(self) -> None:
        """
        GIVEN an SSEBroadcaster with three subscribers where one has a full queue
              and two have capacity
        WHEN publish() is called
        THEN the two healthy subscribers receive the event via their queues and
             the slow subscriber is removed, leaving exactly two subscribers registered
        """
        broadcaster = SSEBroadcaster()

        # Create two healthy queues with capacity
        healthy_queue1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        healthy_queue2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        # Create a slow queue that is already full
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        pre_fill_event = SSEEvent(event="prefill", data="blocking")
        await slow_queue.put(pre_fill_event)

        # Subscribe all three
        broadcaster.subscribe(healthy_queue1)
        broadcaster.subscribe(healthy_queue2)
        broadcaster.subscribe(slow_queue)
        assert len(broadcaster.subscribers) == 3

        # Publish an event
        test_event = SSEEvent(event="message", data="hello")
        await broadcaster.publish(test_event)

        # Healthy subscribers should receive the event
        received1 = await healthy_queue1.get()
        received2 = await healthy_queue2.get()
        assert received1.event == "message"
        assert received1.data == "hello"
        assert received2.event == "message"
        assert received2.data == "hello"

        # Slow subscriber should be removed, leaving exactly 2
        assert len(broadcaster.subscribers) == 2
        assert slow_queue not in broadcaster.subscribers
        assert healthy_queue1 in broadcaster.subscribers
        assert healthy_queue2 in broadcaster.subscribers

    @pytest.mark.asyncio
    async def test_removed_slow_consumer_not_contacted_in_subsequent_publish(self) -> None:
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
        pre_fill_event = SSEEvent(event="prefill", data="blocking")
        await slow_queue.put(pre_fill_event)

        # Subscribe both
        broadcaster.subscribe(healthy_queue)
        broadcaster.subscribe(slow_queue)
        assert len(broadcaster.subscribers) == 2

        # First publish removes the slow consumer
        first_event = SSEEvent(event="first", data="event1")
        await broadcaster.publish(first_event)

        # Slow subscriber should be removed
        assert len(broadcaster.subscribers) == 1
        assert slow_queue not in broadcaster.subscribers

        # Subsequent publishes should work fine with remaining subscriber
        second_event = SSEEvent(event="second", data="event2")
        await broadcaster.publish(second_event)

        third_event = SSEEvent(event="third", data="event3")
        await broadcaster.publish(third_event)

        # Healthy queue should have received all three events
        received1 = await healthy_queue.get()
        received2 = await healthy_queue.get()
        received3 = await healthy_queue.get()

        assert received1.event == "first"
        assert received2.event == "second"
        assert received3.event == "third"

        # Queue should be empty now
        assert healthy_queue.empty()

    @pytest.mark.asyncio
    async def test_no_false_positives_when_all_queues_have_capacity(self) -> None:
        """
        GIVEN an SSEBroadcaster with all subscribers having available queue capacity
        WHEN publish() is called with an event
        THEN all subscribers receive the event and no subscribers are removed
             (zero false positives in slow consumer detection)
        """
        broadcaster = SSEBroadcaster()

        # Create multiple healthy queues with capacity
        queue1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        queue2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        queue3: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        # Subscribe all
        broadcaster.subscribe(queue1)
        broadcaster.subscribe(queue2)
        broadcaster.subscribe(queue3)
        initial_count = len(broadcaster.subscribers)
        assert initial_count == 3

        # Publish multiple events
        for i in range(5):
            event = SSEEvent(event="test", data=f"payload_{i}")
            await broadcaster.publish(event)

        # All subscribers should still be registered (no false positives)
        assert len(broadcaster.subscribers) == 3

        # All queues should have received all 5 events
        assert queue1.qsize() == 5
        assert queue2.qsize() == 5
        assert queue3.qsize() == 5

        # Verify event content
        for i in range(5):
            event1 = await queue1.get()
            event2 = await queue2.get()
            event3 = await queue3.get()
            assert event1.data == f"payload_{i}"
            assert event2.data == f"payload_{i}"
            assert event3.data == f"payload_{i}"

    @pytest.mark.asyncio
    async def test_single_slow_subscriber_removed_leaves_zero_subscribers(self) -> None:
        """
        GIVEN an SSEBroadcaster with a single subscriber whose queue is full
        WHEN publish() removes it as a slow consumer
        THEN the broadcaster's subscriber count is 0 and a subsequent publish()
             with no subscribers completes successfully without error
        """
        broadcaster = SSEBroadcaster()

        # Create and fill a single slow queue
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        pre_fill_event = SSEEvent(event="prefill", data="blocking")
        await slow_queue.put(pre_fill_event)

        # Subscribe the single slow consumer
        broadcaster.subscribe(slow_queue)
        assert len(broadcaster.subscribers) == 1

        # Publish should remove the slow consumer
        event = SSEEvent(event="test", data="payload")
        await broadcaster.publish(event)

        # Subscriber count should be 0
        assert len(broadcaster.subscribers) == 0

        # Subsequent publish with no subscribers should complete without error
        another_event = SSEEvent(event="another", data="data")
        await broadcaster.publish(another_event)  # Should not raise

        # Still zero subscribers
        assert len(broadcaster.subscribers) == 0


class TestSlowConsumerEdgeCases:
    """Edge case tests for slow consumer detection."""

    @pytest.mark.asyncio
    async def test_publish_to_empty_broadcaster_succeeds(self) -> None:
        """Publish with no subscribers should complete without error."""
        broadcaster = SSEBroadcaster()

        assert len(broadcaster.subscribers) == 0

        event = SSEEvent(event="test", data="payload")
        await broadcaster.publish(event)  # Should not raise

        assert len(broadcaster.subscribers) == 0

    @pytest.mark.asyncio
    async def test_multiple_slow_consumers_all_removed(self) -> None:
        """When multiple consumers are slow, all should be removed."""
        broadcaster = SSEBroadcaster()

        # Create multiple slow queues (all full)
        slow_queues: list[asyncio.Queue[SSEEvent]] = []
        for _ in range(3):
            q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
            pre_fill = SSEEvent(event="prefill", data="blocking")
            await q.put(pre_fill)
            slow_queues.append(q)
            broadcaster.subscribe(q)

        # Create one healthy queue
        healthy_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        broadcaster.subscribe(healthy_queue)

        assert len(broadcaster.subscribers) == 4

        # Publish event
        event = SSEEvent(event="test", data="payload")
        await broadcaster.publish(event)

        # All slow consumers should be removed, only healthy remains
        assert len(broadcaster.subscribers) == 1
        assert healthy_queue in broadcaster.subscribers
        for sq in slow_queues:
            assert sq not in broadcaster.subscribers

        # Healthy queue received the event
        received = await healthy_queue.get()
        assert received.event == "test"
        assert received.data == "payload"

    @pytest.mark.asyncio
    async def test_queue_at_capacity_boundary_not_full(self) -> None:
        """A queue with exactly one slot available should receive the event."""
        broadcaster = SSEBroadcaster()

        # Create a queue with maxsize=2, put 1 item (1 slot available)
        boundary_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=2)
        pre_fill = SSEEvent(event="prefill", data="one")
        await boundary_queue.put(pre_fill)

        broadcaster.subscribe(boundary_queue)
        assert len(broadcaster.subscribers) == 1

        # Publish should succeed (queue has capacity)
        event = SSEEvent(event="test", data="payload")
        await broadcaster.publish(event)

        # Subscriber should NOT be removed
        assert len(broadcaster.subscribers) == 1
        assert boundary_queue in broadcaster.subscribers

        # Queue should now have 2 items
        assert boundary_queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_queue_becomes_full_after_successful_publish(self) -> None:
        """
        A queue that becomes full after receiving an event should only be
        removed on the next publish attempt.
        """
        broadcaster = SSEBroadcaster()

        # Create a queue with maxsize=1 (empty initially)
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        broadcaster.subscribe(queue)

        # First publish fills the queue
        event1 = SSEEvent(event="first", data="data1")
        await broadcaster.publish(event1)

        # Subscriber should still be there
        assert len(broadcaster.subscribers) == 1

        # Second publish should detect the full queue and remove subscriber
        event2 = SSEEvent(event="second", data="data2")
        await broadcaster.publish(event2)

        # Now subscriber should be removed
        assert len(broadcaster.subscribers) == 0

        # Original queue still has the first event
        received = await queue.get()
        assert received.event == "first"
        assert received.data == "data1"
