"""Tests for CLI init command.

Tests the `tdd-orchestrator init` command using Click's CliRunner
with tmp_path fixtures for isolated filesystem operations.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli


class TestInitCommand:
    """Tests for the init CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CliRunner for testing."""
        return CliRunner()

    def test_init_help(self, runner: CliRunner) -> None:
        """init --help shows help text."""
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize a project" in result.output
        assert "--project" in result.output
        assert "--name" in result.output
        assert "--force" in result.output

    def test_init_creates_tdd_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """init --project creates .tdd/config.toml."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            result = runner.invoke(cli, ["init", "--project", str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / ".tdd" / "config.toml").is_file()

    def test_init_creates_gitignore(self, runner: CliRunner, tmp_path: Path) -> None:
        """init --project creates .tdd/.gitignore with DB exclusions."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            result = runner.invoke(cli, ["init", "--project", str(tmp_path)])

        assert result.exit_code == 0
        gitignore = tmp_path / ".tdd" / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text(encoding="utf-8")
        assert "orchestrator.db" in content

    def test_init_custom_name_and_language(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """init --name foo --language rust reflects in config."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            result = runner.invoke(
                cli,
                ["init", "--project", str(tmp_path), "--name", "foo", "--language", "rust"],
            )

        assert result.exit_code == 0
        assert "foo" in result.output

        config_text = (tmp_path / ".tdd" / "config.toml").read_text(encoding="utf-8")
        assert 'name = "foo"' in config_text
        assert 'language = "rust"' in config_text

    def test_init_name_defaults_to_dirname(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Name defaults to directory basename when not specified."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            result = runner.invoke(cli, ["init", "--project", str(tmp_path)])

        assert result.exit_code == 0
        dir_name = tmp_path.resolve().name
        assert dir_name in result.output

    def test_init_existing_tdd_errors(self, runner: CliRunner, tmp_path: Path) -> None:
        """init with existing .tdd/ directory returns error exit code."""
        (tmp_path / ".tdd").mkdir()

        result = runner.invoke(cli, ["init", "--project", str(tmp_path)])

        assert result.exit_code != 0
        assert "already initialized" in result.output or "already initialized" in (
            result.output + str(result.exception or "")
        )

    def test_init_force_overwrites(self, runner: CliRunner, tmp_path: Path) -> None:
        """init --force with existing .tdd/ succeeds."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            # First init
            runner.invoke(cli, ["init", "--project", str(tmp_path), "--name", "first"])
            # Second init with --force
            result = runner.invoke(
                cli,
                ["init", "--project", str(tmp_path), "--name", "second", "--force"],
            )

        assert result.exit_code == 0
        assert "second" in result.output

    def test_init_nonexistent_path_errors(self, runner: CliRunner) -> None:
        """init --project /nonexistent path returns error."""
        result = runner.invoke(cli, ["init", "--project", "/nonexistent/path"])

        assert result.exit_code != 0

    def test_init_shows_next_steps(self, runner: CliRunner, tmp_path: Path) -> None:
        """init output includes next steps."""
        with patch(
            "tdd_orchestrator.cli_init._init_db", new_callable=AsyncMock
        ):
            result = runner.invoke(cli, ["init", "--project", str(tmp_path)])

        assert result.exit_code == 0
        assert "Next steps" in result.output

    def test_init_registered_in_main_help(self, runner: CliRunner) -> None:
        """init command appears in main --help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output

    def test_init_requires_project_option(self, runner: CliRunner) -> None:
        """init without --project shows error."""
        result = runner.invoke(cli, ["init"])
        assert result.exit_code != 0
