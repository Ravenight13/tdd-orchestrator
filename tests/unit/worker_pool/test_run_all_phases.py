"""Tests for WorkerPool.run_all_phases() multi-phase sequential execution.

Tests verify that phases are processed in order, results are aggregated,
and execution stops on failure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.worker_pool.config import PoolResult, WorkerConfig, WorkerStats
from tdd_orchestrator.worker_pool.pool import WorkerPool


def _make_pool_result(
    *,
    completed: int = 0,
    failed: int = 0,
    invocations: int = 0,
    stopped_reason: str | None = None,
) -> PoolResult:
    """Helper to build a PoolResult for test assertions."""
    return PoolResult(
        tasks_completed=completed,
        tasks_failed=failed,
        total_invocations=invocations,
        worker_stats=[WorkerStats(worker_id=1, tasks_completed=completed)],
        stopped_reason=stopped_reason,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock database with get_pending_phases and phase gate methods."""
    db = AsyncMock()
    db.get_pending_phases = AsyncMock(return_value=[0, 1, 2])
    db.get_tasks_in_phases_before = AsyncMock(return_value=[])
    db.get_test_files_from_phases_before = AsyncMock(return_value=[])
    db.get_all_tasks = AsyncMock(return_value=[])
    db.update_run_validation = AsyncMock()
    return db


@pytest.fixture
def pool(mock_db: AsyncMock) -> WorkerPool:
    """Create a WorkerPool with mocked dependencies."""
    with patch.object(WorkerPool, "__init__", lambda self, **kw: None):
        p = WorkerPool.__new__(WorkerPool)
        p.db = mock_db
        p.base_dir = Path("/tmp/test")
        p.config = WorkerConfig()
        p.workers = []
        p.run_id = 0
    return p


