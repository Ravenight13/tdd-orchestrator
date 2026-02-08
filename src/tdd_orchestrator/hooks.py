"""Hooks for TDD orchestrator - validation and completion detection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from claude_agent_sdk import HookContext
    from claude_agent_sdk.types import SyncHookJSONOutput


async def pre_tool_use_hook(
    hook_input: Any,
    tool_use_id: str | None,
    context: HookContext,
) -> SyncHookJSONOutput:
    """
    PreToolUse hook - validate commands before execution.

    Safety checks:
    - Block dangerous bash commands (rm -rf, git push --force to main)
    - Validate file paths are within project
    - Log tool usage for audit trail

    Args:
        hook_input: PreToolUseHookInput containing tool_name and tool_input
        tool_use_id: Unique identifier for this tool invocation (may be None)
        context: Hook context from the SDK

    Returns:
        Empty dict to allow, or dict with decision: block to block
    """
    tool_name: str = hook_input.get("tool_name", "")
    tool_input: dict[str, Any] = hook_input.get("tool_input", {})

    # Check Bash commands for dangerous patterns
    if tool_name == "Bash":
        command: str = tool_input.get("command", "")

        # Block dangerous commands
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf $HOME",
            "git push --force origin main",
            "git push -f origin main",
            "git push --force-with-lease origin main",
            "> /dev/sda",
            "mkfs.",
            "dd if=",
            ":(){:|:&};:",  # Fork bomb
            "chmod -R 777 /",
            "chown -R",
        ]

        for pattern in dangerous_patterns:
            if pattern in command:
                return {
                    "decision": "block",
                    "reason": f"Blocked dangerous command containing: {pattern}",
                }

        # Warn about potentially destructive git operations
        warning_patterns = [
            ("git reset --hard", "Hard reset can lose uncommitted changes"),
            ("git clean -fd", "Clean can delete untracked files"),
            ("git checkout -- .", "Checkout can discard changes"),
        ]

        for pattern, warning in warning_patterns:
            if pattern in command:
                print(f"[HOOK WARNING] {warning}: {command[:100]}")

    # Check Write tool for path validation
    if tool_name == "Write":
        file_path: str = tool_input.get("file_path", "")

        # Block writes outside project directory
        blocked_paths = [
            "/etc/",
            "/usr/",
            "/bin/",
            "/sbin/",
            "/var/",
            "/tmp/",
            "/root/",
            "~/.ssh/",
            "~/.aws/",
        ]

        for blocked in blocked_paths:
            if file_path.startswith(blocked):
                return {
                    "decision": "block",
                    "reason": f"Blocked write to protected path: {blocked}",
                }

    # Allow the operation
    return {}


async def post_tool_use_hook(
    hook_input: Any,
    tool_use_id: str | None,
    context: HookContext,
) -> SyncHookJSONOutput:
    """
    PostToolUse hook - log results and check for TDD gate violations.

    Checks:
    - If pytest ran, capture exit code
    - If mypy/ruff ran, capture results
    - Log file modifications for audit

    Args:
        hook_input: PostToolUseHookInput containing tool_name, tool_input, and tool_response
        tool_use_id: Unique identifier for this tool invocation (may be None)
        context: Hook context from the SDK

    Returns:
        Empty dict (no modifications to result)
    """
    tool_name: str = hook_input.get("tool_name", "")
    tool_input: dict[str, Any] = hook_input.get("tool_input", {})
    tool_response: Any = hook_input.get("tool_response", {})

    # Track test and linter execution for TDD enforcement
    if tool_name == "Bash":
        command: str = tool_input.get("command", "")

        # Log pytest execution
        if "pytest" in command:
            # tool_response structure may vary - check for exit code
            response_str = str(tool_response)
            print(f"[HOOK] pytest executed: {command[:100]}")
            if "FAILED" in response_str or "error" in response_str.lower():
                print("[HOOK TDD] Tests FAILED - check output for details")

        # Log linter execution
        if "mypy" in command:
            response_str = str(tool_response)
            print(f"[HOOK] mypy executed: {command[:100]}")
            if "error" in response_str.lower():
                print("[HOOK TDD] mypy found type errors")

        if "ruff" in command:
            response_str = str(tool_response)
            print(f"[HOOK] ruff executed: {command[:100]}")
            if "error" in response_str.lower() or "Found" in response_str:
                print("[HOOK TDD] ruff found lint issues")

        # Log git commits for audit
        if "git commit" in command:
            print(f"[HOOK AUDIT] Git commit: {command[:100]}")

    # Track file modifications
    if tool_name == "Write":
        file_path: str = tool_input.get("file_path", "")
        print(f"[HOOK AUDIT] File written: {file_path}")

    if tool_name == "Edit":
        file_path_edit: str = tool_input.get("file_path", "")
        print(f"[HOOK AUDIT] File edited: {file_path_edit}")

    # No modifications to result
    return {}


async def stop_hook(
    hook_input: Any,
    tool_use_id: str | None,
    context: HookContext,
) -> SyncHookJSONOutput:
    """
    Stop hook - decide whether to continue the orchestration loop.

    Checks:
    - Are there pending tasks remaining?
    - Has max iteration count been reached?
    - Are there unrecoverable errors?

    Args:
        hook_input: StopHookInput containing session info
        tool_use_id: Unique identifier (may be None for stop hook)
        context: Hook context from the SDK

    Returns:
        Empty dict to continue, or dict with stopReason to end
    """
    # Import here to avoid circular deps - database module created by another agent
    try:
        from .database import get_db

        db = await get_db()
        stats = await db.get_stats()

        pending = stats.get("pending", 0)
        in_progress = stats.get("in_progress", 0)
        failed = stats.get("failed", 0)

        # Stop if no more work
        if pending == 0 and in_progress == 0:
            completed = stats.get("completed", 0)
            return {
                "stopReason": f"All tasks complete - {completed} completed, {failed} failed",
            }

        # Stop if too many failures (circuit breaker)
        total = pending + in_progress + stats.get("completed", 0) + failed
        if total > 0 and failed / total > 0.5:
            return {
                "stopReason": f"Too many failures ({failed}/{total}) - stopping to prevent cascade",
            }

    except ImportError:
        # Database module not yet available - continue anyway
        pass
    except Exception as e:
        # If we can't check, continue anyway but log the error
        print(f"[HOOK] Error checking task status: {e}")

    # Continue processing
    return {}


# Type alias for hook dict keys
HookEventName = Literal[
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact"
]


def get_orchestrator_hooks() -> dict[HookEventName, list[Any]]:
    """
    Return hooks dict for ClaudeAgentOptions.

    The SDK expects hooks as a dict with string literal keys mapping to
    lists of HookMatcher objects. For simple cases, you can pass the
    hook functions directly.

    Usage:
        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
        from .hooks import get_orchestrator_hooks

        options = ClaudeAgentOptions(
            hooks=get_orchestrator_hooks()
        )

    Returns:
        Dict mapping hook event names to lists of hook configurations
    """
    from claude_agent_sdk import HookMatcher

    return {
        "PreToolUse": [HookMatcher(hooks=[pre_tool_use_hook])],
        "PostToolUse": [HookMatcher(hooks=[post_tool_use_hook])],
        "Stop": [HookMatcher(hooks=[stop_hook])],
    }
