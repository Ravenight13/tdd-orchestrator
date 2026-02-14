"""Git branch coordination for parallel workers.

Manages isolated Git branches for each worker to prevent merge conflicts
during parallel task execution.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitCoordinator:
    """Coordinates Git operations for parallel workers.

    Each worker operates on an isolated branch: worker-{id}/{task-key}
    Branches are merged back to main at phase boundaries.
    """

    def __init__(self, base_dir: Path):
        """Initialize GitCoordinator.

        Args:
            base_dir: Root directory of the Git repository.
        """
        self.base_dir = base_dir
        self._lock = asyncio.Lock()

    async def create_worker_branch(
        self,
        worker_id: int,
        task_key: str,
        base_branch: str = "main",
        use_local: bool = False,
    ) -> str:
        """Create isolated branch for worker.

        Args:
            worker_id: Worker identifier.
            task_key: Task being worked on.
            base_branch: Branch to create from.
            use_local: If True, create from HEAD (current commit) for local testing.
                      If False (default), fetch and create from origin/{base_branch}.

        Returns:
            Name of created branch.
        """
        branch_name = f"worker-{worker_id}/{task_key}"

        async with self._lock:
            if use_local:
                # Create from current HEAD (for local testing)
                await self._run_git("checkout", "-b", branch_name)
            else:
                # Fetch latest from remote and create from origin
                await self._run_git("fetch", "origin", base_branch)
                await self._run_git("checkout", "-b", branch_name, f"origin/{base_branch}")

        logger.info("Created branch %s for worker %d", branch_name, worker_id)
        return branch_name

    async def create_feature_branch(
        self,
        branch_name: str,
        base_branch: str = "main",
        use_local: bool = False,
    ) -> str:
        """Create and checkout a feature branch.

        Unlike create_worker_branch(), this creates a top-level branch
        (no worker prefix) for the entire pipeline's work.

        Args:
            branch_name: Branch name (e.g., "feat/user-auth").
            base_branch: Branch to create from.
            use_local: If True, create from HEAD instead of origin.

        Returns:
            The branch name.

        Raises:
            subprocess.CalledProcessError: If branch already exists or
                git command fails.
        """
        async with self._lock:
            if use_local:
                await self._run_git("checkout", "-b", branch_name)
            else:
                await self._run_git("fetch", "origin", base_branch)
                await self._run_git("checkout", "-b", branch_name, f"origin/{base_branch}")
        logger.info("Created feature branch %s from %s", branch_name, base_branch)
        return branch_name

    async def commit_changes(
        self,
        message: str,
        files: list[str] | None = None,
    ) -> str:
        """Commit changes to current branch.

        Args:
            message: Commit message (should follow conventional commits).
            files: Specific files to commit, or None for all changes.

        Returns:
            Commit hash.

        Raises:
            ValueError: If there are no changes to commit.
        """
        if files:
            await self._run_git("add", *files)
        else:
            await self._run_git("add", "-A")

        # Check if there are changes to commit
        if not await self.has_uncommitted_changes():
            raise ValueError("No changes to commit")

        # Skip pre-commit hooks for automated commits
        await self._run_git("commit", "--no-verify", "-m", message)

        # Get commit hash
        result = await self._run_git("rev-parse", "HEAD")
        commit_hash = result.stdout.strip()

        logger.info("Committed: %s (%s)", message[:50], commit_hash[:8])
        return commit_hash

    async def push_branch(self, branch_name: str) -> None:
        """Push branch to remote.

        Args:
            branch_name: Branch to push.
        """
        await self._run_git("push", "-u", "origin", branch_name)
        logger.info("Pushed branch %s to remote", branch_name)

    async def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """Delete local branch.

        Args:
            branch_name: Branch to delete.
            force: Force delete even if not merged.
        """
        flag = "-D" if force else "-d"
        await self._run_git("branch", flag, branch_name)
        logger.info("Deleted branch %s", branch_name)

    async def checkout(self, branch_name: str) -> None:
        """Checkout a branch.

        Args:
            branch_name: Branch to checkout.
        """
        await self._run_git("checkout", branch_name)

    async def get_current_branch(self) -> str:
        """Get current branch name.

        Returns:
            Current branch name.
        """
        result = await self._run_git("branch", "--show-current")
        return result.stdout.strip()

    async def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes.

        Returns:
            True if there are uncommitted changes.
        """
        result = await self._run_git("status", "--porcelain")
        return bool(result.stdout.strip())

    async def rollback_to_main(self, branch_to_delete: str | None = None) -> None:
        """Rollback: checkout main and optionally delete worker branch.

        Args:
            branch_to_delete: Branch to delete after checkout.
        """
        await self.checkout("main")

        if branch_to_delete:
            await self.delete_branch(branch_to_delete, force=True)
            logger.info("Rolled back: deleted branch %s", branch_to_delete)

    async def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a git command asynchronously.

        Args:
            args: Git command arguments.

        Returns:
            Completed process result.

        Raises:
            subprocess.CalledProcessError: If git command fails.
        """
        cmd = ["git", *args]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        # After communicate(), returncode is always set (not None)
        returncode: int = proc.returncode if proc.returncode is not None else -1

        if returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise subprocess.CalledProcessError(returncode, cmd, stdout.decode(), error_msg)

        return subprocess.CompletedProcess(cmd, returncode, stdout.decode(), stderr.decode())
