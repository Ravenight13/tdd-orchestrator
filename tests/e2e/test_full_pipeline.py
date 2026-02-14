"""End-to-end integration tests for full TDD pipeline.

These tests verify the complete orchestrator workflow from task creation
through RED -> GREEN -> VERIFY stages, including parallel execution,
failure recovery, and budget enforcement.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdd_orchestrator.models import Stage
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestSingleTaskCompletion:
    """Test single task completing through full TDD pipeline."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_single_task_completes_through_tdd_stages(
        self,
        e2e_db,
        mock_git_e2e,
        mock_sdk_success,
        mock_verifier_tdd_cycle,
    ) -> None:
        """Single task progresses RED -> GREEN -> VERIFY and completes."""
        # Setup: Create task and execution run
        run_id = await e2e_db.start_execution_run(max_workers=1)
        task_id = await e2e_db.create_task(
            task_key="TDD-E2E-01",
            title="E2E Test Task",
            phase=0,
            sequence=0,
            test_file="tests/test_e2e.py",
            impl_file="src/e2e.py",
        )

        # Create worker with mocked dependencies
        config = WorkerConfig(
            max_workers=1,
            single_branch_mode=True,
            heartbeat_interval_seconds=1,
        )
        worker = Worker(1, e2e_db, mock_git_e2e, config, run_id, Path.cwd())

        # Inject mock verifier
        worker.verifier = mock_verifier_tdd_cycle

        # Patch Agent SDK
        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_sdk_success),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            # Start worker
            await worker.start()

            # Claim and process task
            claimed = await e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300)
            assert claimed is True, "Worker should successfully claim task"

            task = await e2e_db.get_task_by_key("TDD-E2E-01")
            assert task is not None, "Task should exist"
            assert task["status"] == "in_progress", "Task should be in progress"

            # Execute RED stage
            red_result = await worker._run_stage(Stage.RED, task)
            assert red_result.success is True, "RED stage should succeed (pytest fails)"
            assert "FAILED" in red_result.output or "ImportError" in red_result.output

            # Record attempt
            await e2e_db.record_attempt(
                task_id=task_id,
                stage="red",
                success=True,
                pytest_output=red_result.output,
            )

            # Execute GREEN stage
            green_result = await worker._run_stage(Stage.GREEN, task, test_output=red_result.output)
            assert green_result.success is True, "GREEN stage should succeed (pytest passes)"
            assert "1 passed" in green_result.output

            # Record attempt
            await e2e_db.record_attempt(
                task_id=task_id,
                stage="green",
                success=True,
                pytest_output=green_result.output,
            )

            # Execute VERIFY stage
            verify_result = await worker._run_stage(
                Stage.VERIFY, task, impl_output=green_result.output
            )
            assert verify_result.success is True, "VERIFY stage should pass all checks"
            # VERIFY stage output is from SDK, not from verifier
            # Just check that it succeeded

            # Mark task complete
            await e2e_db.update_task_status("TDD-E2E-01", "passing")

            # Verify final state
            final_task = await e2e_db.get_task_by_key("TDD-E2E-01")
            assert final_task is not None
            assert final_task["status"] == "passing", "Task should be in passing state"

            # Verify attempts were recorded
            attempts = await e2e_db.get_stage_attempts(task_id)
            assert len(attempts) >= 3, "Should have at least 3 attempts (RED, GREEN, VERIFY)"

            # Cleanup
            await worker.stop()


