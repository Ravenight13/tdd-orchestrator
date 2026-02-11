"""Tests for verify-only pipeline.

Exercises run_verify_only_pipeline() with mocked run_stage callable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool.verify_only import run_verify_only_pipeline


def _make_task(
    task_key: str = "TEST-TDD-02-01",
    impl_file: str = "src/foo.py",
) -> dict[str, Any]:
    """Create a minimal task dict for testing."""
    return {
        "id": 1,
        "task_key": task_key,
        "test_file": "tests/test_foo.py",
        "impl_file": impl_file,
    }


@patch(
    "tdd_orchestrator.worker_pool.verify_only.commit_stage",
    new_callable=AsyncMock,
    return_value=True,
)
@patch(
    "tdd_orchestrator.worker_pool.verify_only.run_ruff_fix",
    new_callable=AsyncMock,
    return_value=True,
)
async def test_verify_only_passes(
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    tmp_path: Path,
) -> None:
    """VERIFY succeeds on first try -> returns True, commits."""
    run_stage = AsyncMock(
        return_value=StageResult(stage=Stage.VERIFY, success=True, output="ok"),
    )

    result = await run_verify_only_pipeline(
        task=_make_task(), run_stage=run_stage, base_dir=tmp_path,
    )

    assert result is True
    run_stage.assert_called_once_with(Stage.VERIFY, _make_task())
    mock_commit.assert_called_once()
    mock_ruff.assert_called_once()


@patch(
    "tdd_orchestrator.worker_pool.verify_only.commit_stage",
    new_callable=AsyncMock,
    return_value=True,
)
@patch(
    "tdd_orchestrator.worker_pool.verify_only.run_ruff_fix",
    new_callable=AsyncMock,
    return_value=True,
)
async def test_verify_only_fix_then_pass(
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    tmp_path: Path,
) -> None:
    """VERIFY fails with issues -> FIX -> RE_VERIFY passes -> True."""
    issues = [{"tool": "mypy", "output": "error: missing type"}]

    run_stage = AsyncMock(side_effect=[
        # VERIFY fails
        StageResult(stage=Stage.VERIFY, success=False, output="fail", issues=issues),
        # FIX succeeds
        StageResult(stage=Stage.FIX, success=True, output="fixed"),
        # RE_VERIFY passes
        StageResult(stage=Stage.RE_VERIFY, success=True, output="ok"),
    ])

    result = await run_verify_only_pipeline(
        task=_make_task(), run_stage=run_stage, base_dir=tmp_path,
    )

    assert result is True
    assert run_stage.call_count == 3
    # Two commits: FIX and RE_VERIFY
    assert mock_commit.call_count == 2


@patch(
    "tdd_orchestrator.worker_pool.verify_only.commit_stage",
    new_callable=AsyncMock,
    return_value=True,
)
@patch(
    "tdd_orchestrator.worker_pool.verify_only.run_ruff_fix",
    new_callable=AsyncMock,
    return_value=True,
)
async def test_verify_only_fix_fails(
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    tmp_path: Path,
) -> None:
    """VERIFY fails -> FIX fails -> returns False."""
    issues = [{"tool": "pytest", "output": "tests failed"}]

    run_stage = AsyncMock(side_effect=[
        # VERIFY fails
        StageResult(stage=Stage.VERIFY, success=False, output="fail", issues=issues),
        # FIX fails
        StageResult(stage=Stage.FIX, success=False, output="", error="fix failed"),
    ])

    result = await run_verify_only_pipeline(
        task=_make_task(), run_stage=run_stage, base_dir=tmp_path,
    )

    assert result is False
    assert run_stage.call_count == 2


@patch(
    "tdd_orchestrator.worker_pool.verify_only.commit_stage",
    new_callable=AsyncMock,
    return_value=True,
)
@patch(
    "tdd_orchestrator.worker_pool.verify_only.run_ruff_fix",
    new_callable=AsyncMock,
    return_value=True,
)
async def test_verify_only_no_issues(
    mock_ruff: AsyncMock,
    mock_commit: AsyncMock,
    tmp_path: Path,
) -> None:
    """VERIFY fails with no issues -> returns False (cannot FIX)."""
    run_stage = AsyncMock(
        return_value=StageResult(
            stage=Stage.VERIFY, success=False, output="fail", issues=None,
        ),
    )

    result = await run_verify_only_pipeline(
        task=_make_task(), run_stage=run_stage, base_dir=tmp_path,
    )

    assert result is False
    run_stage.assert_called_once()
