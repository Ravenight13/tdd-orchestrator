"""Tests for RunValidator end-of-run validation.

Verifies blocking checks (regression, lint, type check, orphaned tasks)
and non-blocking checks (import, done_criteria, AC validation).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.worker_pool.run_validator import RunValidationResult, RunValidator


def _make_task(
    *,
    task_key: str = "TDD-01",
    status: str = "complete",
    test_file: str | None = "tests/test_a.py",
    impl_file: str | None = "src/mod/a.py",
    done_criteria: str | None = None,
    module_exports: str = "[]",
) -> dict[str, object]:
    """Build a fake task dict matching DB row structure."""
    return {
        "task_key": task_key,
        "status": status,
        "test_file": test_file,
        "impl_file": impl_file,
        "done_criteria": done_criteria,
        "module_exports": module_exports,
    }


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock OrchestratorDB with get_all_tasks."""
    db = AsyncMock()
    db.get_all_tasks = AsyncMock(return_value=[])
    db.update_run_validation = AsyncMock()
    return db


@pytest.fixture
def validator(mock_db: AsyncMock) -> RunValidator:
    """Create a RunValidator with mocked DB."""
    return RunValidator(mock_db, Path("/tmp/test"))


class TestRunValidationResultDataclass:
    """Tests for RunValidationResult properties."""

    def test_to_json_produces_valid_json(self) -> None:
        """to_json() output can be parsed by json.loads."""
        result = RunValidationResult(
            passed=True,
            regression_passed=True,
            lint_passed=True,
            type_check_passed=True,
            import_check_passed=True,
            orphaned_tasks=[],
            done_criteria_summary="0/0 criteria satisfied",
            ac_validation_summary="",
            errors=[],
        )
        parsed = json.loads(result.to_json())
        assert parsed["passed"] is True
        assert parsed["orphaned_tasks"] == []

    def test_summary_passed(self) -> None:
        """Summary includes 'PASSED' when all checks pass."""
        result = RunValidationResult(
            passed=True,
            regression_passed=True,
            lint_passed=True,
            type_check_passed=True,
            import_check_passed=True,
            orphaned_tasks=[],
            done_criteria_summary="",
            ac_validation_summary="",
            errors=[],
        )
        assert "PASSED" in result.summary

    def test_summary_failed_regression(self) -> None:
        """Summary includes 'regression' when regression fails."""
        result = RunValidationResult(
            passed=False,
            regression_passed=False,
            lint_passed=True,
            type_check_passed=True,
            import_check_passed=True,
            orphaned_tasks=[],
            done_criteria_summary="",
            ac_validation_summary="",
            errors=[],
        )
        assert "FAILED" in result.summary
        assert "regression" in result.summary

    def test_summary_failed_lint(self) -> None:
        """Summary includes 'lint' when lint fails."""
        result = RunValidationResult(
            passed=False,
            regression_passed=True,
            lint_passed=False,
            type_check_passed=True,
            import_check_passed=True,
            orphaned_tasks=[],
            done_criteria_summary="",
            ac_validation_summary="",
            errors=[],
        )
        assert "lint" in result.summary

    def test_summary_failed_orphaned(self) -> None:
        """Summary includes orphaned count when tasks are orphaned."""
        result = RunValidationResult(
            passed=False,
            regression_passed=True,
            lint_passed=True,
            type_check_passed=True,
            import_check_passed=True,
            orphaned_tasks=["TDD-01", "TDD-02"],
            done_criteria_summary="",
            ac_validation_summary="",
            errors=[],
        )
        assert "2 orphaned" in result.summary


