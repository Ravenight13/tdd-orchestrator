"""Worker pool configuration, constants, and SDK integration.

Defines worker configuration dataclasses, model selection constants,
and optional Claude Agent SDK integration stubs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..models import Stage

# Stage-specific timeout limits (seconds)
# Prevents SDK calls from hanging indefinitely
STAGE_TIMEOUTS: dict[Stage, int] = {
    Stage.RED: 300,  # 5 min - writing failing tests
    Stage.RED_FIX: 300,  # 5 min - fixing static review issues
    Stage.GREEN: 600,  # 10 min - implementing code to pass tests
    Stage.VERIFY: 60,  # 1 min - running quality checks
    Stage.REFACTOR: 300,  # 5 min - improving code structure
    Stage.FIX: 300,  # 5 min - fixing issues
    Stage.RE_VERIFY: 60,  # 1 min - re-running quality checks
}

# Aggregate timeout for GREEN retry (all attempts combined)
# Default 30 minutes; can be overridden via config 'max_green_retry_time_seconds'
DEFAULT_GREEN_RETRY_TIMEOUT_SECONDS = 1800

# Model selection based on task complexity (PLAN8)
# Set via ANTHROPIC_MODEL env var before SDK calls
MODEL_MAP: dict[str, str] = {
    "low": "claude-haiku-4-5-20251001",
    "medium": "claude-sonnet-4-5-20250929",
    "high": "claude-opus-4-5-20251101",
}

# Decomposition always uses Opus (needs full reasoning capability)
DECOMPOSITION_MODEL = "claude-opus-4-5-20251101"

# Escalation model for GREEN retries (when first attempt fails)
ESCALATION_MODEL = "claude-opus-4-5-20251101"

# RED stage always uses Opus (test accuracy is critical)
RED_STAGE_MODEL = "claude-opus-4-5-20251101"

# REFACTOR stage uses Opus (needs strong reasoning about code structure)
REFACTOR_MODEL = "claude-opus-4-5-20251101"

# Maximum test output size to include in retry prompts (prevents context overflow)
MAX_TEST_OUTPUT_SIZE = 3000


def set_model_for_complexity(complexity: str) -> str:
    """Set ANTHROPIC_MODEL environment variable based on task complexity.

    Args:
        complexity: Task complexity level ("low", "medium", "high").

    Returns:
        The model that was set.
    """
    import os

    model = MODEL_MAP.get(complexity, MODEL_MAP["medium"])
    os.environ["ANTHROPIC_MODEL"] = model
    return model


if TYPE_CHECKING:
    pass

# Agent SDK (optional - graceful degradation if not installed)
# Define stub types first, then optionally override with real SDK
HAS_AGENT_SDK = False
ClaudeAgentOptions: Any = None


def sdk_query(*args: Any, **kwargs: Any) -> Any:
    """Stub for sdk_query when SDK is not available."""
    raise RuntimeError("claude_agent_sdk not installed")


class _StubAgentOptions:
    """Stub for ClaudeAgentOptions when SDK is not available."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("claude_agent_sdk not installed")


ClaudeAgentOptions = _StubAgentOptions

try:
    from claude_agent_sdk import (  # type: ignore[import-not-found]
        ClaudeAgentOptions as _SDKAgentOptions,
        query as _sdk_query,
    )

    ClaudeAgentOptions = _SDKAgentOptions
    sdk_query = _sdk_query
    HAS_AGENT_SDK = True
except ImportError:
    pass  # Keep the stubs defined above


@dataclass
class WorkerConfig:
    """Configuration for worker pool."""

    max_workers: int = 2
    max_invocations_per_session: int = 100
    budget_warning_threshold: int = 80
    heartbeat_interval_seconds: int = 30
    claim_timeout_seconds: int = 300
    worker_timeout_seconds: int = 600
    use_local_branches: bool = False
    single_branch_mode: bool = False
    git_stash_enabled: bool = True
    progress_file_enabled: bool = True
    progress_file_path: str = "tdd-progress.md"


@dataclass
class WorkerStats:
    """Statistics for a worker."""

    worker_id: int
    tasks_completed: int = 0
    tasks_failed: int = 0
    invocations: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since worker started."""
        return time.time() - self.start_time


@dataclass
class PoolResult:
    """Result of running the worker pool."""

    tasks_completed: int
    tasks_failed: int
    total_invocations: int
    worker_stats: list[WorkerStats]
    stopped_reason: str | None = None
