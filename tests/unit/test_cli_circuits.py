"""Tests for circuit breaker CLI auto-discovery.

Tests that circuits subcommands use resolve_db_for_cli for
auto-discovery when --db is omitted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.project_config import ProjectConfig, TDDConfig


def _make_config() -> ProjectConfig:
    """Create a ProjectConfig for testing."""
    return ProjectConfig(name="test-project", tdd=TDDConfig(prefix="TDD"))


class TestCircuitsAutoDiscovery:
    """Tests for auto-discovery in circuits commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_circuits_status_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """circuits status without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_circuits._circuits_status_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            result = runner.invoke(cli, ["circuits", "status"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)
        mock_fn.assert_awaited_once_with(db_path, None, None)

    def test_circuits_health_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """circuits health without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_circuits._circuits_health_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(cli, ["circuits", "health"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)

    def test_circuits_reset_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """circuits reset without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_circuits._circuits_reset_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(cli, ["circuits", "reset", "all", "--force"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)

    def test_circuits_status_explicit_db_overrides(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--db /some/path passes override to resolve_db_for_cli."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
                return_value=(db_path, None),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_circuits._circuits_status_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(
                cli, ["circuits", "status", "--db", str(db_path)]
            )
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(str(db_path))

    def test_circuits_no_tdd_shows_error(self, runner: CliRunner) -> None:
        """No .tdd/ and no --db shows error and exits 1."""
        with patch(
            "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
            side_effect=FileNotFoundError("No .tdd/ directory found."),
        ):
            result = runner.invoke(cli, ["circuits", "status"])
        assert result.exit_code != 0
        assert "No .tdd/" in result.output
