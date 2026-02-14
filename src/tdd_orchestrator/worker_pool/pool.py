"""Worker pool for parallel task execution.

Manages a pool of workers that process TDD tasks in parallel,
with database-backed task claiming and Git branch coordination.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ..database import OrchestratorDB
from ..git_coordinator import GitCoordinator
from ..merge_coordinator import MergeCoordinator
from .config import PoolResult, WorkerConfig
from .phase_gate import PhaseGateValidator
from .run_validator import RunValidator
from .worker import Worker

logger = logging.getLogger(__name__)


class WorkerPool:
    """Manages parallel worker execution."""

    def __init__(
        self,
        db: OrchestratorDB,
        base_dir: Path,
        config: WorkerConfig | None = None,
        slack_webhook_url: str | None = None,
    ) -> None:
        """Initialize worker pool.

        Args:
            db: Database instance.
            base_dir: Root directory of the Git repository.
            config: Worker configuration.
            slack_webhook_url: Slack webhook for notifications.
        """
        self.db = db
        self.base_dir = base_dir
        self.config = config or WorkerConfig()
        self.git = GitCoordinator(base_dir)
        self.merge = MergeCoordinator(base_dir, slack_webhook_url)
        self.workers: list[Worker] = []
        self.run_id: int = 0

    async def run_parallel_phase(self, phase: int | None = None) -> PoolResult:
        """Run all tasks in a phase in parallel.

        Only Phase 0 tasks (no dependencies) are processed in parallel.

        Args:
            phase: Phase number to process.

        Returns:
            PoolResult with completion statistics.
        """
        # Start execution run
        self.run_id = await self.db.start_execution_run(self.config.max_workers)

        result = PoolResult(
            tasks_completed=0,
            tasks_failed=0,
            total_invocations=0,
            worker_stats=[],
        )

        try:
            # Get claimable tasks for this phase
            tasks = await self.db.get_claimable_tasks(phase)
            if not tasks:
                logger.info(
                    "No tasks available for phase %s", phase if phase is not None else "all"
                )
                result.stopped_reason = "no_tasks"
                return result

            logger.info(
                "Found %d tasks for phase %s", len(tasks), phase if phase is not None else "all"
            )

            # Create and start workers
            self.workers = [
                Worker(i, self.db, self.git, self.config, self.run_id, self.base_dir)
                for i in range(1, self.config.max_workers + 1)
            ]

            for worker in self.workers:
                await worker.start()

            # Process tasks with worker pool
            task_queue = list(tasks)

            while task_queue:
                # Check budget
                count, limit, is_warning = await self.db.check_invocation_budget(self.run_id)

                if count >= limit:
                    logger.warning("Invocation limit reached (%d/%d)", count, limit)
                    result.stopped_reason = "invocation_limit"
                    break

                if is_warning:
                    logger.warning(
                        "Budget warning: %d/%d invocations (%.0f%%)",
                        count,
                        limit,
                        count / limit * 100,
                    )

                # Assign tasks to workers
                worker_tasks: list[tuple[Worker, dict[str, Any]]] = []

                for worker in self.workers:
                    if task_queue:
                        task = task_queue.pop(0)
                        worker_tasks.append((worker, task))

                if not worker_tasks:
                    break

                # Process tasks in parallel
                results = await asyncio.gather(
                    *[worker.process_task(task) for worker, task in worker_tasks],
                    return_exceptions=True,
                )

                # Check for failures (100% success required)
                for i, (worker, _) in enumerate(worker_tasks):
                    if isinstance(results[i], Exception):
                        logger.error("Worker %d exception: %s", worker.worker_id, results[i])
                        result.tasks_failed += 1
                    elif results[i] is True:
                        result.tasks_completed += 1
                    else:
                        result.tasks_failed += 1

                # Stop on any failure (100% success required)
                if result.tasks_failed > 0:
                    logger.error("Task failure detected - stopping (100%% success required)")
                    result.stopped_reason = "task_failure"
                    break

            # Cleanup stale claims
            await self.db.cleanup_stale_claims()

            # Merge completed branches (skip in single branch mode - already on main)
            if result.tasks_completed > 0 and not self.config.single_branch_mode:
                completed_tasks = [t for t in tasks[: result.tasks_completed]]
                branches = [
                    (
                        f"worker-{(i % self.config.max_workers) + 1}/{t['task_key']}",
                        t["task_key"],
                    )
                    for i, t in enumerate(completed_tasks)
                ]

                merge_results = await self.merge.merge_phase_branches(phase, branches)

                for mr in merge_results:
                    if not mr.success:
                        logger.error("Merge failed for %s: %s", mr.branch, mr.error_message)
                        result.stopped_reason = "merge_failure"

        finally:
            # Stop all workers
            for worker in self.workers:
                await worker.stop()
                result.worker_stats.append(worker.stats)

            # Complete execution run
            status = "completed" if result.stopped_reason is None else "failed"
            await self.db.complete_execution_run(self.run_id, status)

            result.total_invocations = await self.db.get_invocation_count(self.run_id)

        return result

    async def run_all_phases(self) -> PoolResult:
        """Run all pending phases sequentially with failure gating.

        Iterates through phases returned by get_pending_phases(), running
        each via run_parallel_phase(). Stops on first phase failure (unless
        the stopped_reason is "no_tasks", which is non-fatal).

        Returns:
            PoolResult with aggregated statistics across all phases.
        """
        phases = await self.db.get_pending_phases()

        if not phases:
            logger.info("No pending phases found")
            return PoolResult(
                tasks_completed=0,
                tasks_failed=0,
                total_invocations=0,
                worker_stats=[],
                stopped_reason="no_tasks",
            )

        aggregate = PoolResult(
            tasks_completed=0,
            tasks_failed=0,
            total_invocations=0,
            worker_stats=[],
        )

        for phase in phases:
            if not await self._run_phase_gate(phase):
                logger.warning("Phase gate blocked phase %d", phase)
                aggregate.stopped_reason = "gate_failure"
                break

            logger.info("Starting phase %d", phase)
            result = await self.run_parallel_phase(phase)

            aggregate.tasks_completed += result.tasks_completed
            aggregate.tasks_failed += result.tasks_failed
            aggregate.total_invocations += result.total_invocations
            aggregate.worker_stats = result.worker_stats

            if result.stopped_reason and result.stopped_reason != "no_tasks":
                aggregate.stopped_reason = result.stopped_reason
                logger.error("Phase %d stopped: %s", phase, result.stopped_reason)
                break

        if not aggregate.stopped_reason:
            if not await self._run_end_of_run_validation():
                aggregate.stopped_reason = "validation_failure"

        return aggregate

    async def _run_phase_gate(self, phase: int) -> bool:
        """Validate prior phases before starting this phase."""
        if not self.config.enable_phase_gates:
            return True
        gate = PhaseGateValidator(self.db, self.base_dir)
        result = await gate.validate_phase(phase)
        logger.info("Phase gate: %s", result.summary)
        return result.passed

    async def _run_end_of_run_validation(self) -> bool:
        """Post-run validation with comprehensive checks."""
        validator = RunValidator(self.db, self.base_dir)
        result = await validator.validate_run(self.run_id)
        await self.db.update_run_validation(
            self.run_id,
            "passed" if result.passed else "failed",
            result.to_json(),
        )
        logger.info("End-of-run validation: %s", result.summary)
        return result.passed
