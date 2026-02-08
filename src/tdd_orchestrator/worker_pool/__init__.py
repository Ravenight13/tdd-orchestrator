"""Worker pool package for parallel task execution.

Re-exports all public names for backward compatibility.
"""

from __future__ import annotations

from .circuit_breakers import RedFixAttemptTracker, StaticReviewCircuitBreaker
from .config import (
    ClaudeAgentOptions,
    DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS,
    HAS_AGENT_SDK,
    MAX_TEST_OUTPUT_SIZE,
    PoolResult,
    STAGE_MAX_TURNS,
    WorkerConfig,
    WorkerStats,
    sdk_query,
)
from .pool import WorkerPool
from .worker import Worker

__all__ = [
    "ClaudeAgentOptions",
    "DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS",
    "HAS_AGENT_SDK",
    "MAX_TEST_OUTPUT_SIZE",
    "PoolResult",
    "RedFixAttemptTracker",
    "STAGE_MAX_TURNS",
    "StaticReviewCircuitBreaker",
    "Worker",
    "WorkerConfig",
    "WorkerPool",
    "WorkerStats",
    "sdk_query",
]
