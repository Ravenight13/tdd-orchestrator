"""Merge coordination for parallel worker branches.

Handles merging worker branches back to main at phase boundaries,
with conflict detection and Slack notification for human review.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from .git_coordinator import GitCoordinator

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of a merge operation."""

    branch: str
    success: bool
    commit_hash: str | None = None
    conflict_files: list[str] | None = None
    error_message: str | None = None


class SlackNotifier:
    """Sends notifications to Slack for merge conflicts."""

    def __init__(self, webhook_url: str | None = None):
        """Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL. If None, reads from SLACK_WEBHOOK_URL env var.
        """
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")

    async def notify_conflict(
        self,
        branch: str,
        conflict_files: list[str],
        phase: int,
        task_key: str,
    ) -> bool:
        """Send merge conflict notification to Slack.

        Args:
            branch: Branch that failed to merge.
            conflict_files: List of files with conflicts.
            phase: Phase number where conflict occurred.
            task_key: Task key associated with the branch.

        Returns:
            True if notification sent successfully.
        """
        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not configured, skipping notification")
            return False

        # Limit displayed files to prevent message overflow
        files_display = conflict_files[:10]
        files_text = "\n".join(files_display)
        if len(conflict_files) > 10:
            files_text += f"\n... and {len(conflict_files) - 10} more"

        message = {
            "text": "Merge Conflict Detected",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "Merge Conflict - Human Review Required",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Branch:*\n`{branch}`"},
                        {"type": "mrkdwn", "text": f"*Task:*\n`{task_key}`"},
                        {"type": "mrkdwn", "text": f"*Phase:*\n{phase}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*Conflicts:*\n{len(conflict_files)} file(s)",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Conflicting Files:*\n```\n{files_text}\n```",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Run `git status` to review conflicts and resolve manually.",
                        }
                    ],
                },
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=message,
                    timeout=10.0,
                )
                response.raise_for_status()
                logger.info("Slack notification sent for conflict on %s", branch)
                return True
        except httpx.HTTPStatusError as e:
            logger.error("Slack API error: %s", e.response.status_code)
            return False
        except httpx.RequestError as e:
            logger.error("Failed to send Slack notification: %s", e)
            return False


class MergeCoordinator:
    """Coordinates merging of worker branches at phase boundaries.

    Merges are performed sequentially with --no-ff to preserve history.
    On conflict, stops immediately and notifies via Slack.
    """

    def __init__(
        self,
        base_dir: Path,
        slack_webhook_url: str | None = None,
    ):
        """Initialize MergeCoordinator.

        Args:
            base_dir: Root directory of the Git repository.
            slack_webhook_url: Optional Slack webhook URL for notifications.
        """
        self.base_dir = base_dir
        self.git = GitCoordinator(base_dir)
        self.slack = SlackNotifier(slack_webhook_url)
        self._merge_lock = asyncio.Lock()

    async def merge_phase_branches(
        self,
        phase: int | None,
        branches: list[tuple[str, str]],  # [(branch_name, task_key), ...]
        target_branch: str = "main",
    ) -> list[MergeResult]:
        """Merge all worker branches for a completed phase.

        Merges are performed sequentially to detect conflicts early.
        On first conflict, stops and notifies for human review.

        Args:
            phase: Phase number being merged.
            branches: List of (branch_name, task_key) tuples to merge.
            target_branch: Branch to merge into.

        Returns:
            List of MergeResult for each branch.
        """
        results: list[MergeResult] = []

        async with self._merge_lock:
            # Checkout target branch
            await self.git.checkout(target_branch)

            for branch_name, task_key in branches:
                result = await self._merge_single_branch(
                    branch_name, task_key, phase, target_branch
                )
                results.append(result)

                # Stop on first conflict (require 100% success)
                if not result.success:
                    logger.error(
                        "Merge conflict on %s - stopping phase %s merge",
                        branch_name,
                        phase if phase is not None else "all",
                    )
                    break

        return results

    async def _merge_single_branch(
        self,
        branch_name: str,
        task_key: str,
        phase: int | None,
        target_branch: str,
    ) -> MergeResult:
        """Merge a single worker branch.

        Args:
            branch_name: Branch to merge.
            task_key: Task key for the branch.
            phase: Phase number.
            target_branch: Branch to merge into.

        Returns:
            MergeResult with success status.
        """
        try:
            # Attempt merge with --no-ff
            merge_msg = f"Merge {branch_name}: Phase {phase} task {task_key}"

            proc = await asyncio.create_subprocess_exec(
                "git",
                "merge",
                "--no-ff",
                "--no-verify",
                "-m",
                merge_msg,
                branch_name,
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                # Get merge commit hash
                hash_proc = await asyncio.create_subprocess_exec(
                    "git",
                    "rev-parse",
                    "HEAD",
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                )
                hash_out, _ = await hash_proc.communicate()
                commit_hash = hash_out.decode().strip()

                # Delete merged branch
                await self.git.delete_branch(branch_name)

                logger.info("Merged %s -> %s (%s)", branch_name, target_branch, commit_hash[:8])
                return MergeResult(
                    branch=branch_name,
                    success=True,
                    commit_hash=commit_hash,
                )

            # Merge failed - check for conflicts
            conflict_files = await self._get_conflict_files()

            if conflict_files:
                # Abort the merge
                await asyncio.create_subprocess_exec(
                    "git",
                    "merge",
                    "--abort",
                    cwd=self.base_dir,
                )

                # Send Slack notification
                if phase is not None:
                    await self.slack.notify_conflict(branch_name, conflict_files, phase, task_key)

                return MergeResult(
                    branch=branch_name,
                    success=False,
                    conflict_files=conflict_files,
                    error_message=f"Merge conflict in {len(conflict_files)} file(s)",
                )

            # Other merge error
            error_msg = stderr.decode() if stderr else "Unknown merge error"
            return MergeResult(
                branch=branch_name,
                success=False,
                error_message=error_msg,
            )

        except Exception as e:
            logger.exception("Failed to merge %s", branch_name)
            return MergeResult(
                branch=branch_name,
                success=False,
                error_message=str(e),
            )

    async def _get_conflict_files(self) -> list[str]:
        """Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts.
        """
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--name-only",
            "--diff-filter=U",
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if stdout:
            return stdout.decode().strip().split("\n")
        return []

    async def find_worker_branches(self, pattern: str = "worker-*/*") -> list[str]:
        """Find all worker branches matching pattern.

        Args:
            pattern: Glob pattern for branch names.

        Returns:
            List of matching branch names.
        """
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--list",
            pattern,
            cwd=self.base_dir,
            stdout=subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if stdout:
            return [b.strip().lstrip("* ") for b in stdout.decode().splitlines() if b.strip()]
        return []
