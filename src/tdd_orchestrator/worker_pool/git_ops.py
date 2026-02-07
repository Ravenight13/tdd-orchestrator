"""Git operations for TDD pipeline stages.

Provides helper functions for committing stage results,
squashing WIP commits, and running ruff auto-fixes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_ruff_fix(impl_file: str, task_key: str, base_dir: Path) -> bool:
    """Run ruff --fix on implementation file to auto-fix lint issues.

    Args:
        impl_file: Path to implementation file.
        task_key: Task key for logging.
        base_dir: Root directory for file path resolution.

    Returns:
        True if ruff ran successfully, False otherwise.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "ruff",
            "check",
            "--fix",
            impl_file,
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        logger.info("[%s] Ran ruff --fix on %s", task_key, impl_file)
        return True
    except Exception as e:
        logger.warning("[%s] ruff --fix failed: %s", task_key, e)
        return False


async def squash_wip_commits(task_key: str, base_dir: Path) -> bool:
    """Squash all WIP commits for this task into a single commit.

    Finds all commits with 'wip({task_key}):' prefix and squashes them
    into a single feat commit.

    Args:
        task_key: Task key to match WIP commits (e.g., 'HTMX-TDD-02-04').
        base_dir: Root directory for git operations.

    Returns:
        True if squash succeeded, False otherwise.
    """
    try:
        # Count WIP commits for this task
        proc = await asyncio.create_subprocess_exec(
            "git",
            "log",
            "--oneline",
            "--grep",
            f"wip({task_key}):",
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        wip_commits = stdout.decode().strip().split("\n")
        wip_count = len([c for c in wip_commits if c])

        if wip_count < 2:
            logger.debug("[%s] Only %d WIP commits, skipping squash", task_key, wip_count)
            return True

        # Soft reset to before first WIP commit
        proc = await asyncio.create_subprocess_exec(
            "git",
            "reset",
            "--soft",
            f"HEAD~{wip_count}",
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        if proc.returncode != 0:
            logger.warning("[%s] git reset failed, aborting squash", task_key)
            return False

        # Create single squashed commit
        message = (
            f"feat({task_key}): complete (squashed from {wip_count} WIP commits)"
            "\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        )
        proc = await asyncio.create_subprocess_exec(
            "git",
            "commit",
            "--no-verify",
            "-m",
            message,
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        if proc.returncode == 0:
            logger.info("[%s] Squashed %d WIP commits into one", task_key, wip_count)
            return True
        else:
            logger.warning("[%s] squash commit failed", task_key)
            return False

    except Exception as e:
        logger.warning("[%s] WIP squash failed: %s", task_key, e)
        return False


async def commit_stage(task_key: str, stage: str, message: str, base_dir: Path) -> bool:
    """Commit current changes for a TDD stage.

    Creates a WIP commit after each successful stage to preserve work
    incrementally, preventing loss of progress if later stages fail.

    Args:
        task_key: JIRA task key (e.g., 'VEA-123').
        stage: Stage name for logging (e.g., 'RED', 'GREEN').
        message: Commit message.
        base_dir: Root directory for git operations.

    Returns:
        True if commit succeeded, False otherwise.
    """
    try:
        # Stage all changes
        proc = await asyncio.create_subprocess_exec(
            "git",
            "add",
            "-A",
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        # Commit with message and co-author
        # Use --no-verify for TDD WIP commits since:
        # 1. Partial code intentionally doesn't pass all checks
        # 2. RED stage has failing tests by design
        # 3. Actual verification happens in VERIFY stage
        full_message = f"{message}\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
        proc = await asyncio.create_subprocess_exec(
            "git",
            "commit",
            "--no-verify",
            "-m",
            full_message,
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        if proc.returncode == 0:
            logger.info("[%s] Committed %s stage", task_key, stage)
            return True
        else:
            # Non-zero return may mean no changes to commit (not an error)
            stderr = await proc.stderr.read() if proc.stderr else b""
            if b"nothing to commit" in stderr:
                logger.debug("[%s] No changes to commit for %s stage", task_key, stage)
                return True
            logger.warning(
                "[%s] Git commit returned %d for %s stage",
                task_key,
                proc.returncode,
                stage,
            )
            return False
    except Exception as e:
        logger.warning("[%s] Failed to commit %s stage: %s", task_key, stage, e)
        return False
