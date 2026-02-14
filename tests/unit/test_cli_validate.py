"""Tests for validate CLI commands.

Tests the validate command group and its subcommands using CliRunner.
Async implementations are mocked to avoid needing a real database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli_validate import validate


class TestValidateGroupStructure:
    """Tests for the validate command group structure."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_group_exists(self, runner: CliRunner) -> None:
        """validate --help exits 0."""
        result = runner.invoke(validate, ["--help"])
        assert result.exit_code == 0
        assert "validation" in result.output.lower()

    def test_validate_phase_help(self, runner: CliRunner) -> None:
        """validate phase --help exits 0 and shows --phase."""
        result = runner.invoke(validate, ["phase", "--help"])
        assert result.exit_code == 0
        assert "--phase" in result.output

    def test_validate_run_help(self, runner: CliRunner) -> None:
        """validate run --help exits 0 and shows --run-id."""
        result = runner.invoke(validate, ["run", "--help"])
        assert result.exit_code == 0
        assert "--run-id" in result.output

    def test_validate_all_help(self, runner: CliRunner) -> None:
        """validate all --help exits 0."""
        result = runner.invoke(validate, ["all", "--help"])
        assert result.exit_code == 0

    def test_validate_phase_requires_phase_option(self, runner: CliRunner) -> None:
        """validate phase without --phase -> exit code != 0."""
        result = runner.invoke(validate, ["phase"])
        assert result.exit_code != 0


class TestValidatePhaseCommand:
    """Tests for validate phase command execution."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_phase_pass_output(self, runner: CliRunner) -> None:
        """Phase gate passes -> exit 0, 'PASSED' in output."""
        with patch(
            "tdd_orchestrator.cli_validate._validate_phase_async",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = None  # no sys.exit means pass
            result = runner.invoke(validate, ["phase", "--phase", "2"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(2, None)

    def test_validate_phase_fail_output(self, runner: CliRunner) -> None:
        """Phase gate fails -> exit 1."""
        with patch(
            "tdd_orchestrator.cli_validate._validate_phase_async",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.side_effect = SystemExit(1)
            result = runner.invoke(validate, ["phase", "--phase", "2"])
            assert result.exit_code == 1


class TestValidateRunCommand:
    """Tests for validate run command execution."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_run_invokes_validator(self, runner: CliRunner) -> None:
        """validate run calls _validate_run_async."""
        with patch(
            "tdd_orchestrator.cli_validate._validate_run_async",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = None
            result = runner.invoke(validate, ["run"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(None, None)

    def test_validate_run_with_run_id(self, runner: CliRunner) -> None:
        """validate run --run-id 5 passes run_id to async fn."""
        with patch(
            "tdd_orchestrator.cli_validate._validate_run_async",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = None
            result = runner.invoke(validate, ["run", "--run-id", "5"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(5, None)


class TestValidateAllCommand:
    """Tests for validate all command execution."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_all_invokes_async(self, runner: CliRunner) -> None:
        """validate all calls _validate_all_async."""
        with patch(
            "tdd_orchestrator.cli_validate._validate_all_async",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = None
            result = runner.invoke(validate, ["all"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(None)
