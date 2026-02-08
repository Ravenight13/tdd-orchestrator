"""Unit tests for static review missing-file guards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from tdd_orchestrator.ast_checker import ASTCheckResult, ASTViolation
from tdd_orchestrator.worker_pool.circuit_breakers import StaticReviewCircuitBreaker
from tdd_orchestrator.worker_pool.review import run_static_review


def _make_task(test_file: str = "tests/unit/test_foo.py") -> dict[str, object]:
    """Create a minimal task dict for testing."""
    return {
        "id": 1,
        "task_key": "TEST-01",
        "test_file": test_file,
    }


async def test_empty_test_file_returns_empty_result(tmp_path: Path) -> None:
    """Empty test_file skips review entirely."""
    task = _make_task(test_file="")
    cb = StaticReviewCircuitBreaker()
    db = AsyncMock()

    result = await run_static_review(task, tmp_path, cb, db, run_id=1)

    assert isinstance(result, ASTCheckResult)
    assert result.violations == []
    assert result.file_path == ""


async def test_missing_test_file_returns_empty_result(tmp_path: Path) -> None:
    """Non-existent test file skips review (non-blocking)."""
    task = _make_task(test_file="tests/unit/test_nonexistent.py")
    cb = StaticReviewCircuitBreaker()
    db = AsyncMock()

    result = await run_static_review(task, tmp_path, cb, db, run_id=1)

    assert isinstance(result, ASTCheckResult)
    assert result.violations == []
    assert result.file_path == "tests/unit/test_nonexistent.py"


async def test_existing_file_runs_checks(tmp_path: Path) -> None:
    """Existing test file proceeds to actual AST checks."""
    # Create the test file
    test_dir = tmp_path / "tests" / "unit"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_foo.py"
    test_file.write_text("def test_example():\n    assert True\n")

    task = _make_task(test_file="tests/unit/test_foo.py")
    cb = StaticReviewCircuitBreaker()
    db = AsyncMock()
    db.log_static_review_metric = AsyncMock()

    expected_result = ASTCheckResult(violations=[], file_path=str(test_file))

    with patch(
        "tdd_orchestrator.worker_pool.review.ASTQualityChecker"
    ) as mock_checker_cls, patch(
        "tdd_orchestrator.worker_pool.review.verify_pytest_collection",
        new_callable=AsyncMock,
        return_value=(True, ""),
    ):
        mock_checker = MagicMock()
        mock_checker.check_file = AsyncMock(return_value=expected_result)
        mock_checker_cls.return_value = mock_checker

        result = await run_static_review(task, tmp_path, cb, db, run_id=1)

    assert isinstance(result, ASTCheckResult)
    mock_checker.check_file.assert_called_once()
