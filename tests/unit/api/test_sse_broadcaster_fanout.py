"""Tests for SSEBroadcaster subscribe/unsubscribe and fan-out publish functionality."""

import asyncio

import pytest

from tdd_orchestrator.api.sse import SSEBroadcaster, SSEEvent, _SSESubscription


class TestSSEBroadcasterSubscribe:
    """Tests for SSEBroadcaster.subscribe() method."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_sse_subscription(self) -> None:
        """GIVEN a newly created SSEBroadcaster WHEN subscribe() is called THEN it returns an _SSESubscription instance."""
        broadcaster = SSEBroadcaster()

        subscription = broadcaster.subscribe()

        assert isinstance(subscription, _SSESubscription)

    @pytest.mark.asyncio
    async def test_subscribe_increases_subscriber_count(self) -> None:
        """GIVEN a newly created SSEBroadcaster WHEN subscribe() is called THEN the broadcaster's internal subscriber count increases by one."""
        broadcaster = SSEBroadcaster()
        initial_count = broadcaster.subscriber_count

        broadcaster.subscribe()

        assert broadcaster.subscriber_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_multiple_subscribes_increase_count_correctly(self) -> None:
        """GIVEN a newly created SSEBroadcaster WHEN subscribe() is called multiple times THEN the subscriber count reflects total subscribers."""
        broadcaster = SSEBroadcaster()

        broadcaster.subscribe()
        broadcaster.subscribe()
        broadcaster.subscribe()

        assert broadcaster.subscriber_count == 3


class TestSSEBroadcasterPublish:
    """Tests for SSEBroadcaster.publish() method."""

    @pytest.mark.asyncio
    async def test_publish_delivers_event_to_all_subscribers(self) -> None:
        """GIVEN an SSEBroadcaster with 3 subscribers WHEN publish(SSEEvent) is called THEN all 3 subscriber queues receive the same event object."""
        broadcaster = SSEBroadcaster()
        sub1 = broadcaster.subscribe()
        sub2 = broadcaster.subscribe()
        sub3 = broadcaster.subscribe()

        event = SSEEvent(data="hello", event="test")
        await broadcaster.publish(event)

        received1 = sub1.queue.get_nowait()
        received2 = sub2.queue.get_nowait()
        received3 = sub3.queue.get_nowait()

        assert received1 == event
        assert received2 == event
        assert received3 == event

    @pytest.mark.asyncio
    async def test_publish_uses_put_nowait_nonblocking(self) -> None:
        """GIVEN an SSEBroadcaster with subscribers WHEN publish(SSEEvent) is called THEN it uses non-blocking put_nowait."""
        broadcaster = SSEBroadcaster()
        sub = broadcaster.subscribe()

        event = SSEEvent(data="test", event="test")
        await broadcaster.publish(event)

        # If put_nowait was used, the item should be immediately available
        assert not sub.queue.empty()
        received = sub.queue.get_nowait()
        assert received == event

    @pytest.mark.asyncio
    async def test_publish_with_zero_subscribers_succeeds(self) -> None:
        """GIVEN an SSEBroadcaster with 0 subscribers WHEN publish(SSEEvent) is called THEN no error is raised and the method completes successfully."""
        broadcaster = SSEBroadcaster()

        event = SSEEvent(data="no subscribers", event="test")

        # Should not raise any exception
        await broadcaster.publish(event)

        assert broadcaster.subscriber_count == 0


