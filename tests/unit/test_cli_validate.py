"""Tests for validate CLI commands.

Tests the validate command group and its subcommands using CliRunner.
Async implementations are mocked to avoid needing a real database.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli_validate import validate
from tdd_orchestrator.project_config import ProjectConfig, TDDConfig


def _make_config() -> ProjectConfig:
    """Create a ProjectConfig for testing."""
    return ProjectConfig(name="test-project", tdd=TDDConfig(prefix="TDD"))


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

    def test_validate_phase_pass_output(self, runner: CliRunner, tmp_path: Path) -> None:
        """Phase gate passes -> exit 0."""
        db_path = tmp_path / "test.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli_validate._validate_phase_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            mock_fn.return_value = None
            result = runner.invoke(validate, ["phase", "--phase", "2"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(2, db_path)

    def test_validate_phase_fail_output(self, runner: CliRunner, tmp_path: Path) -> None:
        """Phase gate fails -> exit 1."""
        db_path = tmp_path / "test.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli_validate._validate_phase_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            mock_fn.side_effect = SystemExit(1)
            result = runner.invoke(validate, ["phase", "--phase", "2"])
            assert result.exit_code == 1


class TestValidateRunCommand:
    """Tests for validate run command execution."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_run_invokes_validator(self, runner: CliRunner, tmp_path: Path) -> None:
        """validate run calls _validate_run_async."""
        db_path = tmp_path / "test.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli_validate._validate_run_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            mock_fn.return_value = None
            result = runner.invoke(validate, ["run"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(None, db_path)

    def test_validate_run_with_run_id(self, runner: CliRunner, tmp_path: Path) -> None:
        """validate run --run-id 5 passes run_id to async fn."""
        db_path = tmp_path / "test.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli_validate._validate_run_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            mock_fn.return_value = None
            result = runner.invoke(validate, ["run", "--run-id", "5"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(5, db_path)


class TestValidateAllCommand:
    """Tests for validate all command execution."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_all_invokes_async(self, runner: CliRunner, tmp_path: Path) -> None:
        """validate all calls _validate_all_async."""
        db_path = tmp_path / "test.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ),
            patch(
                "tdd_orchestrator.cli_validate._validate_all_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            mock_fn.return_value = None
            result = runner.invoke(validate, ["all"])
            assert result.exit_code == 0
            mock_fn.assert_awaited_once_with(db_path)


class TestValidateAutoDiscovery:
    """Tests for auto-discovery in validate commands."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_validate_phase_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate phase without --db auto-discovers via resolve_db_for_cli."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_validate._validate_phase_async",
                new_callable=AsyncMock,
            ) as mock_fn,
        ):
            result = runner.invoke(validate, ["phase", "--phase", "1"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)
        mock_fn.assert_awaited_once_with(1, db_path)

    def test_validate_run_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate run without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_validate._validate_run_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(validate, ["run"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)

    def test_validate_all_auto_discovers_db(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate all without --db auto-discovers."""
        db_path = tmp_path / ".tdd" / "orchestrator.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, _make_config()),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_validate._validate_all_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(validate, ["all"])
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(None)

    def test_validate_phase_explicit_db_overrides(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--db /some/path passes override to resolve_db_for_cli."""
        db_path = tmp_path / "custom.db"
        with (
            patch(
                "tdd_orchestrator.cli_validate.resolve_db_for_cli",
                return_value=(db_path, None),
            ) as mock_resolve,
            patch(
                "tdd_orchestrator.cli_validate._validate_phase_async",
                new_callable=AsyncMock,
            ),
        ):
            result = runner.invoke(
                validate, ["phase", "--phase", "1", "--db", str(db_path)]
            )
        assert result.exit_code == 0
        mock_resolve.assert_called_once_with(str(db_path))

    def test_validate_no_tdd_shows_error(self, runner: CliRunner) -> None:
        """No .tdd/ and no --db shows error and exits 1."""
        with patch(
            "tdd_orchestrator.cli_validate.resolve_db_for_cli",
            side_effect=FileNotFoundError("No .tdd/ directory found."),
        ):
            result = runner.invoke(validate, ["phase", "--phase", "1"])
        assert result.exit_code != 0
        assert "No .tdd/" in result.output
