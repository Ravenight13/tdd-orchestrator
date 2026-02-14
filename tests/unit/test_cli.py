"""Tests for orchestrator CLI commands.

This module tests the command-line interface using click.testing.CliRunner
to verify commands, arguments, error handling, and auto-discovery.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.project_config import ProjectConfig, TDDConfig


def _make_config(max_workers: int = 2) -> ProjectConfig:
    """Create a ProjectConfig for testing."""
    return ProjectConfig(
        name="test-project", tdd=TDDConfig(prefix="TDD", max_workers=max_workers)
    )


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

    def test_run_workers_help_text(self, runner: CliRunner) -> None:
        """--workers help text mentions config fallback."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "from config or 2" in result.output

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


class TestRunAutoDiscovery:
    """Tests for auto-discovery in run command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_run_auto_discovers_db(self, runner: CliRunner, tmp_path: Path) -> None:
        """run without --db auto-discovers via resolve_db_for_cli."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["run", "--parallel"])
        assert result.exit_code == 0, result.output
        mock_resolve.assert_called_once_with(None)
        # Verify db_path was passed to _run_async
        call_args = mock_run.call_args
        assert call_args[0][4] == db_path  # db_path is 5th positional arg

    def test_run_explicit_db_overrides(self, runner: CliRunner, tmp_path: Path) -> None:
        """--db /foo overrides auto-discovery."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, None),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(cli, ["run", "--parallel", "--db", str(db_path)])
        assert result.exit_code == 0, result.output
        mock_resolve.assert_called_once_with(str(db_path))

    def test_run_no_tdd_shows_error(self, runner: CliRunner) -> None:
        """No .tdd/ and no --db shows error and exits 1."""
        with patch(
            "tdd_orchestrator.cli.resolve_db_for_cli",
            side_effect=FileNotFoundError(
                "No .tdd/ directory found. "
                "Run 'tdd-orchestrator init' first or use --db."
            ),
        ):
            result = runner.invoke(cli, ["run", "--parallel"])
        assert result.exit_code != 0
        assert "No .tdd/" in result.output

    def test_run_workers_from_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """No --workers uses config.tdd.max_workers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        config = _make_config(max_workers=4)
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, config),
            ),
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["run", "--parallel"])
        assert result.exit_code == 0, result.output
        # workers is 2nd positional arg
        assert mock_run.call_args[0][1] == 4

    def test_run_workers_explicit_overrides_config(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--workers 3 overrides config.tdd.max_workers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        config = _make_config(max_workers=4)
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, config),
            ),
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["run", "--parallel", "--workers", "3"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[0][1] == 3

    def test_run_workers_fallback_without_config(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--db /foo (no config) + no --workers -> default 2."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, None),
            ),
            patch(
                "tdd_orchestrator.cli._run_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["run", "--parallel", "--db", str(db_path)])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[0][1] == 2


class TestStatusAutoDiscovery:
    """Tests for auto-discovery in status command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_status_auto_discovers_db(self, runner: CliRunner, tmp_path: Path) -> None:
        """status without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli._status_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)
        mock_fn.assert_awaited_once_with(db_path)

    def test_status_explicit_db_overrides(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--db /foo overrides auto-discovery."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, None),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli._status_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(cli, ["status", "--db", str(db_path)])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(str(db_path))

    def test_status_no_tdd_shows_error(self, runner: CliRunner) -> None:
        """No .tdd/ and no --db shows error and exits 1."""
        with patch(
            "tdd_orchestrator.cli.resolve_db_for_cli",
            side_effect=FileNotFoundError("No .tdd/ directory found."),
        ):
            result = runner.invoke(cli, ["status"])
        assert result.exit_code != 0
        assert "No .tdd/" in result.output


class TestServeAutoDiscovery:
    """Tests for auto-discovery in serve command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_serve_auto_discovers_db(self, runner: CliRunner, tmp_path: Path) -> None:
        """serve without --db-path auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch("tdd_orchestrator.cli.run_server") as mock_serve,
        ):
            result = runner.invoke(cli, ["serve"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)
        mock_serve.assert_called_once()
        assert mock_serve.call_args[1]["db_path"] == db_path

    def test_serve_explicit_db_path_overrides(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--db-path /foo overrides auto-discovery."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli.resolve_db_for_cli",
                return_value=(db_path, None),
            ) as mock_resolve,
            patch("tdd_orchestrator.cli.run_server"),
        ):
            result = runner.invoke(cli, ["serve", "--db-path", str(db_path)])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(str(db_path))
