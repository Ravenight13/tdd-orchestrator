"""Integration tests for GitCoordinator.

Tests Git branch operations, commit operations, and rollback functionality
for parallel worker coordination in the TDD Orchestrator.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tdd_orchestrator.git_coordinator import GitCoordinator


class TestGitBranchOperations:
    """Tests for Git branch creation, switching, and deletion."""

    async def test_create_worker_branch_local(self, git_repo: Path) -> None:
        """Creates branch from HEAD in local mode."""
        git = GitCoordinator(git_repo)

        branch = await git.create_worker_branch(1, "TDD-01", use_local=True)

        assert branch == "worker-1/TDD-01"
        current = await git.get_current_branch()
        assert current == branch

    async def test_create_worker_branch_naming(self, git_repo: Path) -> None:
        """Branch follows worker-{id}/{task_key} format."""
        git = GitCoordinator(git_repo)

        branch1 = await git.create_worker_branch(1, "TDD-01", use_local=True)
        await git.checkout("main")  # Switch back to create another branch

        branch2 = await git.create_worker_branch(2, "TDD-02", use_local=True)
        await git.checkout("main")

        branch3 = await git.create_worker_branch(3, "TASK-123", use_local=True)

        assert branch1 == "worker-1/TDD-01"
        assert branch2 == "worker-2/TDD-02"
        assert branch3 == "worker-3/TASK-123"

    async def test_get_current_branch(self, git_repo: Path) -> None:
        """Returns correct branch name."""
        git = GitCoordinator(git_repo)

        # Initially on main
        current = await git.get_current_branch()
        assert current == "main"

        # After creating worker branch
        await git.create_worker_branch(1, "TDD-01", use_local=True)
        current = await git.get_current_branch()
        assert current == "worker-1/TDD-01"

    async def test_switch_branch(self, git_repo: Path) -> None:
        """Can switch between branches."""
        git = GitCoordinator(git_repo)

        # Create two branches
        await git.create_worker_branch(1, "TDD-01", use_local=True)
        await git.checkout("main")
        await git.create_worker_branch(2, "TDD-02", use_local=True)

        # Switch between them
        await git.checkout("worker-1/TDD-01")
        current = await git.get_current_branch()
        assert current == "worker-1/TDD-01"

        await git.checkout("main")
        current = await git.get_current_branch()
        assert current == "main"

        await git.checkout("worker-2/TDD-02")
        current = await git.get_current_branch()
        assert current == "worker-2/TDD-02"

    async def test_branch_exists(self, git_repo: Path) -> None:
        """Detects existing branches via get_current_branch after checkout."""
        git = GitCoordinator(git_repo)

        # Create branch
        await git.create_worker_branch(1, "TDD-01", use_local=True)

        # Verify we can check out to it (implies it exists)
        await git.checkout("main")
        await git.checkout("worker-1/TDD-01")
        current = await git.get_current_branch()
        assert current == "worker-1/TDD-01"

    async def test_delete_branch(self, git_repo: Path) -> None:
        """Can delete branches."""
        git = GitCoordinator(git_repo)

        # Create and delete branch
        branch = await git.create_worker_branch(1, "TDD-01", use_local=True)
        await git.checkout("main")
        await git.delete_branch(branch, force=True)

        # Verify deletion by trying to checkout (should fail)
        with pytest.raises(subprocess.CalledProcessError):
            await git.checkout(branch)


class TestGitCommitOperations:
    """Tests for commit operations and change detection."""

    async def test_commit_changes_with_message(self, git_repo: Path) -> None:
        """Commits staged changes with provided message."""
        git = GitCoordinator(git_repo)
        await git.create_worker_branch(1, "TDD-01", use_local=True)
        (git_repo / "new_file.py").write_text("# New")

        commit_hash = await git.commit_changes("feat(TDD-01): Add new file")

        assert len(commit_hash) == 40  # Full SHA

    async def test_commit_no_changes_raises(self, git_repo: Path) -> None:
        """Commit with no changes raises ValueError."""
        git = GitCoordinator(git_repo)
        await git.create_worker_branch(1, "TDD-01", use_local=True)

        with pytest.raises(ValueError, match="No changes"):
            await git.commit_changes("Empty commit")

    async def test_has_uncommitted_changes_detects_new_file(self, git_repo: Path) -> None:
        """Detects uncommitted new files."""
        git = GitCoordinator(git_repo)
        (git_repo / "uncommitted.py").write_text("# Uncommitted")

        has_changes = await git.has_uncommitted_changes()

        assert has_changes is True

    async def test_has_uncommitted_changes_detects_modified_file(self, git_repo: Path) -> None:
        """Detects modifications to tracked files."""
        git = GitCoordinator(git_repo)

        # Modify existing file
        (git_repo / "README.md").write_text("# Modified Test Repository\n")

        has_changes = await git.has_uncommitted_changes()

        assert has_changes is True


class TestGitRollbackOperations:
    """Tests for rollback to main and branch cleanup."""

    async def test_rollback_deletes_branch(self, git_repo: Path) -> None:
        """Rollback returns to main and deletes worker branch."""
        git = GitCoordinator(git_repo)
        branch = await git.create_worker_branch(1, "TDD-01", use_local=True)

        await git.rollback_to_main(branch)

        current = await git.get_current_branch()
        assert current == "main"

        # Verify branch is deleted
        with pytest.raises(subprocess.CalledProcessError):
            await git.checkout(branch)

    async def test_rollback_preserves_main(self, git_repo: Path) -> None:
        """Main branch unchanged after rollback."""
        git = GitCoordinator(git_repo)

        # Get main commit hash before operations
        result = await git._run_git("rev-parse", "HEAD")
        main_commit = result.stdout.strip()

        # Create worker branch, make changes
        await git.create_worker_branch(1, "TDD-01", use_local=True)
        (git_repo / "test_file.py").write_text("# Test")
        await git.commit_changes("feat(TDD-01): Add test file")

        # Rollback
        await git.rollback_to_main("worker-1/TDD-01")

        # Verify main is unchanged
        result = await git._run_git("rev-parse", "HEAD")
        assert result.stdout.strip() == main_commit