class TestSSEBroadcasterUnsubscribe:
    """Tests for SSEBroadcaster.unsubscribe() method."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscriber(self) -> None:
        """GIVEN an SSEBroadcaster with 2 subscribers WHEN one subscriber is unsubscribed THEN subscriber count decreases."""
        broadcaster = SSEBroadcaster()
        sub1 = broadcaster.subscribe()
        broadcaster.subscribe()

        await broadcaster.unsubscribe(sub1)

        assert broadcaster.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribed_queue_does_not_receive_events(self) -> None:
        """GIVEN an SSEBroadcaster with 2 subscribers WHEN one is unsubscribed and publish(SSEEvent) is called THEN only the remaining subscriber receives the event."""
        broadcaster = SSEBroadcaster()
        sub1 = broadcaster.subscribe()
        sub2 = broadcaster.subscribe()

        await broadcaster.unsubscribe(sub1)

        event = SSEEvent(data="after unsubscribe", event="test")
        await broadcaster.publish(event)

        # Unsubscribed queue should remain empty
        assert sub1.queue.empty()

        # Remaining subscriber should receive the event
        received = sub2.queue.get_nowait()
        assert received == event

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_subscription_is_safe(self) -> None:
        """GIVEN an SSEBroadcaster WHEN unsubscribe is called with a subscription whose queue was never added THEN no error is raised."""
        broadcaster = SSEBroadcaster()
        # Create a subscription that was never registered via subscribe()
        orphan_queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        orphan_sub = _SSESubscription(orphan_queue, broadcaster)

        # Should not raise any exception
        await broadcaster.unsubscribe(orphan_sub)

        assert broadcaster.subscriber_count == 0


class TestSSEBroadcasterFullQueueHandling:
    """Tests for SSEBroadcaster behavior when subscriber queues are full."""

    @pytest.mark.asyncio
    async def test_publish_to_full_queue_silently_drops_event(self) -> None:
        """GIVEN an SSEBroadcaster with a subscriber WHEN publish(SSEEvent) is called THEN no QueueFull exception is raised."""
        broadcaster = SSEBroadcaster()
        sub = broadcaster.subscribe()

        event = SSEEvent(data="test", event="test")

        # This should not raise QueueFull
        await broadcaster.publish(event)

        assert not sub.queue.empty()

    @pytest.mark.asyncio
    async def test_full_queue_does_not_affect_other_subscribers(self) -> None:
        """GIVEN an SSEBroadcaster with two subscribers WHEN publish is called twice THEN both queues receive events independently."""
        broadcaster = SSEBroadcaster()
        sub1 = broadcaster.subscribe()
        sub2 = broadcaster.subscribe()

        # Publish first event
        event1 = SSEEvent(data="first", event="test")
        await broadcaster.publish(event1)

        # Consume from sub2 but not sub1
        sub2.queue.get_nowait()

        # Publish second event - sub1 now has 1 item, sub2 is empty
        event2 = SSEEvent(data="second", event="test")
        await broadcaster.publish(event2)

        # sub2 should have received event2
        received = sub2.queue.get_nowait()
        assert received == event2

        # sub1 should have both events (no maxsize)
        assert not sub1.queue.empty()


class TestSSEBroadcasterWithMaxsizeQueue:
    """Tests specifically for queues with maxsize constraints."""

    @pytest.mark.asyncio
    async def test_publish_to_default_queue_handles_multiple_events(self) -> None:
        """GIVEN a subscriber queue WHEN multiple events are published THEN all are received in order."""
        broadcaster = SSEBroadcaster()
        sub = broadcaster.subscribe()

        first_event = SSEEvent(data="first", event="test")
        await broadcaster.publish(first_event)

        second_event = SSEEvent(data="second", event="test")
        await broadcaster.publish(second_event)

        # Both events should be in the queue
        assert not sub.queue.empty()
        assert sub.queue.get_nowait() == first_event
        assert sub.queue.get_nowait() == second_event

    @pytest.mark.asyncio
    async def test_mixed_consumption_patterns(self) -> None:
        """GIVEN multiple subscribers with mixed queue states WHEN publish is called THEN non-full queues receive events."""
        broadcaster = SSEBroadcaster()
        sub1 = broadcaster.subscribe()
        sub2 = broadcaster.subscribe()
        sub3 = broadcaster.subscribe()

        # Publish and consume from some queues to create mixed state
        event1 = SSEEvent(data="event1", event="test")
        await broadcaster.publish(event1)

        # Consume from sub1 and sub3, leave sub2 with the event
        sub1.queue.get_nowait()
        sub3.queue.get_nowait()

        # Now publish another event
        event2 = SSEEvent(data="event2", event="test")
        await broadcaster.publish(event2)

        # sub1 and sub3 should have event2
        received1 = sub1.queue.get_nowait()
        received3 = sub3.queue.get_nowait()

        assert received1 == event2
        assert received3 == event2

        # sub2 should have event1 still (and event2 since no maxsize)
        received2_first = sub2.queue.get_nowait()
        assert received2_first == event1


class TestSSEBroadcasterEdgeCases:
    """Edge case tests for SSEBroadcaster."""

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_same_subscription_multiple_times(self) -> None:
        """GIVEN an SSEBroadcaster WHEN a subscription is subscribed, unsubscribed, and the pattern repeats THEN counts are correct."""
        broadcaster = SSEBroadcaster()

        sub = broadcaster.subscribe()
        assert broadcaster.subscriber_count == 1

        await broadcaster.unsubscribe(sub)
        assert broadcaster.subscriber_count == 0

        # Re-subscribing should work
        sub2 = broadcaster.subscribe()
        assert broadcaster.subscriber_count == 1
        assert isinstance(sub2, _SSESubscription)

    @pytest.mark.asyncio
    async def test_publish_empty_data_event(self) -> None:
        """GIVEN an SSEBroadcaster with subscribers WHEN publish is called with an empty-data SSEEvent THEN subscribers receive it."""
        broadcaster = SSEBroadcaster()
        sub = broadcaster.subscribe()

        event = SSEEvent(data="")
        await broadcaster.publish(event)

        received = sub.queue.get_nowait()
        assert received.data == ""

    @pytest.mark.asyncio
    async def test_publish_complex_event(self) -> None:
        """GIVEN an SSEBroadcaster with subscribers WHEN publish is called with a fully-populated SSEEvent THEN subscribers receive the exact event."""
        broadcaster = SSEBroadcaster()
        sub = broadcaster.subscribe()

        event = SSEEvent(
            data='{"nested": {"deep": "value"}, "list": [1, 2, 3]}',
            event="complex",
            id="evt-1",
            retry=5000,
        )
        await broadcaster.publish(event)

        received = sub.queue.get_nowait()
        assert received == event
        assert received.event == "complex"
        assert received.id == "evt-1"
        assert received.retry == 5000
