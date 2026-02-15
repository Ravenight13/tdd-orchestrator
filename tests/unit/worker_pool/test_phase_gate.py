"""Tests for PhaseGateValidator.

Validates phase gate logic: prior phase completion checks,
regression test execution, and result reporting.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdd_orchestrator.worker_pool.phase_gate import (
    PhaseGateResult,
    PhaseGateValidator,
    FileTestResult,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock database with phase gate query methods."""
    db = AsyncMock()
    db.get_tasks_in_phases_before = AsyncMock(return_value=[])
    db.get_test_files_from_phases_before = AsyncMock(return_value=[])
    return db


@pytest.fixture
def validator(mock_db: AsyncMock) -> PhaseGateValidator:
    """Create a PhaseGateValidator with mocked DB."""
    return PhaseGateValidator(db=mock_db, base_dir=Path("/tmp/test"))


class TestFirstPhaseGate:
    """Tests for phases with no prior work."""

    async def test_first_phase_passes_immediately(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """No prior tasks -> gate passes immediately."""
        mock_db.get_tasks_in_phases_before.return_value = []

        result = await validator.validate_phase(0)

        assert result.passed is True
        assert result.incomplete_tasks == []
        assert result.regression_results == []


class TestPriorPhaseCompletion:
    """Tests for prior phase task status validation."""

    async def test_all_prior_complete_tests_pass(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """All prior tasks complete + batch passes -> gate passes."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
            {"task_key": "TDD-0B", "status": "passing"},
        ]
        mock_db.get_test_files_from_phases_before.return_value = [
            "tests/test_a.py",
        ]

        with patch.object(
            validator, "_run_batch_regression",
            return_value=(True, [FileTestResult(
                file="tests/test_a.py", passed=True, exit_code=0, output="ok",
            )]),
        ):
            result = await validator.validate_phase(1)

        assert result.passed is True
        assert result.incomplete_tasks == []

    async def test_incomplete_prior_tasks_fails(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Prior has pending task -> fails, no test runs."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
            {"task_key": "TDD-0B", "status": "pending"},
        ]

        result = await validator.validate_phase(1)

        assert result.passed is False
        assert "TDD-0B" in result.incomplete_tasks
        assert result.regression_results == []

    async def test_blocked_prior_task_fails_gate(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Prior has blocked task -> fails."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "blocked"},
        ]

        result = await validator.validate_phase(1)

        assert result.passed is False
        assert "TDD-0A" in result.incomplete_tasks

    async def test_in_progress_prior_task_fails_gate(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Orphaned in_progress task -> fails."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "in_progress"},
        ]

        result = await validator.validate_phase(1)

        assert result.passed is False
        assert "TDD-0A" in result.incomplete_tasks

    async def test_incomplete_tasks_listed(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Returns task_keys of all non-terminal tasks."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
            {"task_key": "TDD-0B", "status": "pending"},
            {"task_key": "TDD-0C", "status": "blocked"},
            {"task_key": "TDD-0D", "status": "blocked-static-review"},
        ]

        result = await validator.validate_phase(1)

        assert result.passed is False
        assert set(result.incomplete_tasks) == {"TDD-0B", "TDD-0C", "TDD-0D"}


class TestRegressionTesting:
    """Tests for regression test execution."""

    async def test_no_prior_test_files_passes(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Prior tasks complete but no test files -> gate passes."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
        ]
        mock_db.get_test_files_from_phases_before.return_value = []

        result = await validator.validate_phase(1)

        assert result.passed is True
        assert result.regression_results == []

    async def test_batch_failure_reruns_individually(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Batch fails -> individual results captured."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
        ]
        mock_db.get_test_files_from_phases_before.return_value = [
            "tests/test_a.py",
            "tests/test_b.py",
        ]

        # Batch fails
        batch_cmd_called = False

        async def mock_run_command(*args: str) -> tuple[bool, str]:
            nonlocal batch_cmd_called
            if not batch_cmd_called:
                batch_cmd_called = True
                return False, "batch failed"
            # Individual runs: first passes, second fails
            if "test_a.py" in args[-1]:
                return True, "ok"
            return False, "test_b failed"

        with patch.object(validator, "_run_command", side_effect=mock_run_command):
            result = await validator.validate_phase(1)

        assert result.passed is False
        assert len(result.regression_results) == 2

    async def test_regression_failure_fails_gate(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Any test file fails -> gate fails."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
        ]
        mock_db.get_test_files_from_phases_before.return_value = [
            "tests/test_a.py",
        ]

        # Batch fails, individual also fails
        with patch.object(
            validator, "_run_command", return_value=(False, "test failed"),
        ):
            result = await validator.validate_phase(1)

        assert result.passed is False
        assert len(result.regression_results) > 0
        assert any(not r.passed for r in result.regression_results)


class TestSummaryFormat:
    """Tests for PhaseGateResult.summary property."""

    async def test_summary_format_passed(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Summary string correct for pass."""
        mock_db.get_tasks_in_phases_before.return_value = []

        result = await validator.validate_phase(0)

        assert "PASSED" in result.summary
        assert "Phase 0" in result.summary

    async def test_summary_format_failed_incomplete(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Summary includes incomplete count."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "pending"},
            {"task_key": "TDD-0B", "status": "blocked"},
        ]

        result = await validator.validate_phase(1)

        assert "FAILED" in result.summary
        assert "2" in result.summary

    async def test_summary_format_failed_regression(
        self, validator: PhaseGateValidator, mock_db: AsyncMock
    ) -> None:
        """Summary includes failed test count."""
        mock_db.get_tasks_in_phases_before.return_value = [
            {"task_key": "TDD-0A", "status": "complete"},
        ]
        mock_db.get_test_files_from_phases_before.return_value = [
            "tests/test_a.py",
        ]

        with patch.object(
            validator, "_run_command", return_value=(False, "failed"),
        ):
            result = await validator.validate_phase(1)

        assert "FAILED" in result.summary
        assert "regression" in result.summary.lower()
