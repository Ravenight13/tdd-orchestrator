"""Tests for pre-implemented task detection in RED stage.

Exercises verify_stage_result() for RED stage with three branches:
1. Tests fail (classic TDD) -> success, pre_implemented=False
2. Tests pass + impl_file exists -> success, pre_implemented=True
3. Tests pass + no impl_file -> failure
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tdd_orchestrator.models import Stage, StageResult
from tdd_orchestrator.worker_pool.stage_verifier import verify_stage_result


def _make_task(
    task_id: int = 1,
    task_key: str = "TEST-TDD-01-01",
    test_file: str = "tests/test_foo.py",
    impl_file: str = "src/foo.py",
) -> dict[str, Any]:
    """Create a minimal task dict for testing."""
    return {
        "id": task_id,
        "task_key": task_key,
        "test_file": test_file,
        "impl_file": impl_file,
    }


def _make_db() -> AsyncMock:
    """Create a mock OrchestratorDB."""
    db = AsyncMock()
    db.record_stage_attempt = AsyncMock(return_value=1)
    return db


def _make_verifier(pytest_passes: bool) -> MagicMock:
    """Create a mock CodeVerifier with configurable pytest result."""
    verifier = MagicMock()
    verifier.run_pytest = AsyncMock(return_value=(pytest_passes, "test output"))
    return verifier


async def test_red_classic_tdd_tests_fail(tmp_path: Path) -> None:
    """When pytest fails, RED succeeds (classic TDD)."""
    task = _make_task(test_file="tests/test_foo.py")
    db = _make_db()
    verifier = _make_verifier(pytest_passes=False)

    # Create the test file on disk (required by guard)
    test_path = tmp_path / "tests" / "test_foo.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_something(): assert False")

    result = await verify_stage_result(
        Stage.RED, task, "", db, verifier, base_dir=tmp_path,
    )

    assert result.success is True
    assert result.pre_implemented is False
    db.record_stage_attempt.assert_called_once_with(
        task_id=1, stage="red", attempt_number=1, success=True, pytest_exit_code=1,
    )


async def test_red_pre_implemented_tests_pass_impl_exists(tmp_path: Path) -> None:
    """When pytest passes AND impl_file exists, mark pre-implemented."""
    task = _make_task(test_file="tests/test_foo.py", impl_file="src/foo.py")
    db = _make_db()
    verifier = _make_verifier(pytest_passes=True)

    # Create both test file and impl file on disk
    test_path = tmp_path / "tests" / "test_foo.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_something(): assert True")

    impl_path = tmp_path / "src" / "foo.py"
    impl_path.parent.mkdir(parents=True, exist_ok=True)
    impl_path.write_text("def foo(): return True")

    result = await verify_stage_result(
        Stage.RED, task, "", db, verifier, base_dir=tmp_path,
    )

    assert result.success is True
    assert result.pre_implemented is True
    db.record_stage_attempt.assert_called_once_with(
        task_id=1, stage="red", attempt_number=1, success=True, pytest_exit_code=0,
    )


async def test_red_failure_tests_pass_no_impl_file(tmp_path: Path) -> None:
    """When pytest passes but impl_file does NOT exist, RED fails."""
    task = _make_task(test_file="tests/test_foo.py", impl_file="src/foo.py")
    db = _make_db()
    verifier = _make_verifier(pytest_passes=True)

    # Create test file but NOT impl file
    test_path = tmp_path / "tests" / "test_foo.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_something(): assert True")

    result = await verify_stage_result(
        Stage.RED, task, "", db, verifier, base_dir=tmp_path,
    )

    assert result.success is False
    assert result.pre_implemented is False
    assert result.error is not None
    assert "RED tests passed without implementation" in result.error


async def test_red_failure_tests_pass_no_impl_file_specified(tmp_path: Path) -> None:
    """When pytest passes and impl_file is empty string, RED fails."""
    task = _make_task(test_file="tests/test_foo.py", impl_file="")
    db = _make_db()
    verifier = _make_verifier(pytest_passes=True)

    # Create test file
    test_path = tmp_path / "tests" / "test_foo.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_something(): assert True")

    result = await verify_stage_result(
        Stage.RED, task, "", db, verifier, base_dir=tmp_path,
    )

    assert result.success is False
    assert result.pre_implemented is False
    assert result.error is not None


async def test_red_test_file_missing(tmp_path: Path) -> None:
    """When test file doesn't exist, RED fails (unchanged behavior)."""
    task = _make_task(test_file="tests/nonexistent.py")
    db = _make_db()
    verifier = _make_verifier(pytest_passes=False)

    result = await verify_stage_result(
        Stage.RED, task, "", db, verifier, base_dir=tmp_path,
    )

    assert result.success is False
    assert result.pre_implemented is False
    assert "Test file not found" in (result.output or "")
