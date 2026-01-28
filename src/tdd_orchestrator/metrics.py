"""Metrics collection for circuit breaker monitoring.

Provides hooks for collecting and exporting metrics from circuit breakers.
Designed for integration with Prometheus, Grafana, or custom dashboards.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected."""

    COUNTER = "counter"  # Monotonically increasing count
    GAUGE = "gauge"  # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution of values


@dataclass
class MetricValue:
    """A single metric value with metadata."""

    name: str
    value: float
    metric_type: MetricType
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""

    def to_prometheus(self) -> str:
        """Format as Prometheus exposition format."""
        label_str = ""
        if self.labels:
            pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(pairs) + "}"
        return f"{self.name}{label_str} {self.value}"


@dataclass
class CircuitMetrics:
    """Aggregated metrics for a circuit breaker."""

    level: str
    identifier: str
    state: str
    failure_count: int
    success_count: int
    state_changes: int
    time_in_open_seconds: float
    time_in_half_open_seconds: float
    last_state_change: datetime | None
    recovery_count: int
    extensions_count: int


class MetricsCollector:
    """
    Collects metrics from circuit breakers for monitoring.

    Provides hooks for:
    - State change events
    - Failure/success counts
    - Recovery timing
    - Aggregated health status
    """

    def __init__(self) -> None:
        self._metrics: dict[str, MetricValue] = {}
        self._callbacks: list[Callable[[MetricValue], None]] = []
        self._state_timers: dict[str, dict[str, float]] = {}  # circuit_id -> state -> timestamp

    def register_callback(self, callback: Callable[[MetricValue], None]) -> None:
        """Register a callback for metric updates."""
        self._callbacks.append(callback)

    def record_state_change(
        self,
        level: str,
        identifier: str,
        from_state: str,
        to_state: str,
    ) -> None:
        """Record a circuit state change event."""
        circuit_id = f"{level}:{identifier}"
        now = time.time()

        # Track time in previous state
        if circuit_id in self._state_timers and from_state in self._state_timers[circuit_id]:
            duration = now - self._state_timers[circuit_id][from_state]
            self._emit_metric(
                name="circuit_breaker_state_duration_seconds",
                value=duration,
                metric_type=MetricType.GAUGE,
                labels={"level": level, "identifier": identifier, "state": from_state},
                description=f"Time spent in {from_state} state",
            )

        # Start timer for new state
        if circuit_id not in self._state_timers:
            self._state_timers[circuit_id] = {}
        self._state_timers[circuit_id][to_state] = now

        # Emit state change counter
        self._emit_metric(
            name="circuit_breaker_state_changes_total",
            value=1,
            metric_type=MetricType.COUNTER,
            labels={
                "level": level,
                "identifier": identifier,
                "from": from_state,
                "to": to_state,
            },
            description="Total state changes",
        )

        # Update current state gauge
        state_values = {"closed": 0, "open": 1, "half_open": 2}
        self._emit_metric(
            name="circuit_breaker_state",
            value=state_values.get(to_state, -1),
            metric_type=MetricType.GAUGE,
            labels={"level": level, "identifier": identifier},
            description="Current state (0=closed, 1=open, 2=half_open)",
        )

    def record_failure(self, level: str, identifier: str, error_type: str = "unknown") -> None:
        """Record a failure event."""
        self._emit_metric(
            name="circuit_breaker_failures_total",
            value=1,
            metric_type=MetricType.COUNTER,
            labels={"level": level, "identifier": identifier, "error_type": error_type},
            description="Total failures recorded",
        )

    def record_success(self, level: str, identifier: str) -> None:
        """Record a success event."""
        self._emit_metric(
            name="circuit_breaker_successes_total",
            value=1,
            metric_type=MetricType.COUNTER,
            labels={"level": level, "identifier": identifier},
            description="Total successes recorded",
        )

    def record_recovery(self, level: str, identifier: str, duration_seconds: float) -> None:
        """Record a successful recovery (open -> closed)."""
        self._emit_metric(
            name="circuit_breaker_recovery_duration_seconds",
            value=duration_seconds,
            metric_type=MetricType.HISTOGRAM,
            labels={"level": level, "identifier": identifier},
            description="Time to recover from open state",
        )
        self._emit_metric(
            name="circuit_breaker_recoveries_total",
            value=1,
            metric_type=MetricType.COUNTER,
            labels={"level": level, "identifier": identifier},
            description="Total recoveries",
        )

    def record_check_latency(self, level: str, identifier: str, latency_ms: float) -> None:
        """Record circuit check latency."""
        self._emit_metric(
            name="circuit_breaker_check_latency_ms",
            value=latency_ms,
            metric_type=MetricType.HISTOGRAM,
            labels={"level": level, "identifier": identifier},
            description="Latency of check_and_allow calls",
        )

    def get_all_metrics(self) -> list[MetricValue]:
        """Get all current metrics."""
        return list(self._metrics.values())

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
        lines = []
        for metric in self._metrics.values():
            if metric.description:
                lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {metric.metric_type.value}")
            lines.append(metric.to_prometheus())
        return "\n".join(lines)

    def _emit_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType,
        labels: dict[str, str],
        description: str = "",
    ) -> None:
        """Emit a metric and notify callbacks."""
        metric = MetricValue(
            name=name,
            value=value,
            metric_type=metric_type,
            labels=labels,
            description=description,
        )

        # Store with unique key
        key = f"{name}:{':'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"
        self._metrics[key] = metric

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(metric)
            except Exception as e:
                logger.error("Metrics callback error: %s", e)


# Global metrics collector instance
_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_metrics_collector() -> None:
    """Reset the global metrics collector (for testing)."""
    global _collector
    _collector = None