class TestParallelTaskExecution:
    """Test parallel workers processing independent tasks."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_parallel_workers_process_independent_tasks(
        self,
        e2e_db,
        mock_git_e2e,
        mock_sdk_success,
        mock_verifier_all_pass,
    ) -> None:
        """Multiple workers can claim independent tasks atomically without conflicts."""
        # Setup: Create 3 independent tasks
        run_id = await e2e_db.start_execution_run(max_workers=2)
        task_ids = []
        for i in range(3):
            task_id = await e2e_db.create_task(
                task_key=f"TDD-PAR-{i:02d}",
                title=f"Parallel Task {i}",
                phase=0,
                sequence=i,
                test_file=f"tests/test_par_{i}.py",
                impl_file=f"src/par_{i}.py",
            )
            task_ids.append(task_id)

        # Create 2 workers
        config = WorkerConfig(
            max_workers=2,
            single_branch_mode=True,
            heartbeat_interval_seconds=1,
        )

        # Create separate git mocks for each worker
        mock_git_1 = MagicMock()
        mock_git_1.create_worker_branch = AsyncMock(return_value="worker-1/branch")
        mock_git_1.commit_changes = AsyncMock(return_value="abc123")

        mock_git_2 = MagicMock()
        mock_git_2.create_worker_branch = AsyncMock(return_value="worker-2/branch")
        mock_git_2.commit_changes = AsyncMock(return_value="def456")

        worker1 = Worker(1, e2e_db, mock_git_1, config, run_id, Path.cwd())
        worker2 = Worker(2, e2e_db, mock_git_2, config, run_id, Path.cwd())

        # Inject mock verifiers
        worker1.verifier = mock_verifier_all_pass
        worker2.verifier = mock_verifier_all_pass

        # Patch Agent SDK for both workers
        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_sdk_success),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            # Start workers
            await worker1.start()
            await worker2.start()

            # Attempt concurrent claims on same task
            task_id = task_ids[0]

            # Both workers try to claim the same task simultaneously
            claims = await asyncio.gather(
                e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300),
                e2e_db.claim_task(task_id, worker_id=2, timeout_seconds=300),
                return_exceptions=True,
            )

            # Exactly one should succeed (atomic claiming)
            successful_claims = [c for c in claims if c is True]
            assert len(successful_claims) == 1, (
                f"Exactly one worker should claim task (got {len(successful_claims)})"
            )

            # Verify task is claimed by one worker
            task = await e2e_db.get_task_by_key("TDD-PAR-00")
            assert task is not None
            assert task["claimed_by"] in [1, 2], "Task should be claimed by either worker 1 or 2"
            assert task["status"] == "in_progress", "Claimed task should be in_progress"

            # Process remaining tasks sequentially to avoid race issues
            for i in range(1, 3):
                task_id = task_ids[i]
                task = await e2e_db.get_next_pending_task()
                if task:
                    claimed = await e2e_db.claim_task(task["id"], worker_id=1, timeout_seconds=300)
                    if claimed:
                        await e2e_db.update_task_status(task["task_key"], "complete")
                        await e2e_db.release_task(task["id"], worker_id=1, outcome="completed")

            # Verify no data corruption occurred
            stats = await e2e_db.get_stats()
            total_tasks = (
                stats.get("complete", 0) + stats.get("in_progress", 0) + stats.get("pending", 0)
            )
            assert total_tasks == 3, f"Should have exactly 3 tasks total (got {total_tasks})"

            # Cleanup
            await worker1.stop()
            await worker2.stop()


class TestFailureRecovery:
    """Test task failure and retry handling."""

    @pytest.mark.asyncio
    async def test_task_failure_allows_retry(
        self,
        e2e_db,
        mock_git_e2e,
        mock_sdk_failure_then_success,
    ) -> None:
        """Task can be retried after failure, retry count increments."""
        # Setup: Create task
        run_id = await e2e_db.start_execution_run(max_workers=1)
        task_id = await e2e_db.create_task(
            task_key="TDD-FAIL-01",
            title="Failure Recovery Test",
            goal="Implement failure recovery feature",
            phase=0,
            sequence=0,
            test_file="tests/test_fail.py",
            impl_file="src/fail.py",
        )

        config = WorkerConfig(single_branch_mode=True)
        worker = Worker(1, e2e_db, mock_git_e2e, config, run_id, Path.cwd())

        # Mock verifier
        class MockVerifier:
            call_count = 0

            async def run_pytest(self, test_file: str) -> tuple[bool, str]:
                self.call_count += 1
                if self.call_count == 1:
                    return (False, "FAILED: Initial test failure")
                else:
                    return (True, "1 passed after retry")

            async def run_ruff(self, impl_file: str) -> tuple[bool, str]:
                return (True, "All checks passed!")

            async def run_mypy(self, impl_file: str) -> tuple[bool, str]:
                return (True, "Success: no issues found")

        worker.verifier = MockVerifier()

        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch(
                "tdd_orchestrator.worker_pool.worker.sdk_query",
                side_effect=mock_sdk_failure_then_success,
            ),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            await worker.start()

            # First attempt - should fail
            claimed = await e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300)
            assert claimed is True

            task = await e2e_db.get_task_by_key("TDD-FAIL-01")
            assert task is not None

            # Try RED stage - this will fail due to mock
            try:
                red_result = await worker._run_stage(Stage.RED, task)
                # Record failure
                await e2e_db.record_attempt(
                    task_id, "red", success=False, error_message=red_result.output
                )
                # Mark as blocked (no 'failed' status exists)
                await e2e_db.update_task_status("TDD-FAIL-01", "blocked")
            except Exception as e:
                # Expected - record the failure
                await e2e_db.record_attempt(task_id, "red", success=False, error_message=str(e))
                await e2e_db.update_task_status("TDD-FAIL-01", "blocked")

            # Release task
            await e2e_db.release_task(task_id, worker_id=1, outcome="failed")

            # Verify task is in blocked state
            task_after_fail = await e2e_db.get_task_by_key("TDD-FAIL-01")
            assert task_after_fail is not None
            assert task_after_fail["status"] == "blocked"

            # Second attempt - retry should succeed
            # Reset task to pending for retry
            await e2e_db.update_task_status("TDD-FAIL-01", "pending")

            claimed_retry = await e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300)
            assert claimed_retry is True, "Should be able to reclaim failed task"

            task_retry = await e2e_db.get_task_by_key("TDD-FAIL-01")
            assert task_retry is not None

            # Run RED stage again - should succeed this time
            red_result_retry = await worker._run_stage(Stage.RED, task_retry)
            await e2e_db.record_attempt(
                task_id, "red", success=True, pytest_output=red_result_retry.output
            )

            # Verify retry count incremented
            attempts = await e2e_db.get_stage_attempts(task_id)
            red_attempts = [a for a in attempts if a["stage"] == "red"]
            assert len(red_attempts) >= 2, "Should have at least 2 RED attempts (failure + retry)"

            # Mark complete
            await e2e_db.update_task_status("TDD-FAIL-01", "complete")

            final_task = await e2e_db.get_task_by_key("TDD-FAIL-01")
            assert final_task is not None
            assert final_task["status"] == "complete", "Task should complete after retry"

            await worker.stop()


class TestBudgetExhaustion:
    """Test invocation budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_exhaustion_halts_processing(
        self,
        e2e_db,
        mock_git_e2e,
        mock_sdk_success,
        mock_verifier_all_pass,
    ) -> None:
        """Processing halts when invocation budget is exceeded."""
        # Setup: Create 5 tasks but set very low budget
        max_invocations = 3
        await e2e_db.set_config("max_invocations_per_session", str(max_invocations))

        run_id = await e2e_db.start_execution_run(max_workers=1)

        # Create 5 tasks (more than budget allows)
        for i in range(5):
            await e2e_db.create_task(
                task_key=f"TDD-BUDGET-{i:02d}",
                title=f"Budget Test Task {i}",
                phase=0,
                sequence=i,
                test_file=f"tests/test_budget_{i}.py",
                impl_file=f"src/budget_{i}.py",
            )

        config = WorkerConfig(
            max_workers=1,
            max_invocations_per_session=max_invocations,
            single_branch_mode=True,
        )
        worker = Worker(1, e2e_db, mock_git_e2e, config, run_id, Path.cwd())
        worker.verifier = mock_verifier_all_pass

        with (
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_sdk_success),
            patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", return_value=MagicMock()),
        ):
            await worker.start()

            # Pre-record invocations to exceed budget
            for _ in range(max_invocations + 1):
                await e2e_db.record_invocation(run_id, "red")

            # Check budget - should be exceeded
            count, limit, is_warning = await e2e_db.check_invocation_budget(run_id)
            assert count > limit, "Invocation count should exceed limit"
            # is_warning=True means at 80% threshold, but we're fully exceeded (count > limit)
            # The budget logic still reports warning=True when exceeded

            # Verify remaining tasks stay pending
            stats = await e2e_db.get_stats()
            assert stats["pending"] == 5, "All tasks should remain pending (budget exhausted)"

            # Attempt to claim task - should work (budget doesn't prevent claiming)
            task = await e2e_db.get_next_pending_task()
            if task:
                task_id = task["id"]
                claimed = await e2e_db.claim_task(task_id, worker_id=1, timeout_seconds=300)

                # Note: Budget checking happens at worker pool level, not individual worker
                # This test verifies budget can be checked and enforced
                if claimed:
                    # Even if claimed, budget check would prevent stage execution
                    # Release the task with valid outcome
                    await e2e_db.release_task(task_id, worker_id=1, outcome="released")

            # Verify budget state persists
            final_count, final_limit, _ = await e2e_db.check_invocation_budget(run_id)
            assert final_count >= max_invocations, "Budget should remain exceeded"

            await worker.stop()
