"""Integration tests for REFACTOR stage in the TDD pipeline.

Tests verify that _run_tdd_pipeline correctly invokes (or skips) REFACTOR
based on check_needs_refactor results, handles failures gracefully, and
uses the correct model override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from tdd_orchestrator.ast_checker.models import ASTCheckResult
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.refactor_checker import RefactorCheck
from tdd_orchestrator.worker_pool import Worker, WorkerConfig
from tdd_orchestrator.worker_pool.config import REFACTOR_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_key: str = "TDD-REF-01") -> dict[str, Any]:
    """Build a minimal task dict for pipeline tests."""
    return {
        "id": 1,
        "task_key": task_key,
        "title": "Refactor test task",
        "test_file": "tests/test_ref.py",
        "impl_file": "src/ref.py",
        "acceptance_criteria": "pass all checks",
        "complexity": "medium",
    }


def _ok(stage: Stage) -> StageResult:
    """Return a successful StageResult for *stage*."""
    return StageResult(stage=stage, success=True, output="ok")


def _fail(stage: Stage, issues: list[dict[str, Any]] | None = None) -> StageResult:
    """Return a failed StageResult for *stage*."""
    return StageResult(stage=stage, success=False, output="fail", error="err", issues=issues)


async def _create_worker(db: OrchestratorDB, tmp_path: Path) -> Worker:
    """Create a Worker wired to *db* with mocked git."""
    run_id = await db.start_execution_run(max_workers=1)
    mock_git = MagicMock()
    config = WorkerConfig(single_branch_mode=True)
    return Worker(1, db, mock_git, config, run_id, tmp_path)


# ---------------------------------------------------------------------------
# Shared patch context -- patches module-level imports AND instance methods
# ---------------------------------------------------------------------------

class _PipelineHarness:
    """Async context manager that patches everything _run_tdd_pipeline needs.

    Module-level patches: HAS_AGENT_SDK, commit_stage, run_ruff_fix,
    check_needs_refactor, run_static_review, squash_wip_commits.
    Instance patches: worker._run_stage, worker._run_green_with_retry,
    worker.db.get_successful_attempt.
    """

    def __init__(
        self,
        worker: Worker,
        stage_side_effect: Any,
        refactor_check: RefactorCheck,
    ) -> None:
        self._worker = worker
        self._stage_se = stage_side_effect
        self._refactor_check = refactor_check
        self._patches: list[Any] = []

    async def __aenter__(self) -> "_PipelineHarness":
        static_review = ASTCheckResult(violations=[], is_blocking=False)
        self._patches = [
            patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
            patch("tdd_orchestrator.worker_pool.worker.commit_stage", new_callable=AsyncMock),
            patch("tdd_orchestrator.worker_pool.worker.run_ruff_fix", new_callable=AsyncMock),
            patch(
                "tdd_orchestrator.worker_pool.worker.check_needs_refactor",
                new_callable=AsyncMock, return_value=self._refactor_check,
            ),
            patch(
                "tdd_orchestrator.worker_pool.worker.run_static_review",
                new_callable=AsyncMock, return_value=static_review,
            ),
            patch(
                "tdd_orchestrator.worker_pool.worker.squash_wip_commits",
                new_callable=AsyncMock,
            ),
            patch(
                "tdd_orchestrator.worker_pool.worker.discover_test_file",
                new_callable=AsyncMock, return_value="tests/test_ref.py",
            ),
            patch.object(
                self._worker, "_run_stage",
                new_callable=AsyncMock, side_effect=self._stage_se,
            ),
            patch.object(
                self._worker, "_run_green_with_retry",
                new_callable=AsyncMock, return_value=_ok(Stage.GREEN),
            ),
            patch.object(
                self._worker.db, "get_successful_attempt",
                new_callable=AsyncMock, return_value=None,
            ),
        ]
        for p in self._patches:
            p.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        for p in reversed(self._patches):
            p.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRefactorPipeline:
    """Integration tests for REFACTOR in _run_tdd_pipeline."""

    async def test_pipeline_skips_refactor_when_clean(self, tmp_path: Path) -> None:
        """When check_needs_refactor returns False, REFACTOR is never called."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()
            calls: list[Stage] = []

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                calls.append(stage)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=False)
            async with _PipelineHarness(worker, _se, check):
                result = await worker._run_tdd_pipeline(task)

            assert result is True
            assert Stage.REFACTOR not in calls

    async def test_pipeline_runs_refactor_when_triggered(self, tmp_path: Path) -> None:
        """When check_needs_refactor returns True, REFACTOR stage IS called."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()
            calls: list[Stage] = []

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                calls.append(stage)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=True, reasons=["File too long"])
            async with _PipelineHarness(worker, _se, check):
                result = await worker._run_tdd_pipeline(task)

            assert result is True
            assert Stage.REFACTOR in calls

    async def test_pipeline_reverify_after_refactor(self, tmp_path: Path) -> None:
        """After a successful REFACTOR, RE_VERIFY is called."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()
            calls: list[Stage] = []

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                calls.append(stage)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=True, reasons=["Function too long"])
            async with _PipelineHarness(worker, _se, check):
                result = await worker._run_tdd_pipeline(task)

            assert result is True
            refactor_idx = calls.index(Stage.REFACTOR)
            reverify_idx = calls.index(Stage.RE_VERIFY)
            assert reverify_idx > refactor_idx

    async def test_pipeline_refactor_failure_still_succeeds(
        self, tmp_path: Path
    ) -> None:
        """If REFACTOR fails the pipeline still returns True (best-effort)."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                if stage == Stage.REFACTOR:
                    return _fail(stage)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=True, reasons=["File too long"])
            async with _PipelineHarness(worker, _se, check):
                result = await worker._run_tdd_pipeline(task)

            assert result is True

    async def test_pipeline_fix_after_failed_reverify(self, tmp_path: Path) -> None:
        """If RE_VERIFY fails after REFACTOR, the FIX stage is called."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()
            calls: list[Stage] = []
            reverify_count = 0

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                nonlocal reverify_count
                calls.append(stage)
                if stage == Stage.RE_VERIFY:
                    reverify_count += 1
                    if reverify_count == 1:
                        return _fail(
                            stage, issues=[{"tool": "mypy", "output": "type error"}]
                        )
                    return _ok(stage)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=True, reasons=["Class too many methods"])
            async with _PipelineHarness(worker, _se, check):
                result = await worker._run_tdd_pipeline(task)

            assert result is True
            assert Stage.FIX in calls
            fix_idx = calls.index(Stage.FIX)
            refactor_idx = calls.index(Stage.REFACTOR)
            assert fix_idx > refactor_idx

    async def test_refactor_uses_opus_model(self, tmp_path: Path) -> None:
        """_run_stage is called with model_override=REFACTOR_MODEL for REFACTOR."""
        async with OrchestratorDB(":memory:") as db:
            worker = await _create_worker(db, tmp_path)
            task = _make_task()
            captured_kw: dict[str, Any] = {}

            async def _se(stage: Stage, task: Any, **kw: Any) -> StageResult:
                if stage == Stage.REFACTOR:
                    captured_kw.update(kw)
                return _ok(stage)

            check = RefactorCheck(needs_refactor=True, reasons=["File too long"])
            async with _PipelineHarness(worker, _se, check):
                await worker._run_tdd_pipeline(task)

            assert captured_kw.get("model_override") == REFACTOR_MODEL
