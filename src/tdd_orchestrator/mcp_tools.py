"""Custom MCP tools for TDD orchestrator feature management.

These tools allow Claude to query and update task state during TDD execution.
The tools are registered as an in-process MCP server for minimal latency.
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server, tool


@tool(
    "task_get_next",
    "Get the next pending task to implement. Returns task details or 'No pending tasks' if queue is empty.",
    {},  # No input parameters
)
async def task_get_next(args: dict[str, Any]) -> dict[str, Any]:
    """Query database for next pending task in priority order."""
    # Import here to avoid circular deps
    from .database import get_db

    db = await get_db()
    task = await db.get_next_pending_task()

    if not task:
        return {"content": [{"type": "text", "text": "No pending tasks"}]}

    return {"content": [{"type": "text", "text": json.dumps(task, indent=2, default=str)}]}


@tool(
    "task_mark_passing",
    "Mark a task as passing all tests. Use after tests pass.",
    {"task_key": str},  # Simple schema: parameter name -> type
)
async def task_mark_passing(args: dict[str, Any]) -> dict[str, Any]:
    """Update task status to 'passing'."""
    from .database import get_db

    task_key = args.get("task_key")
    if not task_key:
        return {
            "content": [{"type": "text", "text": "Error: task_key required"}],
            "is_error": True,
        }

    db = await get_db()
    success = await db.mark_task_passing(task_key)

    if success:
        return {"content": [{"type": "text", "text": f"Task {task_key} marked as passing"}]}
    else:
        return {
            "content": [{"type": "text", "text": f"Error: Task {task_key} not found"}],
            "is_error": True,
        }


@tool(
    "task_mark_failing",
    "Mark a task as failing tests. Use when tests fail and need retry or investigation.",
    {"task_key": str, "reason": str},
)
async def task_mark_failing(args: dict[str, Any]) -> dict[str, Any]:
    """Update task status to 'failing' with reason."""
    from .database import get_db

    task_key = args.get("task_key")
    reason = args.get("reason", "")

    if not task_key:
        return {
            "content": [{"type": "text", "text": "Error: task_key required"}],
            "is_error": True,
        }

    db = await get_db()
    success = await db.mark_task_failing(task_key, reason)

    if success:
        return {
            "content": [{"type": "text", "text": f"Task {task_key} marked as failing: {reason}"}]
        }
    else:
        return {
            "content": [{"type": "text", "text": f"Error: Task {task_key} not found"}],
            "is_error": True,
        }


@tool(
    "task_get_stats",
    "Get summary statistics of all tasks by status.",
    {},  # No input parameters
)
async def task_get_stats(args: dict[str, Any]) -> dict[str, Any]:
    """Return task counts by status."""
    from .database import get_db

    db = await get_db()
    stats = await db.get_stats()

    return {"content": [{"type": "text", "text": json.dumps(stats, indent=2)}]}


@tool(
    "task_get_by_key",
    "Get a specific task by its key.",
    {"task_key": str},
)
async def task_get_by_key(args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve task details by key."""
    from .database import get_db

    task_key = args.get("task_key")
    if not task_key:
        return {
            "content": [{"type": "text", "text": "Error: task_key required"}],
            "is_error": True,
        }

    db = await get_db()
    task = await db.get_task_by_key(task_key)

    if not task:
        return {
            "content": [{"type": "text", "text": f"Task {task_key} not found"}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": json.dumps(task, indent=2, default=str)}]}


# Collect all tools for export
ALL_TOOLS: list[SdkMcpTool[Any]] = [
    task_get_next,
    task_mark_passing,
    task_mark_failing,
    task_get_stats,
    task_get_by_key,
]


def create_orchestrator_mcp_server(
    name: str = "tdd-orchestrator",
    version: str = "1.0.0",
) -> McpSdkServerConfig:
    """Create MCP server with orchestrator tools.

    Args:
        name: Server name for identification
        version: Server version string

    Returns:
        McpSdkServerConfig ready for use with ClaudeAgentOptions
    """
    return create_sdk_mcp_server(
        name=name,
        version=version,
        tools=ALL_TOOLS,
    )
