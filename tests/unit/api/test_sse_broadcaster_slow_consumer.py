"""Tests for SSEBroadcaster slow consumer detection.

Tests verify that subscribers with full queues are automatically removed
during publish() to prevent blocking healthy subscribers.
"""

import asyncio

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent


class TestSSEBroadcasterSlowConsumerDetection:
    """Test slow consumer detection and removal in SSEBroadcaster."""

    @pytest.mark.asyncio
    async def test_slow_subscriber_removed_when_queue_full_during_publish(self) -> None:
        """GIVEN a subscriber with full queue, WHEN publish() is called, THEN subscriber is removed."""
        broadcaster = SSEBroadcaster()

        # Create a queue with maxsize=1 and fill it
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        filler_event = SSEEvent(data="filler")
        await slow_queue.put(filler_event)

        # Subscribe with the full queue
        broadcaster.subscribe(slow_queue)
        initial_count = broadcaster.subscriber_count
        assert initial_count == 1

        # Publish should detect slow consumer and remove it
        new_event = SSEEvent(data="new_event")
        await broadcaster.publish(new_event)

        # Slow subscriber should be removed
        assert broadcaster.subscriber_count == 0
        # Queue should still have only the original event (new one wasn't added)
        assert slow_queue.qsize() == 1
        assert slow_queue.get_nowait() == filler_event

    @pytest.mark.asyncio
    async def test_healthy_subscribers_receive_event_when_one_is_slow(self) -> None:
        """GIVEN three subscribers where one is slow, WHEN publish(), THEN two healthy receive event."""
        broadcaster = SSEBroadcaster()

        # Create two healthy queues with capacity
        healthy_queue_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        healthy_queue_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        # Create a slow queue that's already full
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(data="blocking"))

        # Subscribe all three
        broadcaster.subscribe(healthy_queue_1)
        broadcaster.subscribe(healthy_queue_2)
        broadcaster.subscribe(slow_queue)
        assert broadcaster.subscriber_count == 3

        # Publish event
        event = SSEEvent(data="test_message")
        await broadcaster.publish(event)

        # Two healthy subscribers remain, slow one removed
        assert broadcaster.subscriber_count == 2

        # Healthy queues received the event
        received_1 = healthy_queue_1.get_nowait()
        received_2 = healthy_queue_2.get_nowait()
        assert received_1.data == "test_message"
        assert received_2.data == "test_message"

        # Slow queue still has only original event
        assert slow_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_removed_slow_subscriber_not_contacted_on_subsequent_publish(self) -> None:
        """GIVEN a removed slow subscriber, WHEN subsequent publish(), THEN it's not contacted."""
        broadcaster = SSEBroadcaster()

        # Create a healthy queue and a slow queue
        healthy_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(data="blocking"))

        broadcaster.subscribe(healthy_queue)
        broadcaster.subscribe(slow_queue)
        assert broadcaster.subscriber_count == 2

        # First publish removes slow subscriber
        event_1 = SSEEvent(data="first")
        await broadcaster.publish(event_1)
        assert broadcaster.subscriber_count == 1

        # Second publish should only go to healthy subscriber
        event_2 = SSEEvent(data="second")
        await broadcaster.publish(event_2)

        # Healthy queue should have both events
        assert healthy_queue.qsize() == 2
        first_received = healthy_queue.get_nowait()
        second_received = healthy_queue.get_nowait()
        assert first_received.data == "first"
        assert second_received.data == "second"

        # Slow queue should still have only the original blocking event
        assert slow_queue.qsize() == 1
        assert broadcaster.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_no_subscribers_removed_when_all_have_capacity(self) -> None:
        """GIVEN all subscribers with capacity, WHEN publish(), THEN no subscribers removed."""
        broadcaster = SSEBroadcaster()

        # Create multiple healthy queues
        queue_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        queue_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        queue_3: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        broadcaster.subscribe(queue_1)
        broadcaster.subscribe(queue_2)
        broadcaster.subscribe(queue_3)
        assert broadcaster.subscriber_count == 3

        # Publish event
        event = SSEEvent(data="broadcast")
        await broadcaster.publish(event)

        # All subscribers should remain (zero false positives)
        assert broadcaster.subscriber_count == 3

        # All queues received the event
        assert queue_1.get_nowait().data == "broadcast"
        assert queue_2.get_nowait().data == "broadcast"
        assert queue_3.get_nowait().data == "broadcast"

    @pytest.mark.asyncio
    async def test_single_slow_subscriber_removed_leaves_zero_count(self) -> None:
        """GIVEN single subscriber with full queue, WHEN removed, THEN count is 0."""
        broadcaster = SSEBroadcaster()

        # Create and fill a queue
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(data="blocking"))

        broadcaster.subscribe(slow_queue)
        assert broadcaster.subscriber_count == 1

        # Publish removes the slow subscriber
        await broadcaster.publish(SSEEvent(data="test"))

        # No subscribers remain
        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_publish_with_no_subscribers_completes_without_error(self) -> None:
        """GIVEN no subscribers, WHEN publish(), THEN completes successfully."""
        broadcaster = SSEBroadcaster()
        assert broadcaster.subscriber_count == 0

        # Publish with no subscribers should not raise
        event = SSEEvent(data="orphan_event")
        await broadcaster.publish(event)

        # Still no subscribers, no error
        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_publish_after_all_slow_subscribers_removed(self) -> None:
        """GIVEN all subscribers removed as slow, WHEN subsequent publish(), THEN succeeds."""
        broadcaster = SSEBroadcaster()

        # Create a slow subscriber
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(data="blocking"))

        broadcaster.subscribe(slow_queue)

        # First publish removes slow subscriber
        await broadcaster.publish(SSEEvent(data="first"))
        assert broadcaster.subscriber_count == 0

        # Subsequent publish with no subscribers should succeed
        await broadcaster.publish(SSEEvent(data="second"))
        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_multiple_slow_subscribers_all_removed(self) -> None:
        """GIVEN multiple slow subscribers, WHEN publish(), THEN all are removed."""
        broadcaster = SSEBroadcaster()

        # Create multiple slow queues
        slow_queues: list[asyncio.Queue[SSEEvent]] = []
        for i in range(3):
            queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
            await queue.put(SSEEvent(data=f"blocking_{i}"))
            slow_queues.append(queue)
            broadcaster.subscribe(queue)

        assert broadcaster.subscriber_count == 3

        # Publish should remove all slow subscribers
        await broadcaster.publish(SSEEvent(data="test"))

        assert broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_mixed_slow_and_healthy_subscribers_correct_removal(self) -> None:
        """GIVEN mix of slow and healthy subscribers, WHEN publish(), THEN only slow removed."""
        broadcaster = SSEBroadcaster()

        # Create healthy queues
        healthy_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        healthy_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)

        # Create slow queues
        slow_1: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        slow_2: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_1.put(SSEEvent(data="blocking_1"))
        await slow_2.put(SSEEvent(data="blocking_2"))

        # Subscribe in mixed order
        broadcaster.subscribe(healthy_1)
        broadcaster.subscribe(slow_1)
        broadcaster.subscribe(healthy_2)
        broadcaster.subscribe(slow_2)
        assert broadcaster.subscriber_count == 4

        # Publish
        event = SSEEvent(data="test")
        await broadcaster.publish(event)

        # Only healthy subscribers remain
        assert broadcaster.subscriber_count == 2

        # Healthy queues received the event
        assert healthy_1.get_nowait().data == "test"
        assert healthy_2.get_nowait().data == "test"

    @pytest.mark.asyncio
    async def test_slow_consumer_detection_preserves_event_data_integrity(self) -> None:
        """GIVEN slow consumer detection, WHEN publish(), THEN event data is intact for healthy."""
        broadcaster = SSEBroadcaster()

        healthy_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=10)
        slow_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=1)
        await slow_queue.put(SSEEvent(data="blocking"))

        broadcaster.subscribe(healthy_queue)
        broadcaster.subscribe(slow_queue)

        # Publish event with specific data
        event = SSEEvent(data="important_data", event="custom_type", id="msg-123")
        await broadcaster.publish(event)

        # Verify healthy subscriber received intact event
        received = healthy_queue.get_nowait()
        assert received.data == "important_data"
        assert received.event == "custom_type"
        assert received.id == "msg-123"

    @pytest.mark.asyncio
    async def test_subscriber_at_capacity_boundary_receives_event(self) -> None:
        """GIVEN subscriber with exactly one slot available, WHEN publish(), THEN receives event."""
        broadcaster = SSEBroadcaster()

        # Queue with maxsize=2, put 1 item (1 slot available)
        boundary_queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=2)
        await boundary_queue.put(SSEEvent(data="existing"))

        broadcaster.subscribe(boundary_queue)
        assert broadcaster.subscriber_count == 1

        # Publish should succeed since there's capacity
        event = SSEEvent(data="new_event")
        await broadcaster.publish(event)

        # Subscriber should remain (not incorrectly marked as slow)
        assert broadcaster.subscriber_count == 1

        # Queue should have both events
        assert boundary_queue.qsize() == 2
        first = boundary_queue.get_nowait()
        second = boundary_queue.get_nowait()
        assert first.data == "existing"
        assert second.data == "new_event"
