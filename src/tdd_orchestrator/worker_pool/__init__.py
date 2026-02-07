"""Worker pool package for parallel task execution.

Re-exports all public names for backward compatibility.
"""

from __future__ import annotations

from .circuit_breakers import RedFixAttemptTracker, StaticReviewCircuitBreaker
from .config import (
    DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS,
    MAX_TEST_OUTPUT_SIZE,
    PoolResult,
    WorkerConfig,
    WorkerStats,
)
from .pool import WorkerPool
from .worker import Worker

__all__ = [
    "DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS",
    "MAX_TEST_OUTPUT_SIZE",
    "PoolResult",
    "RedFixAttemptTracker",
    "StaticReviewCircuitBreaker",
    "Worker",
    "WorkerConfig",
    "WorkerPool",
    "WorkerStats",
]
