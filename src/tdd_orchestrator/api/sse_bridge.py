"""SSE bridge for wiring circuit breaker callbacks to SSE events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SSEBroadcaster(Protocol):
    """Protocol for SSE broadcaster."""

    async def broadcast(self, *, event_type: str, data: str) -> None:
        """Broadcast an SSE event to all connected clients."""
        ...


class MetricsCollector(Protocol):
    """Protocol for metrics collector."""

    def on_circuit_breaker_state_change(self, callback: Any) -> None:
        """Register a callback for circuit breaker state changes."""
        ...


def wire_circuit_breaker_sse(
    broadcaster: SSEBroadcaster,
    collector: MetricsCollector,
) -> None:
    """Wire circuit breaker state changes to SSE broadcasts.

    Args:
        broadcaster: SSE broadcaster instance
        collector: Metrics collector instance
    """

    def callback(payload: dict[str, Any]) -> None:
        """Callback fired on circuit breaker state change.

        Args:
            payload: Dictionary containing task_id, old_state, new_state, failure_count
        """
        # Add ISO-8601 timestamp
        data = {
            "task_id": payload["task_id"],
            "old_state": payload["old_state"],
            "new_state": payload["new_state"],
            "failure_count": payload["failure_count"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Broadcast the event
        try:
            # Run the async broadcast in the event loop
            asyncio.create_task(
                broadcaster.broadcast(
                    event_type="circuit_breaker_state_changed",
                    data=json.dumps(data),
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast circuit breaker state change: %s",
                e,
                exc_info=True,
            )

    # Register the callback
    collector.on_circuit_breaker_state_change(callback)