class TestRunAllPhasesOrdering:
    """Tests for phase ordering and sequential execution."""

    async def test_processes_phases_in_order(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Phases [0, 1, 2] all succeed -> run_parallel_phase called 0, 1, 2."""
        call_order: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            call_order.append(phase)
            return _make_pool_result(completed=1, invocations=5)

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        await pool.run_all_phases()

        assert call_order == [0, 1, 2]

    async def test_stops_on_phase_failure(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Phase 1 returns stopped_reason -> phase 2 never called."""
        call_order: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            call_order.append(phase)
            if phase == 1:
                return _make_pool_result(failed=1, stopped_reason="task_failure")
            return _make_pool_result(completed=1)

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()

        assert call_order == [0, 1]
        assert result.stopped_reason == "task_failure"


class TestRunAllPhasesEmptyPhases:
    """Tests for no pending phases."""

    async def test_no_pending_phases(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """get_pending_phases returns [] -> returns PoolResult with stopped_reason='no_tasks'."""
        mock_db.get_pending_phases.return_value = []

        result = await pool.run_all_phases()

        assert result.tasks_completed == 0
        assert result.tasks_failed == 0
        assert result.stopped_reason == "no_tasks"


class TestRunAllPhasesAggregation:
    """Tests for result aggregation across phases."""

    async def test_aggregates_completed_counts(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Phase 0: 2 completed, phase 1: 3 completed -> total=5."""
        mock_db.get_pending_phases.return_value = [0, 1]

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            if phase == 0:
                return _make_pool_result(completed=2, invocations=5)
            return _make_pool_result(completed=3, invocations=7)

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.tasks_completed == 5

    async def test_aggregates_failed_counts(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Verify tasks_failed summed across phases (stops on failure)."""
        mock_db.get_pending_phases.return_value = [0, 1]

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            if phase == 0:
                return _make_pool_result(completed=2, invocations=5)
            return _make_pool_result(completed=1, failed=1, stopped_reason="task_failure")

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.tasks_failed == 1
        assert result.tasks_completed == 3

    async def test_aggregates_invocations(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Verify total_invocations summed across phases."""
        mock_db.get_pending_phases.return_value = [0, 1]

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            if phase == 0:
                return _make_pool_result(completed=1, invocations=10)
            return _make_pool_result(completed=1, invocations=15)

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.total_invocations == 25

    async def test_worker_stats_from_final_phase(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Worker stats are from the final phase that ran."""
        mock_db.get_pending_phases.return_value = [0, 1]

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            stats = WorkerStats(worker_id=phase or 0, tasks_completed=1)
            return PoolResult(
                tasks_completed=1, tasks_failed=0,
                total_invocations=5, worker_stats=[stats],
            )

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert len(result.worker_stats) == 1
        assert result.worker_stats[0].worker_id == 1  # from phase 1 (last)


class TestRunAllPhasesPlaceholders:
    """Tests for phase gate and end-of-run validation placeholders."""

    async def test_phase_gate_placeholder_allows(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """_run_phase_gate returns True (default) -> phase runs."""
        mock_db.get_pending_phases.return_value = [0]
        pool.run_parallel_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_pool_result(completed=1)
        )

        result = await pool.run_all_phases()
        assert result.tasks_completed == 1
        pool.run_parallel_phase.assert_called_once_with(0)

    async def test_end_of_run_validation_placeholder(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """_run_end_of_run_validation returns True -> no stopped_reason."""
        mock_db.get_pending_phases.return_value = [0]
        pool.run_parallel_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_pool_result(completed=1)
        )

        result = await pool.run_all_phases()
        assert result.stopped_reason is None

    async def test_phase_gate_blocks_execution(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """_run_phase_gate returns False -> phase skipped, stopped_reason set."""
        mock_db.get_pending_phases.return_value = [0]
        pool.run_parallel_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_pool_result(completed=1)
        )
        pool._run_phase_gate = AsyncMock(return_value=False)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.stopped_reason == "gate_failure"
        pool.run_parallel_phase.assert_not_called()

    async def test_end_of_run_validation_failure(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """_run_end_of_run_validation returns False -> stopped_reason set."""
        mock_db.get_pending_phases.return_value = [0]
        pool.run_parallel_phase = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_pool_result(completed=1)
        )
        pool._run_end_of_run_validation = AsyncMock(return_value=False)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.stopped_reason == "validation_failure"


class TestRunAllPhasesPhaseGateConfig:
    """Tests for phase gate configuration."""

    async def test_enable_phase_gates_false_bypasses_validation(
        self, mock_db: AsyncMock
    ) -> None:
        """enable_phase_gates=False -> all phases execute without gate checks."""
        config = WorkerConfig(enable_phase_gates=False)

        with patch.object(WorkerPool, "__init__", lambda self, **kw: None):
            p = WorkerPool.__new__(WorkerPool)
            p.db = mock_db
            p.base_dir = Path("/tmp/test")
            p.config = config
            p.workers = []
            p.run_id = 0

        mock_db.get_pending_phases.return_value = [0, 1]
        call_order: list[int | None] = []

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            call_order.append(phase)
            return _make_pool_result(completed=1, invocations=5)

        p.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await p.run_all_phases()

        assert call_order == [0, 1]
        assert result.tasks_completed == 2
        # DB gate methods should NOT have been called
        mock_db.get_tasks_in_phases_before.assert_not_called()


class TestRunAllPhasesNoTasksSkip:
    """Tests for phases returning no_tasks."""

    async def test_no_tasks_in_phase_does_not_stop(
        self, pool: WorkerPool, mock_db: AsyncMock
    ) -> None:
        """Phase returning stopped_reason='no_tasks' does NOT stop the loop."""
        mock_db.get_pending_phases.return_value = [0, 1]

        async def mock_run_phase(phase: int | None = None) -> PoolResult:
            if phase == 0:
                return _make_pool_result(stopped_reason="no_tasks")
            return _make_pool_result(completed=2, invocations=5)

        pool.run_parallel_phase = AsyncMock(side_effect=mock_run_phase)  # type: ignore[method-assign]

        result = await pool.run_all_phases()
        assert result.tasks_completed == 2
        assert result.stopped_reason is None
