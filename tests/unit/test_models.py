"""Tests for orchestrator domain models.

This module tests the Stage enum and VerifyResult dataclass from the
orchestrator models, ensuring correct values and behavior.
"""

from __future__ import annotations

from tdd_orchestrator.models import Stage, VerifyResult


class TestStage:
    """Test class for Stage enum."""

    def test_stage_red_value(self) -> None:
        """Test that Stage.RED has correct string value 'red'."""
        assert Stage.RED.value == "red"

    def test_stage_green_value(self) -> None:
        """Test that Stage.GREEN has correct string value 'green'."""
        assert Stage.GREEN.value == "green"

    def test_stage_verify_value(self) -> None:
        """Test that Stage.VERIFY has correct string value 'verify'."""
        assert Stage.VERIFY.value == "verify"

    def test_stage_fix_value(self) -> None:
        """Test that Stage.FIX has correct string value 'fix'."""
        assert Stage.FIX.value == "fix"

    def test_stage_re_verify_value(self) -> None:
        """Test that Stage.RE_VERIFY has correct string value 're_verify'."""
        assert Stage.RE_VERIFY.value == "re_verify"

    def test_all_stages_defined(self) -> None:
        """Test that all expected stages exist in the enum."""
        stages = [s.value for s in Stage]
        assert "red" in stages
        assert "green" in stages
        assert "verify" in stages
        assert "fix" in stages
        assert "re_verify" in stages

    def test_stage_count(self) -> None:
        """Test that Stage enum has exactly 5 stages."""
        assert len(Stage) == 5


class TestVerifyResult:
    """Test class for VerifyResult dataclass."""

    def test_all_passed_returns_true_when_all_tools_pass(self) -> None:
        """Test all_passed property returns True when pytest, ruff, and mypy all pass."""
        result = VerifyResult(
            pytest_passed=True,
            pytest_output="1 passed",
            ruff_passed=True,
            ruff_output="All checks passed",
            mypy_passed=True,
            mypy_output="Success: no issues found",
        )
        assert result.all_passed is True

    def test_all_passed_returns_false_when_pytest_fails(self) -> None:
        """Test all_passed property returns False when pytest fails."""
        result = VerifyResult(
            pytest_passed=False,
            pytest_output="1 failed",
            ruff_passed=True,
            ruff_output="All checks passed",
            mypy_passed=True,
            mypy_output="Success: no issues found",
        )
        assert result.all_passed is False

    def test_all_passed_returns_false_when_ruff_fails(self) -> None:
        """Test all_passed property returns False when ruff fails."""
        result = VerifyResult(
            pytest_passed=True,
            pytest_output="1 passed",
            ruff_passed=False,
            ruff_output="E501 line too long",
            mypy_passed=True,
            mypy_output="Success: no issues found",
        )
        assert result.all_passed is False

    def test_all_passed_returns_false_when_mypy_fails(self) -> None:
        """Test all_passed property returns False when mypy fails."""
        result = VerifyResult(
            pytest_passed=True,
            pytest_output="1 passed",
            ruff_passed=True,
            ruff_output="All checks passed",
            mypy_passed=False,
            mypy_output="error: Incompatible types",
        )
        assert result.all_passed is False

    def test_all_passed_returns_false_when_multiple_tools_fail(self) -> None:
        """Test all_passed property returns False when multiple tools fail."""
        result = VerifyResult(
            pytest_passed=False,
            pytest_output="1 failed",
            ruff_passed=False,
            ruff_output="E501 line too long",
            mypy_passed=False,
            mypy_output="error: Incompatible types",
        )
        assert result.all_passed is False

    def test_verify_result_stores_all_outputs(self) -> None:
        """Test that VerifyResult stores all tool outputs correctly."""
        pytest_out = "test output"
        ruff_out = "ruff output"
        mypy_out = "mypy output"

        result = VerifyResult(
            pytest_passed=True,
            pytest_output=pytest_out,
            ruff_passed=True,
            ruff_output=ruff_out,
            mypy_passed=True,
            mypy_output=mypy_out,
        )

        assert result.pytest_output == pytest_out
        assert result.ruff_output == ruff_out
        assert result.mypy_output == mypy_out
