"""Progress file writer for real-time execution visibility.

This module provides human-readable progress file generation for the TDD
orchestrator, enabling monitoring and debugging without direct database access.

The progress file is updated after each task completion and contains:
- Run metadata (ID, start time, status)
- Summary statistics (total, completed, success rate, ETA)
- Active workers and current tasks
- Recently completed tasks
- Blocked/failed tasks with error reasons
- Per-worker statistics
- Invocation budget status
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import OrchestratorDB

logger = logging.getLogger(__name__)


@dataclass
class TaskStats:
    """Statistics about task execution status."""

    total: int = 0
    pending: int = 0
    in_progress: int = 0
    passing: int = 0
    complete: int = 0
    blocked: int = 0

    @property
    def finished(self) -> int:
        """Get count of finished tasks (complete + passing)."""
        return self.complete + self.passing

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        finished = self.finished
        if finished == 0:
            return 0.0
        failed = self.blocked
        total_done = finished + failed
        if total_done == 0:
            return 100.0
        return (finished / total_done) * 100.0


@dataclass
class ActiveWorker:
    """Information about an active worker."""

    worker_id: int
    task_key: str | None
    stage: str | None
    duration_seconds: float


@dataclass
class CompletedTask:
    """Information about a recently completed task."""

    task_key: str
    title: str
    duration_seconds: float
    completed_at: str


@dataclass
class BlockedTask:
    """Information about a blocked/failed task."""

    task_key: str
    title: str
    reason: str
    failed_at: str


@dataclass
class WorkerStatistics:
    """Statistics for a single worker."""

    worker_id: int
    completed: int = 0
    failed: int = 0
    invocations: int = 0


@dataclass
class ProgressFileWriter:
    """Generates human-readable progress markdown file.

    Updates after each task completion to provide real-time
    visibility into orchestrator execution status.

    Attributes:
        db: Database instance for querying task status.
        output_path: Path to write the progress markdown file.
        run_id: Current execution run ID (set after run starts).
        start_time: When the execution run started.
    """

    db: OrchestratorDB
    output_path: Path
    run_id: int | None = None
    start_time: datetime | None = None
    _completion_times: list[float] = field(default_factory=list)

    async def update(self) -> None:
        """Update the progress file with current status.

        Queries the database for current execution state and writes
        a formatted markdown file with all progress sections.
        """
        if self.run_id is None:
            logger.warning("Cannot update progress file: run_id not set")
            return

        try:
            # Gather all data in parallel-ish manner
            stats = await self._get_task_stats()
            active_workers = await self._get_active_workers()
            recent_completions = await self._get_recent_completions()
            blocked_tasks = await self._get_blocked_tasks()
            worker_stats = await self._get_worker_statistics()
            budget_info = await self._get_budget_info()

            # Calculate ETA
            eta_str = self._calculate_eta(stats)

            # Determine run status
            status = await self._get_run_status()

            # Generate markdown content
            content = self._generate_markdown(
                stats=stats,
                active_workers=active_workers,
                recent_completions=recent_completions,
                blocked_tasks=blocked_tasks,
                worker_stats=worker_stats,
                budget_info=budget_info,
                eta_str=eta_str,
                status=status,
            )

            # Write to file
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(content)

            logger.debug("Progress file updated: %s", self.output_path)

        except Exception as e:
            logger.error("Failed to update progress file: %s", e)

    async def _get_task_stats(self) -> TaskStats:
        """Query database for task counts by status."""
        db_stats = await self.db.get_stats()

        return TaskStats(
            total=sum(db_stats.values()),
            pending=db_stats.get("pending", 0),
            in_progress=db_stats.get("in_progress", 0),
            passing=db_stats.get("passing", 0),
            complete=db_stats.get("complete", 0),
            blocked=db_stats.get("blocked", 0),
        )

    async def _get_active_workers(self) -> list[ActiveWorker]:
        """Get currently running tasks with their workers."""
        results: list[ActiveWorker] = []

        # Query workers table joined with tasks
        rows = await self.db.execute_query(
            """
            SELECT
                w.worker_id,
                t.task_key,
                t.claimed_at,
                a.stage
            FROM workers w
            LEFT JOIN tasks t ON w.current_task_id = t.id
            LEFT JOIN (
                SELECT task_id, stage, MAX(id) as max_id
                FROM attempts
                GROUP BY task_id
            ) latest ON latest.task_id = t.id
            LEFT JOIN attempts a ON a.id = latest.max_id
            WHERE w.status = 'active'
            ORDER BY w.worker_id
            """
        )

        now = datetime.now()
        for row in rows:
            duration = 0.0
            if row.get("claimed_at"):
                try:
                    claimed_at = datetime.fromisoformat(row["claimed_at"])
                    duration = (now - claimed_at).total_seconds()
                except (ValueError, TypeError):
                    pass

            results.append(
                ActiveWorker(
                    worker_id=row["worker_id"],
                    task_key=row.get("task_key"),
                    stage=row.get("stage", "").upper() if row.get("stage") else None,
                    duration_seconds=duration,
                )
            )

        return results

    async def _get_recent_completions(self, limit: int = 5) -> list[CompletedTask]:
        """Get last N completed tasks."""
        results: list[CompletedTask] = []

        rows = await self.db.execute_query(
            """
            SELECT
                t.task_key,
                t.title,
                t.updated_at,
                tc.claimed_at,
                tc.released_at
            FROM tasks t
            LEFT JOIN task_claims tc ON tc.task_id = t.id AND tc.outcome = 'completed'
            WHERE t.status IN ('complete', 'passing')
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )

        for row in rows:
            duration = 0.0
            if row.get("claimed_at") and row.get("released_at"):
                try:
                    claimed = datetime.fromisoformat(row["claimed_at"])
                    released = datetime.fromisoformat(row["released_at"])
                    duration = (released - claimed).total_seconds()
                except (ValueError, TypeError):
                    pass

            # Track completion times for ETA calculation
            if duration > 0:
                self._completion_times.append(duration)
                # Keep only last 20 for rolling average
                self._completion_times = self._completion_times[-20:]

            completed_at = row.get("updated_at", "")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at)
                    completed_at = dt.strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    pass

            results.append(
                CompletedTask(
                    task_key=row["task_key"],
                    title=row.get("title", ""),
                    duration_seconds=duration,
                    completed_at=completed_at,
                )
            )

        return results

    async def _get_blocked_tasks(self) -> list[BlockedTask]:
        """Get failed tasks with error reasons."""
        results: list[BlockedTask] = []

        rows = await self.db.execute_query(
            """
            SELECT
                t.task_key,
                t.title,
                t.updated_at,
                a.error_message,
                av.message as ast_message,
                av.pattern as ast_pattern
            FROM tasks t
            LEFT JOIN (
                SELECT task_id, error_message, MAX(id) as max_id
                FROM attempts
                WHERE success = 0
                GROUP BY task_id
            ) latest_attempt ON latest_attempt.task_id = t.id
            LEFT JOIN attempts a ON a.id = latest_attempt.max_id
            LEFT JOIN ast_violations av ON av.task_id = t.id
            WHERE t.status = 'blocked'
            ORDER BY t.updated_at DESC
            """
        )

        for row in rows:
            # Determine failure reason
            reason = "Unknown error"
            if row.get("ast_pattern"):
                reason = f"{row['ast_pattern']} (AST)"
            elif row.get("error_message"):
                reason = row["error_message"][:80]  # Truncate long messages

            failed_at = row.get("updated_at", "")
            if failed_at:
                try:
                    dt = datetime.fromisoformat(failed_at)
                    failed_at = dt.strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    pass

            results.append(
                BlockedTask(
                    task_key=row["task_key"],
                    title=row.get("title", ""),
                    reason=reason,
                    failed_at=failed_at,
                )
            )

        return results

    async def _get_worker_statistics(self) -> list[WorkerStatistics]:
        """Get per-worker completion and failure counts."""
        results: list[WorkerStatistics] = []

        rows = await self.db.execute_query(
            """
            SELECT
                w.worker_id,
                COUNT(CASE WHEN tc.outcome = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN tc.outcome = 'failed' THEN 1 END) as failed,
                (SELECT COUNT(*) FROM invocations i
                 WHERE i.worker_id = w.id AND i.run_id = ?) as invocations
            FROM workers w
            LEFT JOIN task_claims tc ON tc.worker_id = w.id
            GROUP BY w.worker_id
            ORDER BY w.worker_id
            """,
            (self.run_id,),
        )

        for row in rows:
            results.append(
                WorkerStatistics(
                    worker_id=row["worker_id"],
                    completed=row.get("completed", 0) or 0,
                    failed=row.get("failed", 0) or 0,
                    invocations=row.get("invocations", 0) or 0,
                )
            )

        return results

    async def _get_budget_info(self) -> dict[str, Any]:
        """Get invocation budget status."""
        count, limit, is_warning = await self.db.check_invocation_budget(self.run_id or 0)
        percentage = (count / limit * 100) if limit > 0 else 0

        return {
            "used": count,
            "limit": limit,
            "percentage": percentage,
            "is_warning": is_warning,
        }

    async def _get_run_status(self) -> str:
        """Get current run status."""
        if self.run_id is None:
            return "Unknown"

        rows = await self.db.execute_query(
            "SELECT status FROM execution_runs WHERE id = ?",
            (self.run_id,),
        )

        if rows:
            status = rows[0].get("status", "unknown")
            return status.capitalize()
        return "Unknown"

    def _calculate_eta(self, stats: TaskStats) -> str:
        """Estimate completion time based on average task duration.

        Args:
            stats: Current task statistics.

        Returns:
            Human-readable ETA string like "16:10:00 (~25 min)".
        """
        remaining = stats.pending + stats.in_progress
        if remaining == 0:
            return "Complete"

        # Use rolling average of completion times
        if not self._completion_times:
            return "Calculating..."

        avg_duration = sum(self._completion_times) / len(self._completion_times)
        estimated_seconds = avg_duration * remaining

        # Calculate ETA time
        eta_time = datetime.now() + timedelta(seconds=estimated_seconds)
        eta_formatted = eta_time.strftime("%H:%M:%S")

        # Format remaining time
        remaining_minutes = int(estimated_seconds / 60)
        if remaining_minutes < 1:
            time_str = "<1 min"
        elif remaining_minutes < 60:
            time_str = f"~{remaining_minutes} min"
        else:
            hours = remaining_minutes // 60
            mins = remaining_minutes % 60
            time_str = f"~{hours}h {mins}m"

        return f"{eta_formatted} ({time_str})"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted string like "2m 15s" or "45s".
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"

    def _generate_markdown(
        self,
        stats: TaskStats,
        active_workers: list[ActiveWorker],
        recent_completions: list[CompletedTask],
        blocked_tasks: list[BlockedTask],
        worker_stats: list[WorkerStatistics],
        budget_info: dict[str, Any],
        eta_str: str,
        status: str,
    ) -> str:
        """Generate the complete markdown content.

        Args:
            stats: Task statistics.
            active_workers: Currently active workers.
            recent_completions: Recently completed tasks.
            blocked_tasks: Failed/blocked tasks.
            worker_stats: Per-worker statistics.
            budget_info: Invocation budget status.
            eta_str: Estimated completion time string.
            status: Current run status.

        Returns:
            Complete markdown content for the progress file.
        """
        lines: list[str] = []

        # Header
        lines.append("# TDD Orchestrator Progress")
        lines.append("")
        lines.append(f"**Run ID**: {self.run_id}")
        if self.start_time:
            lines.append(f"**Started**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Status**: {status}")
        lines.append("")

        # Summary Table
        lines.append("## Summary")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Tasks | {stats.total} |")
        lines.append(f"| Completed | {stats.finished} |")
        lines.append(f"| Success Rate | {stats.success_rate:.0f}% |")
        lines.append(f"| Estimated Completion | {eta_str} |")
        lines.append("")

        # Active Workers
        lines.append("## Active Workers")
        if active_workers:
            lines.append("| Worker | Task | Stage | Duration |")
            lines.append("|--------|------|-------|----------|")
            for worker in active_workers:
                task = worker.task_key or "-"
                stage = worker.stage or "-"
                duration = (
                    self._format_duration(worker.duration_seconds) if worker.task_key else "-"
                )
                lines.append(f"| Worker {worker.worker_id} | {task} | {stage} | {duration} |")
        else:
            lines.append("*No active workers*")
        lines.append("")

        # Recently Completed
        lines.append("## Recently Completed (Last 5)")
        if recent_completions:
            lines.append("| Task | Title | Duration | Completed At |")
            lines.append("|------|-------|----------|--------------|")
            for completed in recent_completions:
                duration = (
                    self._format_duration(completed.duration_seconds)
                    if completed.duration_seconds > 0
                    else "-"
                )
                # Truncate long titles
                task_title = (
                    completed.title[:40] + "..." if len(completed.title) > 40 else completed.title
                )
                lines.append(
                    f"| {completed.task_key} | {task_title} | {duration} | {completed.completed_at} |"
                )
        else:
            lines.append("*No completed tasks yet*")
        lines.append("")

        # Blocked Tasks
        lines.append("## Blocked Tasks")
        if blocked_tasks:
            lines.append("| Task | Title | Reason | Failed At |")
            lines.append("|------|-------|--------|-----------|")
            for blocked in blocked_tasks:
                # Truncate long titles and reasons
                blocked_title = (
                    blocked.title[:30] + "..." if len(blocked.title) > 30 else blocked.title
                )
                blocked_reason = (
                    blocked.reason[:40] + "..." if len(blocked.reason) > 40 else blocked.reason
                )
                lines.append(
                    f"| {blocked.task_key} | {blocked_title} | {blocked_reason} | {blocked.failed_at} |"
                )
        else:
            lines.append("*No blocked tasks*")
        lines.append("")

        # Worker Statistics
        lines.append("## Worker Statistics")
        if worker_stats:
            lines.append("| Worker | Completed | Failed | Invocations |")
            lines.append("|--------|-----------|--------|-------------|")
            for ws in worker_stats:
                lines.append(
                    f"| Worker {ws.worker_id} | {ws.completed} completed | "
                    f"{ws.failed} failed | {ws.invocations} invocations |"
                )
        else:
            lines.append("*No worker statistics*")
        lines.append("")

        # Invocation Budget
        lines.append("## Invocation Budget")
        used = budget_info["used"]
        limit = budget_info["limit"]
        percentage = budget_info["percentage"]
        lines.append(f"**Used**: {used}/{limit} ({percentage:.0f}%)")

        if budget_info["is_warning"]:
            lines.append("Warning: Nearing limit")
        lines.append("")

        return "\n".join(lines)

    def record_completion_time(self, duration_seconds: float) -> None:
        """Record a task completion time for ETA calculation.

        Called by WorkerPool after each task completes to maintain
        accurate ETA estimates.

        Args:
            duration_seconds: Time taken to complete the task.
        """
        if duration_seconds > 0:
            self._completion_times.append(duration_seconds)
            # Keep only last 20 for rolling average
            self._completion_times = self._completion_times[-20:]