class TestRunValidatorEmptyRun:
    """Tests for empty runs (no tasks)."""

    async def test_empty_run_passes(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """No tasks -> passed=True immediately."""
        mock_db.get_all_tasks.return_value = []

        result = await validator.validate_run(1)

        assert result.passed is True
        assert result.regression_passed is True
        assert result.lint_passed is True
        assert result.type_check_passed is True


class TestRunValidatorBlockingChecks:
    """Tests for blocking checks (affect passed status)."""

    async def test_all_checks_pass(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """All blocking + non-blocking pass -> passed=True."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(1)

        assert result.passed is True
        assert result.regression_passed is True
        assert result.lint_passed is True
        assert result.type_check_passed is True
        assert result.orphaned_tasks == []

    async def test_regression_failure_blocks(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Regression fails -> passed=False."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        async def side_effect(*args: str) -> tuple[bool, str]:
            # pytest is the first arg -> fail it; pass ruff/mypy
            if "pytest" in args[0]:
                return False, "FAILED"
            return True, "ok"

        with patch.object(validator, "_run_command", side_effect=side_effect):
            result = await validator.validate_run(1)

        assert result.passed is False
        assert result.regression_passed is False

    async def test_lint_failure_blocks(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Ruff fails -> passed=False."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        async def side_effect(*args: str) -> tuple[bool, str]:
            if "ruff" in args[0]:
                return False, "lint errors"
            return True, "ok"

        with patch.object(validator, "_run_command", side_effect=side_effect):
            result = await validator.validate_run(1)

        assert result.passed is False
        assert result.lint_passed is False

    async def test_type_check_failure_blocks(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Mypy fails -> passed=False."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        async def side_effect(*args: str) -> tuple[bool, str]:
            if "mypy" in args[0]:
                return False, "type errors"
            return True, "ok"

        with patch.object(validator, "_run_command", side_effect=side_effect):
            result = await validator.validate_run(1)

        assert result.passed is False
        assert result.type_check_passed is False

    async def test_orphaned_tasks_blocks(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Pending/blocked tasks -> passed=False, task_keys listed."""
        mock_db.get_all_tasks.return_value = [
            _make_task(task_key="TDD-01", status="complete"),
            _make_task(task_key="TDD-02", status="pending"),
            _make_task(task_key="TDD-03", status="blocked"),
        ]

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(1)

        assert result.passed is False
        assert "TDD-02" in result.orphaned_tasks
        assert "TDD-03" in result.orphaned_tasks
        assert "TDD-01" not in result.orphaned_tasks


class TestRunValidatorNonBlockingChecks:
    """Tests for non-blocking checks (don't affect passed status)."""

    async def test_import_failure_non_blocking(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Import check fails -> passed=True (non-blocking)."""
        mock_db.get_all_tasks.return_value = [
            _make_task(module_exports='["MyClass"]')
        ]

        async def side_effect(*args: str) -> tuple[bool, str]:
            # Fail the import check (python -c), pass everything else
            if args[0].endswith("python") or args[0].endswith("python3"):
                return False, "ImportError"
            return True, "ok"

        with patch.object(validator, "_run_command", side_effect=side_effect):
            result = await validator.validate_run(1)

        assert result.passed is True
        assert result.import_check_passed is False

    async def test_ac_validation_summary_populated(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """AC validation populates summary string in result."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        with (
            patch.object(validator, "_run_command", return_value=(True, "ok")),
            patch(
                "tdd_orchestrator.worker_pool.ac_validator.validate_run_ac",
                return_value="1/2 criteria verifiable, 1/1 verified as satisfied",
            ) as mock_ac,
        ):
            result = await validator.validate_run(1)

        mock_ac.assert_awaited_once()
        assert result.ac_validation_summary == (
            "1/2 criteria verifiable, 1/1 verified as satisfied"
        )

    async def test_ac_validation_does_not_block(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """AC validation issues do not affect result.passed."""
        mock_db.get_all_tasks.return_value = [_make_task()]

        with (
            patch.object(validator, "_run_command", return_value=(True, "ok")),
            patch(
                "tdd_orchestrator.worker_pool.ac_validator.validate_run_ac",
                return_value="0/5 criteria verifiable",
            ),
        ):
            result = await validator.validate_run(1)

        assert result.passed is True


class TestRunValidatorSkippedChecks:
    """Tests for skipping checks when files are missing."""

    async def test_no_test_files_skips_regression(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Tasks without test_files -> regression skipped, passed=True."""
        mock_db.get_all_tasks.return_value = [
            _make_task(test_file=None, impl_file="src/a.py")
        ]

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(1)

        assert result.passed is True
        assert result.regression_passed is True

    async def test_no_impl_files_skips_lint(
        self, validator: RunValidator, mock_db: AsyncMock
    ) -> None:
        """Tasks without impl_files -> lint/type skipped, passed=True."""
        mock_db.get_all_tasks.return_value = [
            _make_task(impl_file=None, test_file="tests/test_a.py")
        ]

        with patch.object(validator, "_run_command", return_value=(True, "ok")):
            result = await validator.validate_run(1)

        assert result.passed is True
        assert result.lint_passed is True
        assert result.type_check_passed is True
