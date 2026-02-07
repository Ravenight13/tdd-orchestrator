"""TDD Orchestrator Agent.

This package provides MCP tools, hooks, and orchestration logic for managing
Test-Driven Development workflows with Claude agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .database import OrchestratorDB, get_db, reset_db, set_db_path
from .task_loader import LoadResult, load_tdd_tasks
from .hooks import (
    get_orchestrator_hooks,
    post_tool_use_hook,
    pre_tool_use_hook,
    stop_hook,
)
from .git_coordinator import GitCoordinator
from .merge_coordinator import MergeCoordinator, MergeResult, SlackNotifier
from .worker_pool import PoolResult, Worker, WorkerConfig, WorkerPool, WorkerStats
from .cli import cli, main

# Conditionally import SDK-dependent modules
# These require claude_agent_sdk which may not be installed
try:
    from .mcp_tools import (
        ALL_TOOLS,
        create_orchestrator_mcp_server,
        task_get_by_key,
        task_get_next,
        task_get_stats,
        task_mark_failing,
        task_mark_passing,
    )
except ImportError:
    # SDK not installed - provide None placeholders
    ALL_TOOLS = None  # type: ignore[assignment]
    create_orchestrator_mcp_server = None  # type: ignore[assignment]
    task_get_by_key = None
    task_get_next = None
    task_get_stats = None
    task_mark_failing = None
    task_mark_passing = None

if TYPE_CHECKING:
    pass

__all__ = [
    # Database
    "OrchestratorDB",
    "get_db",
    "reset_db",
    "set_db_path",
    # Task Loader
    "load_tdd_tasks",
    "LoadResult",
    # Hooks
    "get_orchestrator_hooks",
    "pre_tool_use_hook",
    "post_tool_use_hook",
    "stop_hook",
    # MCP Server (requires claude_agent_sdk)
    "create_orchestrator_mcp_server",
    # Individual tools (requires claude_agent_sdk)
    "task_get_next",
    "task_mark_passing",
    "task_mark_failing",
    "task_get_stats",
    "task_get_by_key",
    # Tool collection (requires claude_agent_sdk)
    "ALL_TOOLS",
    # Parallel Execution
    "GitCoordinator",
    "MergeCoordinator",
    "MergeResult",
    "SlackNotifier",
    # Worker Pool
    "Worker",
    "WorkerPool",
    "WorkerConfig",
    "WorkerStats",
    "PoolResult",
    # CLI
    "cli",
    "main",
]
