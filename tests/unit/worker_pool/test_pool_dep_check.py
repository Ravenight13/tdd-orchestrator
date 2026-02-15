"""Tests for the application-level dependency safety net in WorkerPool.

Verifies that the pool filters tasks through are_dependencies_met()
before assigning them to workers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from tdd_orchestrator.worker_pool.pool import WorkerPool


class TestPoolDependencyCheck:
    """Tests for dependency safety net in run_parallel_phase."""

    def _make_pool(self, mock_db: AsyncMock, tmp_path: Path) -> WorkerPool:
        """Create a WorkerPool with mocked DB."""
        return WorkerPool(db=mock_db, base_dir=tmp_path)

    def _make_db(self, tasks: list[dict[str, object]]) -> AsyncMock:
        """Create a mock DB returning the given claimable tasks."""
        db = AsyncMock()
        db.cleanup_stale_claims = AsyncMock(return_value=0)
        db.start_execution_run = AsyncMock(return_value=1)
        db.get_claimable_tasks = AsyncMock(return_value=tasks)
        db.complete_execution_run = AsyncMock()
        db.get_invocation_count = AsyncMock(return_value=0)
        db.get_resumable_tasks = AsyncMock(return_value=[])
        db.check_invocation_budget = AsyncMock(return_value=(0, 100, False))
        db.claim_task = AsyncMock(return_value=False)
        db.register_worker = AsyncMock()
        db.unregister_worker = AsyncMock()
        db.get_config_int = AsyncMock(return_value=60)
        db.update_worker_heartbeat = AsyncMock()
        # Mock _conn for are_dependencies_met
        db._conn = AsyncMock()
        return db

    @patch("tdd_orchestrator.worker_pool.pool.are_dependencies_met")
    async def test_filters_unmet_tasks(
        self, mock_deps: AsyncMock, tmp_path: Path,
    ) -> None:
        """Tasks with unmet dependencies are filtered out."""
        tasks = [
            {"task_key": "T-01", "id": 1},
            {"task_key": "T-02", "id": 2},
        ]
        db = self._make_db(tasks)
        pool = self._make_pool(db, tmp_path)

        # T-01 deps met, T-02 deps not met
        mock_deps.side_effect = [True, False]

        result = await pool.run_parallel_phase(phase=0)

        # T-02 was filtered, so only T-01 was processed
        # But pool still returns (no workers started for this test)
        # The key assertion: are_dependencies_met was called for both
        assert mock_deps.call_count == 2

    @patch("tdd_orchestrator.worker_pool.pool.are_dependencies_met")
    async def test_all_deps_met_passes_through(
        self, mock_deps: AsyncMock, tmp_path: Path,
    ) -> None:
        """All tasks pass through when all deps are met."""
        tasks = [
            {"task_key": "T-01", "id": 1},
            {"task_key": "T-02", "id": 2},
        ]
        db = self._make_db(tasks)
        pool = self._make_pool(db, tmp_path)
        mock_deps.return_value = True

        await pool.run_parallel_phase(phase=0)
        assert mock_deps.call_count == 2

    @patch("tdd_orchestrator.worker_pool.pool.are_dependencies_met")
    async def test_empty_task_list(
        self, mock_deps: AsyncMock, tmp_path: Path,
    ) -> None:
        """Empty task list doesn't call dep check."""
        db = self._make_db([])
        pool = self._make_pool(db, tmp_path)

        result = await pool.run_parallel_phase(phase=0)
        mock_deps.assert_not_called()
        assert result.stopped_reason == "no_tasks"

    @patch("tdd_orchestrator.worker_pool.pool.are_dependencies_met")
    async def test_all_filtered_returns_no_tasks(
        self, mock_deps: AsyncMock, tmp_path: Path,
    ) -> None:
        """When all tasks are filtered, result shows no_tasks."""
        tasks = [{"task_key": "T-01", "id": 1}]
        db = self._make_db(tasks)
        pool = self._make_pool(db, tmp_path)
        mock_deps.return_value = False

        result = await pool.run_parallel_phase(phase=0)
        assert result.stopped_reason == "no_tasks"
