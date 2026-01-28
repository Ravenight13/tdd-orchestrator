"""Circuit breaker configuration for TDD orchestrator.

This module defines configuration dataclasses for circuit breakers at
three levels: stage, worker, and system. Each level has different
thresholds and behaviors appropriate to its scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class CircuitState(Enum):
    """Possible states for a circuit breaker."""

    CLOSED = "closed"  # Normal operation - requests allowed
    OPEN = "open"  # Circuit tripped - requests blocked
    HALF_OPEN = "half_open"  # Testing recovery - limited requests


class CircuitLevel(Enum):
    """Hierarchy levels for circuit breakers."""

    STAGE = "stage"  # Per-stage within a task
    WORKER = "worker"  # Per-worker across tasks
    SYSTEM = "system"  # Global across all workers


@dataclass(frozen=True)
class StageCircuitConfig:
    """Configuration for stage-level circuit breakers.

    Stage circuits prevent infinite retries when a specific stage
    (e.g., GREEN, VERIFY) fails repeatedly for the same task.

    Attributes:
        max_failures: Consecutive failures before opening circuit.
        recovery_timeout_seconds: Time before attempting half-open.
        skip_to_next_task: If True, continue with other tasks when blocked.
        record_failure_pattern: If True, store patterns for analysis.
    """

    max_failures: int = 3
    recovery_timeout_seconds: int = 300  # 5 minutes
    skip_to_next_task: bool = True
    record_failure_pattern: bool = True


@dataclass(frozen=True)
class WorkerCircuitConfig:
    """Configuration for worker-level circuit breakers.

    Worker circuits pause unhealthy workers that fail consecutive tasks,
    preventing them from consuming resources on doomed operations.

    Attributes:
        max_consecutive_failures: Task failures before pausing worker.
        pause_duration_seconds: Initial pause duration.
        half_open_max_requests: Test requests allowed in half-open.
        success_threshold: Successes needed to close circuit.
        max_extensions: Maximum times pause can be extended.
    """

    max_consecutive_failures: int = 3
    pause_duration_seconds: int = 300  # 5 minutes
    half_open_max_requests: int = 1
    success_threshold: int = 1
    max_extensions: int = 3


@dataclass(frozen=True)
class SystemCircuitConfig:
    """Configuration for system-level circuit breakers.

    System circuits halt execution when widespread failures indicate
    a systemic issue (e.g., API outage, network problems).

    Attributes:
        failure_threshold_percent: Percentage of workers failing to trip.
        monitoring_window_seconds: Time window for calculating failure rate.
        auto_recovery_enabled: If True, attempt automatic recovery.
        recovery_delay_seconds: Time before attempting recovery.
        min_workers_for_threshold: Minimum workers before threshold applies.
        graceful_shutdown_timeout: Seconds to wait for in-flight tasks.
    """

    failure_threshold_percent: int = 50
    monitoring_window_seconds: int = 300  # 5 minutes
    auto_recovery_enabled: bool = True
    recovery_delay_seconds: int = 600  # 10 minutes
    min_workers_for_threshold: int = 2
    graceful_shutdown_timeout: int = 60


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Master configuration containing all circuit breaker settings.

    This is the main configuration object passed to the CircuitBreakerRegistry.
    It contains sub-configurations for each level plus global settings.

    Attributes:
        stage: Stage-level circuit configuration.
        worker: Worker-level circuit configuration.
        system: System-level circuit configuration.
        failure_mode: How to count failures ('consecutive' or 'sliding_window').
        sliding_window_seconds: Window size if using sliding_window mode.
        enable_notifications: If True, send Slack notifications on state changes.
        notification_throttle_seconds: Minimum time between notifications.
    """

    stage: StageCircuitConfig = field(default_factory=StageCircuitConfig)
    worker: WorkerCircuitConfig = field(default_factory=WorkerCircuitConfig)
    system: SystemCircuitConfig = field(default_factory=SystemCircuitConfig)

    # Global settings
    failure_mode: Literal["consecutive", "sliding_window"] = "consecutive"
    sliding_window_seconds: int = 60
    enable_notifications: bool = True
    notification_throttle_seconds: int = 300  # 5 minutes


# Default configuration instance for convenience
DEFAULT_CONFIG = CircuitBreakerConfig()
