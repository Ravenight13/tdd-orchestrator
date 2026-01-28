"""Notification system for circuit breaker events.

Implements throttled Slack notifications with flapping detection.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for notification throttling."""

    throttle_seconds: int = 60  # Min seconds between notifications per circuit
    flapping_threshold: int = 5  # State changes to detect flapping
    flapping_window_seconds: int = 300  # Window for flapping detection
    slack_webhook_url: str | None = None
    enabled: bool = True


@dataclass
class NotificationRecord:
    """Record of a sent notification for throttling."""

    circuit_id: str  # level:identifier
    event_type: str
    sent_at: datetime
    message: str


class NotificationThrottler:
    """
    Throttles notifications to prevent alert fatigue.

    Key features:
    - Per-circuit throttling (max 1 notification per circuit per minute)
    - Flapping detection (suppress repeated open/close cycles)
    - Aggregation of similar events
    """

    def __init__(self, config: NotificationConfig | None = None) -> None:
        self._config = config or NotificationConfig()
        self._last_sent: dict[str, datetime] = {}  # circuit_id -> last_sent_time
        self._state_changes: dict[str, list[datetime]] = {}  # circuit_id -> timestamps
        self._pending_notifications: list[NotificationRecord] = []
        self._lock = asyncio.Lock()

    async def should_send(
        self,
        level: str,
        identifier: str,
        event_type: str,
    ) -> tuple[bool, str | None]:
        """
        Check if notification should be sent.

        Args:
            level: Circuit level (stage, worker, system)
            identifier: Circuit identifier
            event_type: Type of event (opened, closed, etc.)

        Returns:
            Tuple of (should_send, reason_if_not)
        """
        if not self._config.enabled:
            return False, "notifications_disabled"

        circuit_id = f"{level}:{identifier}"
        now = datetime.now()

        async with self._lock:
            # Check throttle window
            last_sent = self._last_sent.get(circuit_id)
            if last_sent:
                elapsed = (now - last_sent).total_seconds()
                if elapsed < self._config.throttle_seconds:
                    return (
                        False,
                        f"throttled ({elapsed:.0f}s < {self._config.throttle_seconds}s)",
                    )

            # Check for flapping
            if event_type in ("opened", "closed", "half_open"):
                if self._is_flapping(circuit_id, now):
                    return False, "flapping_detected"

            return True, None

    async def record_sent(
        self,
        level: str,
        identifier: str,
        event_type: str,
        message: str,
    ) -> None:
        """Record that a notification was sent."""
        circuit_id = f"{level}:{identifier}"
        now = datetime.now()

        async with self._lock:
            self._last_sent[circuit_id] = now

            # Track state changes for flapping detection
            if event_type in ("opened", "closed", "half_open"):
                if circuit_id not in self._state_changes:
                    self._state_changes[circuit_id] = []
                self._state_changes[circuit_id].append(now)

                # Clean old entries outside window
                cutoff = now - timedelta(seconds=self._config.flapping_window_seconds)
                self._state_changes[circuit_id] = [
                    ts for ts in self._state_changes[circuit_id] if ts > cutoff
                ]

    def _is_flapping(self, circuit_id: str, now: datetime) -> bool:
        """Check if circuit is flapping (rapid state changes)."""
        changes = self._state_changes.get(circuit_id, [])
        cutoff = now - timedelta(seconds=self._config.flapping_window_seconds)
        recent_changes = [ts for ts in changes if ts > cutoff]
        return len(recent_changes) >= self._config.flapping_threshold

    async def get_flapping_circuits(self) -> list[str]:
        """Get list of currently flapping circuits."""
        now = datetime.now()
        flapping = []

        async with self._lock:
            for circuit_id, changes in self._state_changes.items():
                cutoff = now - timedelta(seconds=self._config.flapping_window_seconds)
                recent = [ts for ts in changes if ts > cutoff]
                if len(recent) >= self._config.flapping_threshold:
                    flapping.append(circuit_id)

        return flapping


class SlackNotifier:
    """
    Sends circuit breaker notifications to Slack.

    Features:
    - Color-coded messages by severity
    - Structured blocks for readability
    - Rate limiting via throttler
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        throttler: NotificationThrottler | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._throttler = throttler or NotificationThrottler()

    async def notify_circuit_event(
        self,
        level: str,
        identifier: str,
        event_type: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """
        Send notification for circuit breaker event.

        Args:
            level: Circuit level (stage, worker, system)
            identifier: Circuit identifier
            event_type: Event type (opened, closed, etc.)
            reason: Human-readable reason
            details: Additional context

        Returns:
            True if notification was sent, False if throttled/failed
        """
        # Check throttling
        should_send, throttle_reason = await self._throttler.should_send(
            level, identifier, event_type
        )

        if not should_send:
            logger.debug(
                "Notification throttled: %s:%s - %s",
                level,
                identifier,
                throttle_reason,
            )
            return False

        # Build message
        message = self._build_message(level, identifier, event_type, reason, details)

        # Send if webhook configured
        if self._webhook_url:
            success = await self._send_to_slack(message)
            if success:
                await self._throttler.record_sent(level, identifier, event_type, reason)
            return success
        else:
            # Log only if no webhook
            logger.info("Circuit notification (no webhook): %s", message)
            await self._throttler.record_sent(level, identifier, event_type, reason)
            return True

    def _build_message(
        self,
        level: str,
        identifier: str,
        event_type: str,
        reason: str,
        details: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build Slack message payload."""
        # Suppress unused parameter warning - details reserved for future use
        _ = details

        # Color by event type
        colors = {
            "opened": "#FF0000",  # Red - circuit opened
            "closed": "#00FF00",  # Green - recovered
            "half_open": "#FFA500",  # Orange - testing
            "flapping_detected": "#FF00FF",  # Magenta - unstable
            "manual_reset": "#0000FF",  # Blue - admin action
        }
        color = colors.get(event_type, "#808080")

        # Build blocks
        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"Circuit Breaker: {event_type.upper()}",
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Level:* {level}"},
                                {"type": "mrkdwn", "text": f"*Circuit:* {identifier}"},
                            ],
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Reason:* {reason}",
                            },
                        },
                    ],
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

    async def _send_to_slack(self, message: dict[str, Any]) -> bool:
        """Send message to Slack webhook."""
        if not self._webhook_url:
            return False

        try:
            import aiohttp  # type: ignore[import-not-found]

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=message,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return True
                    else:
                        logger.error(
                            "Slack notification failed: %d %s",
                            response.status,
                            await response.text(),
                        )
                        return False
        except ImportError:
            logger.warning("aiohttp not installed - Slack notifications disabled")
            return False
        except Exception as e:
            logger.error("Slack notification error: %s", e)
            return False
