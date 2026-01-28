"""Worker budget tests - invocation limit enforcement."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.worker_pool import WorkerConfig, WorkerPool


class TestBudgetEnforcement:
    """Invocation budget limit tests."""

    @pytest.mark.asyncio
    async def test_budget_check_returns_count_and_limit(self) -> None:
        """check_invocation_budget returns current count and limit."""
        async with OrchestratorDB(":memory:") as db:
            # Start execution run with default budget (100)
            run_id = await db.start_execution_run(max_workers=2)

            # Record some invocations
            await db.record_invocation(run_id, "RED", worker_id=1, task_id=1, duration_ms=100)
            await db.record_invocation(run_id, "GREEN", worker_id=1, task_id=1, duration_ms=150)
            await db.record_invocation(run_id, "VERIFY", worker_id=2, task_id=2, duration_ms=200)

            # Verify count/limit returned correctly
            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 3, "Should count 3 invocations"
            assert limit == 100, "Default limit should be 100"
            assert is_warning is False, "Should not be at warning threshold (3/100)"

    @pytest.mark.asyncio
    async def test_budget_exceeded_detected(self) -> None:
        """Budget exceeded is detected when count >= limit."""
        async with OrchestratorDB(":memory:") as db:
            # Set low budget (max_invocations_per_session=2)
            await db.set_config("max_invocations_per_session", "2")

            # Start execution run
            run_id = await db.start_execution_run(max_workers=2)

            # Record invocations up to/beyond limit
            await db.record_invocation(run_id, "RED", worker_id=1, task_id=1, duration_ms=100)
            await db.record_invocation(run_id, "GREEN", worker_id=1, task_id=1, duration_ms=150)

            # Check budget at limit
            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 2, "Should count 2 invocations"
            assert limit == 2, "Limit should be 2"
            assert count >= limit, "Budget should be exceeded (count >= limit)"

            # Record one more invocation (over limit)
            await db.record_invocation(run_id, "VERIFY", worker_id=1, task_id=1, duration_ms=200)

            # Verify exceeded state
            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 3, "Should count 3 invocations"
            assert count > limit, "Budget should be over limit (3 > 2)"

    @pytest.mark.asyncio
    async def test_budget_warning_threshold(self) -> None:
        """Warning threshold is detected before budget exhausted."""
        async with OrchestratorDB(":memory:") as db:
            # Set warning at 80%, limit at 10
            await db.set_config("max_invocations_per_session", "10")
            await db.set_config("budget_warning_threshold", "80")

            # Start execution run
            run_id = await db.start_execution_run(max_workers=2)

            # Record 7 invocations (70% - below warning)
            for i in range(7):
                await db.record_invocation(run_id, "RED", worker_id=1, task_id=1, duration_ms=100)

            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 7, "Should count 7 invocations"
            assert limit == 10, "Limit should be 10"
            assert is_warning is False, "Should not warn at 70%"

            # Record 1 more invocation (80% - at warning)
            await db.record_invocation(run_id, "GREEN", worker_id=1, task_id=1, duration_ms=100)

            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 8, "Should count 8 invocations"
            assert is_warning is True, "Should warn at 80%"

            # Record 1 more invocation (90% - still warning)
            await db.record_invocation(run_id, "VERIFY", worker_id=1, task_id=1, duration_ms=100)

            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 9, "Should count 9 invocations"
            assert is_warning is True, "Should still warn at 90%"

    @pytest.mark.asyncio
    async def test_pool_stops_on_budget_exhaustion(self, tmp_path: Path) -> None:
        """WorkerPool stops processing when budget exhausted."""
        # Create minimal test environment
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()

        async with OrchestratorDB(":memory:") as db:
            # Set very low budget (2 invocations)
            await db.set_config("max_invocations_per_session", "2")

            # Create 3 tasks with file paths to avoid Git errors
            await db.create_task(
                "TDD-01",
                "Task 1",
                phase=0,
                sequence=0,
                test_file="test_1.py",
                impl_file="impl_1.py",
            )
            await db.create_task(
                "TDD-02",
                "Task 2",
                phase=0,
                sequence=1,
                test_file="test_2.py",
                impl_file="impl_2.py",
            )
            await db.create_task(
                "TDD-03",
                "Task 3",
                phase=0,
                sequence=2,
                test_file="test_3.py",
                impl_file="impl_3.py",
            )

            # Configure WorkerPool with low budget
            config = WorkerConfig(
                max_workers=2,
                max_invocations_per_session=2,
                budget_warning_threshold=80,
                single_branch_mode=True,  # Avoid Git operations
            )

            pool = WorkerPool(db=db, base_dir=test_dir, config=config)

            # Mock Worker._run_tdd_pipeline and Git operations
            with (
                patch("tdd_orchestrator.worker_pool.Worker._run_tdd_pipeline") as mock_pipeline,
                patch("tdd_orchestrator.git_coordinator.GitCoordinator.commit_changes"),
            ):

                async def mock_pipeline_side_effect(task: dict[str, Any]) -> bool:
                    # Record invocation via database (simulating real behavior)
                    run_id = pool.run_id
                    await db.record_invocation(
                        run_id, "RED", worker_id=1, task_id=task["id"], duration_ms=100
                    )
                    # Return success
                    return True

                mock_pipeline.side_effect = mock_pipeline_side_effect

                # Run pool (should stop after budget exhausted)
                result = await pool.run_parallel_phase(phase=0)

                # Verify stopped due to budget
                assert result.stopped_reason == "invocation_limit", (
                    f"Expected invocation_limit, got {result.stopped_reason}"
                )
                assert result.total_invocations >= 2, "Should record at least 2 invocations"

    @pytest.mark.asyncio
    async def test_budget_isolated_per_run(self) -> None:
        """Budget is tracked separately for each execution run."""
        async with OrchestratorDB(":memory:") as db:
            await db.set_config("max_invocations_per_session", "10")

            # Start first execution run
            run_id_1 = await db.start_execution_run(max_workers=2)
            await db.record_invocation(run_id_1, "RED", worker_id=1, task_id=1, duration_ms=100)
            await db.record_invocation(run_id_1, "GREEN", worker_id=1, task_id=1, duration_ms=150)

            # Start second execution run
            run_id_2 = await db.start_execution_run(max_workers=2)
            await db.record_invocation(run_id_2, "RED", worker_id=2, task_id=2, duration_ms=100)

            # Check budgets independently
            count_1, limit_1, _ = await db.check_invocation_budget(run_id_1)
            count_2, limit_2, _ = await db.check_invocation_budget(run_id_2)

            assert count_1 == 2, "Run 1 should have 2 invocations"
            assert count_2 == 1, "Run 2 should have 1 invocation"
            assert limit_1 == limit_2 == 10, "Both runs should have same limit"

    @pytest.mark.asyncio
    async def test_zero_invocations_before_run_starts(self) -> None:
        """Budget check returns 0 count before any invocations recorded."""
        async with OrchestratorDB(":memory:") as db:
            await db.set_config("max_invocations_per_session", "100")

            # Start execution run but record no invocations
            run_id = await db.start_execution_run(max_workers=2)

            # Check budget
            count, limit, is_warning = await db.check_invocation_budget(run_id)

            assert count == 0, "Should count 0 invocations initially"
            assert limit == 100, "Limit should be 100"
            assert is_warning is False, "Should not warn at 0%"
