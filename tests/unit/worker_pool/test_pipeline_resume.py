"""Tests for pipeline stage resume logic.

Covers the _should_skip_stage helper and resume integration with
run_tdd_pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool.pipeline import (
    PipelineContext,
    _should_skip_stage,
    run_tdd_pipeline,
)


class TestShouldSkipStage:
    """Tests for the _should_skip_stage helper."""

    def test_none_resume_skips_nothing(self) -> None:
        """No resume means no skipping."""
        assert _should_skip_stage(None, "red") is False
        assert _should_skip_stage(None, "green") is False
        assert _should_skip_stage(None, "verify") is False

    def test_resume_from_red_skips_red(self) -> None:
        """Resume from red skips the red stage."""
        assert _should_skip_stage("red", "red") is True

    def test_resume_from_red_does_not_skip_green(self) -> None:
        """Resume from red does NOT skip green."""
        assert _should_skip_stage("red", "green") is False

    def test_resume_from_green_skips_red_and_green(self) -> None:
        """Resume from green skips both red and green."""
        assert _should_skip_stage("green", "red") is True
        assert _should_skip_stage("green", "green") is True

    def test_resume_from_green_does_not_skip_verify(self) -> None:
        """Resume from green does NOT skip verify."""
        assert _should_skip_stage("green", "verify") is False

    def test_resume_from_verify_caps_at_verify(self) -> None:
        """Resume from verify or later caps at verify (re-runs verify)."""
        # verify itself is skipped (idx <= effective_resume)
        assert _should_skip_stage("verify", "verify") is True
        # But fix/re_verify/refactor are NOT skipped
        assert _should_skip_stage("verify", "fix") is False
        assert _should_skip_stage("verify", "re_verify") is False

    def test_resume_from_fix_caps_at_verify(self) -> None:
        """Resume from fix still caps at verify."""
        assert _should_skip_stage("fix", "verify") is True
        assert _should_skip_stage("fix", "fix") is False

    def test_unknown_stage_returns_false(self) -> None:
        """Unknown stage names return False (no skip)."""
        assert _should_skip_stage("unknown", "red") is False
        assert _should_skip_stage("red", "unknown") is False

    def test_resume_from_red_fix_skips_red_and_red_fix(self) -> None:
        """Resume from red_fix skips red and red_fix."""
        assert _should_skip_stage("red_fix", "red") is True
        assert _should_skip_stage("red_fix", "red_fix") is True
        assert _should_skip_stage("red_fix", "green") is False


def _make_ctx(
    run_stage: AsyncMock | None = None,
) -> PipelineContext:
    """Create a minimal PipelineContext for testing."""
    db = AsyncMock()
    db.get_successful_attempt = AsyncMock(return_value=None)
    db.mark_task_failing = AsyncMock()
    db.update_task_status = AsyncMock()
    db.update_task_test_file = AsyncMock()
    db.get_config_int = AsyncMock(return_value=1)

    if run_stage is None:
        run_stage = AsyncMock(
            return_value=StageResult(
                stage=Stage.VERIFY, success=True, output="OK", error=None
            )
        )

    return PipelineContext(
        db=db,
        base_dir=MagicMock(),
        worker_id=1,
        run_id=1,
        static_review_circuit_breaker=MagicMock(),
        run_stage=run_stage,
    )


def _make_task() -> dict[str, object]:
    """Create a minimal task dict."""
    return {
        "id": 1,
        "task_key": "T-01",
        "title": "Test task",
        "test_file": "tests/test_foo.py",
        "impl_file": "src/foo.py",
        "task_type": "implement",
        "complexity": "medium",
    }


class TestRunTddPipelineResume:
    """Tests for run_tdd_pipeline with resume_from_stage."""

    @patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
    @patch("tdd_orchestrator.worker_pool.pipeline.commit_stage", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.run_ruff_fix", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.check_needs_refactor")
    async def test_resume_none_runs_full_pipeline(
        self,
        mock_refactor: MagicMock,
        mock_ruff: AsyncMock,
        mock_commit: AsyncMock,
    ) -> None:
        """No resume runs the full pipeline (RED + GREEN + VERIFY)."""
        mock_refactor.return_value = MagicMock(needs_refactor=False)

        run_stage = AsyncMock(
            return_value=StageResult(
                stage=Stage.RED, success=True, output="test output", error=None,
                pre_implemented=False,
            )
        )
        ctx = _make_ctx(run_stage)
        task = _make_task()

        with patch("tdd_orchestrator.worker_pool.pipeline.discover_test_file",
                    new_callable=AsyncMock, return_value="tests/test_foo.py"):
            with patch("tdd_orchestrator.worker_pool.pipeline.run_static_review",
                       new_callable=AsyncMock) as mock_review:
                mock_review.return_value = MagicMock(is_blocking=False)
                result = await run_tdd_pipeline(ctx, task, resume_from_stage=None)

        assert result is True
        # RED, GREEN, and VERIFY stages should all be called
        stage_calls = [call.args[0] for call in run_stage.call_args_list]
        assert Stage.RED in stage_calls
        assert Stage.GREEN in stage_calls
        assert Stage.VERIFY in stage_calls

    @patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
    @patch("tdd_orchestrator.worker_pool.pipeline.commit_stage", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.run_ruff_fix", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.check_needs_refactor")
    async def test_resume_from_red_skips_red(
        self,
        mock_refactor: MagicMock,
        mock_ruff: AsyncMock,
        mock_commit: AsyncMock,
    ) -> None:
        """Resume from red skips RED and static review, runs GREEN+VERIFY."""
        mock_refactor.return_value = MagicMock(needs_refactor=False)

        run_stage = AsyncMock(
            return_value=StageResult(
                stage=Stage.GREEN, success=True, output="impl", error=None,
            )
        )
        ctx = _make_ctx(run_stage)
        task = _make_task()

        result = await run_tdd_pipeline(ctx, task, resume_from_stage="red")

        assert result is True
        stage_calls = [call.args[0] for call in run_stage.call_args_list]
        assert Stage.RED not in stage_calls
        assert Stage.GREEN in stage_calls
        assert Stage.VERIFY in stage_calls

    @patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
    @patch("tdd_orchestrator.worker_pool.pipeline.commit_stage", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.run_ruff_fix", new_callable=AsyncMock)
    @patch("tdd_orchestrator.worker_pool.pipeline.check_needs_refactor")
    async def test_resume_from_green_skips_red_and_green(
        self,
        mock_refactor: MagicMock,
        mock_ruff: AsyncMock,
        mock_commit: AsyncMock,
    ) -> None:
        """Resume from green skips RED+GREEN, runs VERIFY."""
        mock_refactor.return_value = MagicMock(needs_refactor=False)

        run_stage = AsyncMock(
            return_value=StageResult(
                stage=Stage.VERIFY, success=True, output="OK", error=None,
            )
        )
        ctx = _make_ctx(run_stage)
        task = _make_task()

        result = await run_tdd_pipeline(ctx, task, resume_from_stage="green")

        assert result is True
        stage_calls = [call.args[0] for call in run_stage.call_args_list]
        assert Stage.RED not in stage_calls
        assert Stage.GREEN not in stage_calls
        assert Stage.VERIFY in stage_calls

    @patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
    async def test_verify_only_task_ignores_resume(self) -> None:
        """Verify-only tasks bypass resume logic entirely."""
        run_stage = AsyncMock(
            return_value=StageResult(
                stage=Stage.VERIFY, success=True, output="OK", error=None,
            )
        )
        ctx = _make_ctx(run_stage)
        task = _make_task()
        task["task_type"] = "verify-only"

        with patch("tdd_orchestrator.worker_pool.pipeline.run_verify_only_pipeline",
                    new_callable=AsyncMock, return_value=True):
            with patch("tdd_orchestrator.worker_pool.pipeline._run_post_verify_checks",
                       new_callable=AsyncMock):
                result = await run_tdd_pipeline(ctx, task, resume_from_stage="red")

        assert result is True
        # run_stage should NOT be called (verify_only_pipeline handles it)
        # The point is: the resume_from_stage is ignored for verify-only tasks
