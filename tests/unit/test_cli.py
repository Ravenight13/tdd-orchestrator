"""Tests for orchestrator CLI commands.

This module tests the command-line interface using click.testing.CliRunner
to verify commands, arguments, and error handling.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli


class TestCLI:
    """Test class for CLI command structure."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CliRunner for testing."""
        return CliRunner()

    def test_cli_group_exists(self, runner: CliRunner) -> None:
        """Test that CLI group is defined and callable."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "TDD Orchestrator" in result.output

    def test_status_command_exists(self, runner: CliRunner) -> None:
        """Test that status command is registered."""
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output.lower()

    def test_run_command_exists(self, runner: CliRunner) -> None:
        """Test that run command is registered."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "parallel" in result.output.lower()

    def test_help_displays_commands(self, runner: CliRunner) -> None:
        """Test that help text displays available commands."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "run" in result.output

    def test_invalid_command_fails_gracefully(self, runner: CliRunner) -> None:
        """Test that invalid commands fail with proper error message."""
        result = runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0
        # Click shows error about invalid command

    def test_verbose_flag_accepted(self, runner: CliRunner) -> None:
        """Test that --verbose flag is accepted."""
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0

    def test_run_command_has_parallel_flag(self, runner: CliRunner) -> None:
        """Test that run command has --parallel flag."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--parallel" in result.output or "-p" in result.output

    def test_run_command_has_workers_option(self, runner: CliRunner) -> None:
        """Test that run command has --workers option."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--workers" in result.output or "-w" in result.output

    def test_status_command_has_db_option(self, runner: CliRunner) -> None:
        """Test that status command has --db option."""
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "--db" in result.output

    def test_validate_command_exists(self, runner: CliRunner) -> None:
        """Test that validate command group is registered."""
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "validation" in result.output.lower()

    def test_help_displays_validate(self, runner: CliRunner) -> None:
        """Test that main help includes validate command."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
