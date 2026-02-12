"""Dependency resolution tests for orchestrator database.

This module tests the v_ready_tasks view logic that determines which tasks
are ready to execute based on their dependencies.
"""

from __future__ import annotations

import pytest
from tdd_orchestrator.database import OrchestratorDB


class TestDependencyResolution:
    """Tests for v_ready_tasks view and dependency checks."""

    @pytest.mark.asyncio
    async def test_task_with_unmet_dependency_not_ready(self) -> None:
        """Tasks with pending dependencies are not in ready queue."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-00"

    @pytest.mark.asyncio
    async def test_task_with_complete_dependency_is_ready(self) -> None:
        """Tasks with completed dependencies appear in ready queue."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )
            await db.update_task_status("TDD-00", "complete")

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-01"

    @pytest.mark.asyncio
    async def test_task_with_passing_dependency_is_ready(self) -> None:
        """'passing' status counts as dependency satisfied."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )
            await db.update_task_status("TDD-00", "passing")

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-01"

    @pytest.mark.asyncio
    async def test_task_without_dependencies_is_ready(self) -> None:
        """Task with no dependencies is immediately ready."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Independent", phase=0, sequence=0)

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-01"

    @pytest.mark.asyncio
    async def test_multiple_dependencies_all_must_be_met(self) -> None:
        """Task with multiple dependencies requires all to be satisfied."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq 1", phase=0, sequence=0)
            await db.create_task("TDD-01", "Prereq 2", phase=0, sequence=1)
            await db.create_task(
                "TDD-02",
                "Dependent",
                depends_on=["TDD-00", "TDD-01"],
                phase=0,
                sequence=2,
            )
            await db.update_task_status("TDD-00", "complete")
            # TDD-01 still pending

            ready_task = await db.get_next_pending_task()

            # Should return TDD-01 (next independent task), not TDD-02
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-01"


class TestNegativeDependencies:
    """Negative dependency test cases - edge cases and invalid states."""

    @pytest.mark.asyncio
    async def test_circular_dependency_detected(self) -> None:
        """Circular dependencies result in no ready tasks (deadlock)."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Task A", phase=0, sequence=0, depends_on=["TDD-02"])
            await db.create_task("TDD-02", "Task B", phase=0, sequence=1, depends_on=["TDD-01"])

            # Should detect circular dependency (no task is ready)
            ready_task = await db.get_next_pending_task()
            assert ready_task is None  # Deadlock detected

    @pytest.mark.asyncio
    async def test_missing_dependency_allows_task(self) -> None:
        """Missing dependency reference currently allows task to proceed.

        NOTE: This is current behavior - the v_ready_tasks view uses a JOIN
        to check dependencies. If a dependency doesn't exist, the JOIN fails
        and NOT EXISTS returns true, making the task ready.

        Future improvement: Add validation to ensure all dependencies exist
        before marking a task as ready.
        """
        async with OrchestratorDB(":memory:") as db:
            await db.create_task(
                "TDD-01",
                "Orphan",
                depends_on=["TDD-NONEXISTENT"],
                phase=0,
                sequence=0,
            )

            ready_task = await db.get_next_pending_task()
            # Current behavior: task is ready because JOIN fails (no blocker found)
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-01"

    @pytest.mark.asyncio
    async def test_phase_ordering_respected(self) -> None:
        """Lower phase tasks are returned before higher phase tasks."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-10", "Phase 1", phase=1, sequence=0)
            await db.create_task("TDD-00", "Phase 0", phase=0, sequence=0)

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-00"

    @pytest.mark.asyncio
    async def test_blocked_dependency_blocks_dependent(self) -> None:
        """Task with blocked dependency should not be ready."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )
            await db.update_task_status("TDD-00", "blocked")

            ready_task = await db.get_next_pending_task()

            # TDD-01 should not be ready since TDD-00 is blocked
            assert ready_task is None

    @pytest.mark.asyncio
    async def test_in_progress_dependency_blocks_dependent(self) -> None:
        """Task with in_progress dependency should not be ready."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )
            await db.update_task_status("TDD-00", "in_progress")

            ready_task = await db.get_next_pending_task()

            # TDD-01 should not be ready since TDD-00 is in_progress
            assert ready_task is None

    @pytest.mark.asyncio
    async def test_sequence_ordering_within_phase(self) -> None:
        """Tasks within same phase are ordered by sequence."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-10", "Task 2", phase=0, sequence=10)
            await db.create_task("TDD-05", "Task 1", phase=0, sequence=5)
            await db.create_task("TDD-15", "Task 3", phase=0, sequence=15)

            ready_task = await db.get_next_pending_task()

            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-05"

    @pytest.mark.asyncio
    async def test_complex_dependency_chain(self) -> None:
        """Test complex dependency chain: A -> B -> C."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-A", "Task A", phase=0, sequence=0)
            await db.create_task("TDD-B", "Task B", depends_on=["TDD-A"], phase=0, sequence=1)
            await db.create_task("TDD-C", "Task C", depends_on=["TDD-B"], phase=0, sequence=2)

            # Only A should be ready initially
            ready_task = await db.get_next_pending_task()
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-A"

            # Complete A, now B should be ready
            await db.update_task_status("TDD-A", "complete")
            ready_task = await db.get_next_pending_task()
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-B"

            # Complete B, now C should be ready
            await db.update_task_status("TDD-B", "complete")
            ready_task = await db.get_next_pending_task()
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-C"

    @pytest.mark.asyncio
    async def test_partial_dependency_satisfaction(self) -> None:
        """Task with 3 dependencies waits until all are satisfied."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-A", "Task A", phase=0, sequence=0)
            await db.create_task("TDD-B", "Task B", phase=0, sequence=1)
            await db.create_task("TDD-C", "Task C", phase=0, sequence=2)
            await db.create_task(
                "TDD-D",
                "Task D",
                depends_on=["TDD-A", "TDD-B", "TDD-C"],
                phase=0,
                sequence=3,
            )

            # Complete 2 out of 3 dependencies
            await db.update_task_status("TDD-A", "complete")
            await db.update_task_status("TDD-B", "passing")

            # D should still not be ready
            ready_tasks = []
            for _ in range(10):  # Try to get all ready tasks
                task = await db.get_next_pending_task()
                if task is None:
                    break
                ready_tasks.append(task["task_key"])
                await db.update_task_status(task["task_key"], "in_progress")

            assert "TDD-D" not in ready_tasks

            # Now complete the third dependency
            await db.update_task_status("TDD-C", "complete")
            await db.update_task_status("TDD-D", "pending")  # Reset D

            ready_task = await db.get_next_pending_task()
            assert ready_task is not None
            assert ready_task["task_key"] == "TDD-D"
