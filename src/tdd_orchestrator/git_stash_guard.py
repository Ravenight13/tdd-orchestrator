"""Git stash guard for rollback protection.

Provides automatic git stash/restore protection around task execution
to prevent working tree corruption when tasks fail.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)


@dataclass
class StashOperation:
    """Record of a git stash operation for audit logging.

    Attributes:
        task_key: JIRA task key (e.g., TDD-042).
        operation: Type of operation ('create', 'drop', 'pop', 'skip').
        success: Whether the operation succeeded.
        stash_id: Git stash identifier (e.g., 'stash@{0}').
        error_message: Error message if operation failed.
        timestamp: When the operation occurred.
    """

    task_key: str
    operation: str  # 'create', 'drop', 'pop', 'skip'
    success: bool
    stash_id: str | None
    error_message: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GitStashGuard:
    """Async context manager for git stash/restore protection.

    Automatically stashes working tree before task execution
    and restores on failure.

    Usage:
        async with GitStashGuard(task_key, base_dir) as guard:
            # Execute task - if exception raised, stash will be restored
            await run_tdd_pipeline(task)
        # On success: stash dropped
        # On exception: working tree restored to pre-task state

    With preserve_on_failure=True (default):
        async with GitStashGuard(task_key, base_dir, preserve_on_failure=True) as guard:
            success = await run_tdd_pipeline(task)
            guard.mark_result(success)
        # On success: stash dropped
        # On failure: working tree preserved for inspection, stash dropped

    Attributes:
        task_key: JIRA task key for the current task.
        base_dir: Root directory of the Git repository.
        preserve_on_failure: If True, preserve working tree on failure for inspection.
        stash_id: Git stash identifier (set after stash creation).
        had_changes: Whether there were changes to stash.
        operations: Log of all stash operations for audit trail.
    """

    task_key: str
    base_dir: Path
    preserve_on_failure: bool = True
    stash_id: str | None = field(default=None, init=False)
    had_changes: bool = field(default=False, init=False)
    operations: list[StashOperation] = field(default_factory=list, init=False)
    _success: bool = field(default=True, init=False)

    async def __aenter__(self) -> "GitStashGuard":
        """Enter context: create stash if there are changes.

        Returns:
            Self for use in context.
        """
        self.had_changes = await self._has_changes()

        if self.had_changes:
            await self._create_stash()
            logger.info(
                "GitStashGuard: Created stash for task %s (stash_id=%s)",
                self.task_key,
                self.stash_id,
            )
        else:
            self._log_operation("skip", success=True)
            logger.debug(
                "GitStashGuard: No changes to stash for task %s",
                self.task_key,
            )

        return self

    def mark_result(self, success: bool) -> None:
        """Mark the pipeline result for preserve_on_failure logic.

        Call this before exiting the context manager to indicate
        whether the pipeline succeeded or failed.

        Args:
            success: True if pipeline succeeded, False if it failed.
        """
        self._success = success

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Exit context: drop stash on success, handle failure based on mode.

        Args:
            exc_type: Exception type if raised.
            exc_val: Exception value if raised.
            exc_tb: Exception traceback if raised.

        Returns:
            False to propagate exceptions, never suppresses.

        Behavior:
            - If preserve_on_failure=True AND pipeline failed:
              Preserve working tree for inspection, just drop stash.
            - If preserve_on_failure=False (legacy):
              Restore stash on exception (destroy working tree).
            - On success: drop stash (current behavior).
        """
        if not self.had_changes:
            # No stash was created, nothing to do
            return False

        # Determine if pipeline failed (exception OR marked failure)
        pipeline_failed = exc_type is not None or not self._success

        if pipeline_failed:
            if self.preserve_on_failure:
                # Preserve working tree for inspection
                logger.warning(
                    "GitStashGuard: Task %s failed, preserving failure state for inspection",
                    self.task_key,
                )
                await self._drop_stash()
            else:
                # Legacy mode: restore working tree to pre-task state
                exc_name = exc_type.__name__ if exc_type else "marked failure"
                logger.warning(
                    "GitStashGuard: Task %s failed (%s), restoring stash",
                    self.task_key,
                    exc_name,
                )
                await self._restore_stash()
        else:
            # Success: drop the stash (no longer needed)
            await self._drop_stash()
            logger.info(
                "GitStashGuard: Task %s succeeded, dropped stash",
                self.task_key,
            )

        # Never suppress exceptions
        return False

    async def _run_git_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Execute a git command asynchronously.

        Args:
            args: Git command arguments (without 'git' prefix).

        Returns:
            Completed process with stdout/stderr.

        Raises:
            subprocess.CalledProcessError: If command fails.
        """
        cmd = ["git", *args]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        returncode: int = proc.returncode if proc.returncode is not None else -1

        if returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise subprocess.CalledProcessError(returncode, cmd, stdout.decode(), error_msg)

        return subprocess.CompletedProcess(cmd, returncode, stdout.decode(), stderr.decode())

    async def _has_changes(self) -> bool:
        """Check if working tree has uncommitted changes.

        Returns:
            True if there are staged, unstaged, or untracked changes.
        """
        result = await self._run_git_command("status", "--porcelain")
        return bool(result.stdout.strip())

    async def _create_stash(self) -> None:
        """Create a stash with all changes including untracked files.

        Creates stash with message: 'pre-task-{task_key}'
        Includes untracked files via -u flag.
        """
        stash_message = f"pre-task-{self.task_key}"

        try:
            await self._run_git_command("stash", "push", "-u", "-m", stash_message)
            self.stash_id = "stash@{0}"
            self._log_operation("create", success=True)
        except subprocess.CalledProcessError as e:
            self._log_operation("create", success=False, error_message=str(e))
            raise

    async def _drop_stash(self) -> None:
        """Drop the most recent stash (used on success).

        Discards the stash at stash@{0} since task completed successfully.
        """
        try:
            await self._run_git_command("stash", "drop", "stash@{0}")
            self._log_operation("drop", success=True)
        except subprocess.CalledProcessError as e:
            # Log but don't raise - stash drop failure isn't critical
            self._log_operation("drop", success=False, error_message=str(e))
            logger.warning(
                "GitStashGuard: Failed to drop stash for task %s: %s",
                self.task_key,
                e,
            )

    async def _restore_stash(self) -> None:
        """Restore working tree to pre-task state (used on failure).

        Performs:
        1. git reset --hard HEAD (discard all working tree changes)
        2. git stash pop stash@{0} (restore pre-task state)

        Handles merge conflicts by using --theirs strategy.
        """
        try:
            # First, discard all working tree changes from the failed task
            await self._run_git_command("reset", "--hard", "HEAD")

            # Clean untracked files created during failed task
            await self._run_git_command("clean", "-fd")

            # Now pop the stash to restore pre-task state
            await self._run_git_command("stash", "pop", "stash@{0}")
            self._log_operation("pop", success=True)

        except subprocess.CalledProcessError as e:
            error_str = str(e)

            # Check if it's a merge conflict
            if "CONFLICT" in error_str or "conflict" in error_str.lower():
                logger.warning(
                    "GitStashGuard: Merge conflict during stash pop for task %s, "
                    "attempting --theirs resolution",
                    self.task_key,
                )
                await self._resolve_stash_conflicts()
            else:
                self._log_operation("pop", success=False, error_message=error_str)
                logger.error(
                    "GitStashGuard: Failed to restore stash for task %s: %s",
                    self.task_key,
                    e,
                )
                raise

    async def _resolve_stash_conflicts(self) -> None:
        """Resolve merge conflicts during stash pop using --theirs strategy.

        Prefers the pre-task version (from stash) over any conflicting changes.
        """
        try:
            # Use checkout --theirs to prefer stash content
            await self._run_git_command("checkout", "--theirs", ".")

            # Stage the resolved files
            await self._run_git_command("add", "-A")

            # Reset to clean state (stash is already applied)
            await self._run_git_command("reset", "HEAD")

            self._log_operation(
                "pop", success=True, error_message="resolved conflicts with --theirs"
            )
            logger.info(
                "GitStashGuard: Resolved stash conflicts for task %s using --theirs",
                self.task_key,
            )
        except subprocess.CalledProcessError as e:
            self._log_operation(
                "pop", success=False, error_message=f"conflict resolution failed: {e}"
            )
            logger.error(
                "GitStashGuard: Failed to resolve stash conflicts for task %s: %s",
                self.task_key,
                e,
            )
            raise

    def _log_operation(
        self,
        operation: str,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Log a stash operation for audit trail.

        Args:
            operation: Operation type ('create', 'drop', 'pop', 'skip').
            success: Whether operation succeeded.
            error_message: Error message if failed.
        """
        op = StashOperation(
            task_key=self.task_key,
            operation=operation,
            success=success,
            stash_id=self.stash_id,
            error_message=error_message,
        )
        self.operations.append(op)

    def get_operations(self) -> list[StashOperation]:
        """Get all operations performed by this guard.

        Returns:
            List of StashOperation records.
        """
        return self.operations.copy()

    async def persist_operations(self, db: "OrchestratorDB", task_id: int) -> int:
        """Persist all stash operations to the database audit log.

        Should be called after the context manager exits to record
        all operations for audit trail and debugging.

        Args:
            db: Database connection to use.
            task_id: Database ID of the task (not task_key).

        Returns:
            Number of operations persisted.
        """
        count = 0
        for op in self.operations:
            await db.log_stash_operation(
                task_id=task_id,
                stash_id=op.stash_id,
                operation=op.operation,
                success=op.success,
                error_message=op.error_message,
            )
            count += 1

        if count > 0:
            logger.debug(
                "GitStashGuard: Persisted %d stash operations for task_id=%d",
                count,
                task_id,
            )

        return count
