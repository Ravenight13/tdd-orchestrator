"""Tests for --resume flag and stale task recovery.

Covers:
- CLI flag wiring (--resume passed through to _run_parallel)
- WorkerPool.run_parallel_phase resume behavior
- WorkerPool.run_all_phases resume behavior
- cleanup_stale_claims integration
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.project_config import ProjectConfig, TDDConfig
from tdd_orchestrator.worker_pool.pool import WorkerPool


def _make_config() -> ProjectConfig:
    return ProjectConfig(name="test", tdd=TDDConfig(prefix="T"))


class TestResumeCliFlag:
    """Tests for --resume CLI flag wiring."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_run_help_shows_resume_flag(self, runner: CliRunner) -> None:
        """--resume appears in run --help output."""
        result = runner.invoke(cli, ["run", "--help"])
        assert "--resume" in result.output

    def test_resume_flag_passes_through(
        self, runner: CliRunner, tmp_path: Path,
    ) -> None:
        """--resume flag is passed through to _run_async."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ) as mock_run_async,
        ):
            runner.invoke(cli, ["run", "-p", "--resume"])

        # resume should be True in the call
        call_kwargs = mock_run_async.call_args
        # positional args: parallel, workers, phase, all_phases, db_path,
        #   slack_webhook, max_invocations, local, single_branch, no_phase_gates, resume
        assert call_kwargs[0][-1] is True  # resume is last positional arg


class TestResumeWorkerPool:
    """Tests for resume logic in WorkerPool."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.cleanup_stale_claims = AsyncMock(return_value=0)
        db.start_execution_run = AsyncMock(return_value=1)
        db.get_claimable_tasks = AsyncMock(return_value=[])
        db.complete_execution_run = AsyncMock()
        db.get_invocation_count = AsyncMock(return_value=0)
        return db

    @pytest.fixture
    def pool(self, mock_db: AsyncMock, tmp_path: Path) -> WorkerPool:
        return WorkerPool(db=mock_db, base_dir=tmp_path)

    async def test_resume_calls_cleanup_stale_claims(
        self, pool: WorkerPool, mock_db: AsyncMock,
    ) -> None:
        """resume=True triggers cleanup_stale_claims."""
        await pool.run_parallel_phase(phase=0, resume=True)
        mock_db.cleanup_stale_claims.assert_called_once()

    async def test_no_resume_skips_cleanup(
        self, pool: WorkerPool, mock_db: AsyncMock,
    ) -> None:
        """resume=False does not call cleanup_stale_claims at start."""
        await pool.run_parallel_phase(phase=0, resume=False)
        # No tasks → early return before the existing cleanup in the body.
        # cleanup_stale_claims should NOT be called at all.
        mock_db.cleanup_stale_claims.assert_not_called()

    async def test_resume_with_recovered_tasks(
        self, pool: WorkerPool, mock_db: AsyncMock,
    ) -> None:
        """resume=True with stale tasks recovers them."""
        mock_db.cleanup_stale_claims.return_value = 3
        await pool.run_parallel_phase(phase=0, resume=True)
        # Called once at start for resume (no tasks → early return before body cleanup)
        assert mock_db.cleanup_stale_claims.call_count == 1

    async def test_run_all_phases_resume_only_first_phase(
        self, pool: WorkerPool, mock_db: AsyncMock,
    ) -> None:
        """run_all_phases with resume=True cleans up on first phase only."""
        mock_db.get_pending_phases = AsyncMock(return_value=[0, 1])
        mock_db.cleanup_stale_claims.return_value = 0

        with patch.object(pool, "_run_phase_gate", return_value=True):
            with patch.object(pool, "_run_end_of_run_validation", return_value=True):
                await pool.run_all_phases(resume=True)

        # cleanup_stale_claims called once for resume on first phase,
        # not called again on second phase (resume=False)
        # Both phases have no tasks → early return before body cleanup
        calls = mock_db.cleanup_stale_claims.call_count
        assert calls == 1  # Only the resume cleanup on first phase

    async def test_resume_exits_cleanly_when_nothing_stale(
        self, pool: WorkerPool, mock_db: AsyncMock,
    ) -> None:
        """resume=True with 0 stale tasks still works."""
        mock_db.cleanup_stale_claims.return_value = 0
        result = await pool.run_parallel_phase(phase=0, resume=True)
        assert result.stopped_reason == "no_tasks"
