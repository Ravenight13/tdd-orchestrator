"""Unit tests for pipeline extraction (run_tdd_pipeline, _run_green_with_retry).

Tests exercise the extracted functions with mocked dependencies,
following the pattern from test_verify_only.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool.circuit_breakers import StaticReviewCircuitBreaker
from tdd_orchestrator.worker_pool.pipeline import (
    PipelineContext,
    _run_green_with_retry,
    run_tdd_pipeline,
)


def _make_ctx(
    tmp_path: Path,
    *,
    run_stage: AsyncMock | None = None,
) -> PipelineContext:
    """Build a PipelineContext with an in-memory AsyncMock db."""
    db = AsyncMock()
    db.get_successful_attempt = AsyncMock(return_value=None)
    db.get_config_int = AsyncMock(side_effect=lambda key, default: default)
    db.record_stage_attempt = AsyncMock()
    db.mark_task_failing = AsyncMock()
    return PipelineContext(
        db=db,
        base_dir=tmp_path,
        worker_id=1,
        run_id=1,
        static_review_circuit_breaker=StaticReviewCircuitBreaker(),
        run_stage=run_stage or AsyncMock(),
    )


def _make_task(task_key: str = "TDD-PIPE-01") -> dict[str, Any]:
    """Build a minimal task dict for pipeline tests."""
    return {
        "id": 1,
        "task_key": task_key,
        "title": "Pipeline test task",
        "test_file": "tests/test_pipe.py",
        "impl_file": "src/pipe.py",
        "acceptance_criteria": "pass all checks",
        "complexity": "medium",
    }


def _ok(stage: Stage) -> StageResult:
    return StageResult(stage=stage, success=True, output="ok")


def _fail(stage: Stage) -> StageResult:
    return StageResult(stage=stage, success=False, output="fail", error="err")


# ---------------------------------------------------------------------------
# run_tdd_pipeline tests
# ---------------------------------------------------------------------------


@patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", False)
async def test_returns_false_without_sdk(tmp_path: Path) -> None:
    """Pipeline returns False when SDK is not available."""
    ctx = _make_ctx(tmp_path)
    result = await run_tdd_pipeline(ctx, _make_task())
    assert result is False


@patch("tdd_orchestrator.worker_pool.pipeline.commit_stage", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.run_ruff_fix", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.run_static_review", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.discover_test_file", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline._run_green_with_retry", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.run_verify_only_pipeline", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
async def test_delegates_to_verify_only(
    mock_verify_only: AsyncMock,
    mock_green_retry: AsyncMock,
    mock_discover: AsyncMock,
    mock_review: AsyncMock,
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    tmp_path: Path,
) -> None:
    """verify-only tasks delegate to run_verify_only_pipeline."""
    mock_verify_only.return_value = True
    ctx = _make_ctx(tmp_path)
    task = _make_task()
    task["task_type"] = "verify-only"

    result = await run_tdd_pipeline(ctx, task)
    assert result is True
    mock_verify_only.assert_called_once()
    mock_green_retry.assert_not_called()


@patch("tdd_orchestrator.worker_pool.pipeline.check_needs_refactor", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.commit_stage", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.run_ruff_fix", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.run_static_review", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.discover_test_file", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline._run_green_with_retry", new_callable=AsyncMock)
@patch("tdd_orchestrator.worker_pool.pipeline.HAS_AGENT_SDK", True)
async def test_happy_path_red_green_verify(
    mock_green_retry: AsyncMock,
    mock_discover: AsyncMock,
    mock_review: AsyncMock,
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    mock_refactor_check: AsyncMock,
    tmp_path: Path,
) -> None:
    """RED -> GREEN -> VERIFY succeeds without REFACTOR."""
    from tdd_orchestrator.ast_checker.models import ASTCheckResult
    from tdd_orchestrator.refactor_checker import RefactorCheck

    mock_review.return_value = ASTCheckResult(violations=[], is_blocking=False)
    mock_discover.return_value = "tests/test_pipe.py"
    mock_green_retry.return_value = _ok(Stage.GREEN)
    mock_refactor_check.return_value = RefactorCheck(needs_refactor=False)

    stages_called: list[Stage] = []

    async def _run_stage(stage: Stage, task: Any, **kw: Any) -> StageResult:
        stages_called.append(stage)
        return _ok(stage)

    ctx = _make_ctx(tmp_path, run_stage=AsyncMock(side_effect=_run_stage))
    result = await run_tdd_pipeline(ctx, _make_task())

    assert result is True
    assert Stage.RED in stages_called
    assert Stage.VERIFY in stages_called


# ---------------------------------------------------------------------------
# _run_green_with_retry tests
# ---------------------------------------------------------------------------


async def test_green_retry_succeeds_first_attempt(tmp_path: Path) -> None:
    """GREEN succeeds on first attempt, returns success."""
    run_stage = AsyncMock(return_value=_ok(Stage.GREEN))
    ctx = _make_ctx(tmp_path, run_stage=run_stage)

    result = await _run_green_with_retry(ctx, _make_task(), test_output="test fails")

    assert result.success is True
    assert run_stage.call_count == 1


@patch("tdd_orchestrator.worker_pool.pipeline.ESCALATION_MODEL", "claude-opus-test")
async def test_green_retry_escalates_on_failure(tmp_path: Path) -> None:
    """Second GREEN attempt uses escalation model."""
    run_stage = AsyncMock(side_effect=[_fail(Stage.GREEN), _ok(Stage.GREEN)])
    ctx = _make_ctx(tmp_path, run_stage=run_stage)
    ctx.db.get_config_int = AsyncMock(side_effect=lambda key, default: default)

    result = await _run_green_with_retry(ctx, _make_task(), test_output="test fails")

    assert result.success is True
    assert run_stage.call_count == 2
    # Second call should have model_override
    second_call_kwargs = run_stage.call_args_list[1]
    assert second_call_kwargs.kwargs.get("model_override") == "claude-opus-test"


async def test_green_retry_returns_failure_after_max_attempts(tmp_path: Path) -> None:
    """All GREEN attempts fail -> returns failed StageResult."""
    run_stage = AsyncMock(return_value=_fail(Stage.GREEN))
    ctx = _make_ctx(tmp_path, run_stage=run_stage)

    result = await _run_green_with_retry(ctx, _make_task(), test_output="test fails")

    assert result.success is False
    # Default max_green_attempts is 2
    assert run_stage.call_count == 2
