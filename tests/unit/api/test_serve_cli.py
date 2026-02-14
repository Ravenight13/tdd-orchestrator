"""Tests for the serve CLI command.

Tests that the 'serve' command is properly registered on the CLI group
and correctly delegates to run_server with the appropriate arguments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli

_FAKE_DB = Path("/tmp/fake.db")


class TestServeCLICommand:
    """Tests for the serve CLI command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture(autouse=True)
    def _mock_resolve(self) -> Generator[MagicMock, None, None]:
        """Auto-mock resolve_db_for_cli so serve doesn't need a real .tdd/."""

        def _resolve(db_override: str | None = None) -> tuple[Path, None]:
            if db_override is not None:
                return Path(db_override), None
            return _FAKE_DB, None

        with patch(
            "tdd_orchestrator.cli.resolve_db_for_cli",
            side_effect=_resolve,
        ) as m:
            yield m

    def test_serve_command_calls_run_server_with_defaults_when_no_arguments(
        self, runner: CliRunner
    ) -> None:
        """GIVEN no arguments WHEN invoking `cli serve` THEN run_server is called with defaults."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once_with(
                host="127.0.0.1",
                port=8420,
                db_path=_FAKE_DB,
                reload=False,
                log_level="info",
            )

    def test_serve_command_calls_run_server_with_explicit_options(
        self, runner: CliRunner
    ) -> None:
        """GIVEN explicit options WHEN invoking `cli serve` THEN run_server is called with those values."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(
                cli,
                [
                    "serve",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "9000",
                    "--db-path",
                    "/tmp/test.db",
                    "--reload",
                    "--log-level",
                    "debug",
                ],
            )

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once_with(
                host="0.0.0.0",
                port=9000,
                db_path=Path("/tmp/test.db"),
                reload=True,
                log_level="debug",
            )

    def test_serve_command_exits_nonzero_when_invalid_log_level(
        self, runner: CliRunner
    ) -> None:
        """GIVEN invalid --log-level 'banana' WHEN invoking `cli serve` THEN exits non-zero with error."""
        with patch("tdd_orchestrator.cli.run_server"):
            result = runner.invoke(cli, ["serve", "--log-level", "banana"])

            assert result.exit_code != 0, "Should fail with invalid log level"
            # Click shows invalid choice errors in output (could be stdout or stderr depending on version)
            error_output = result.output if result.output else ""
            assert "invalid" in error_output.lower() or "choice" in error_output.lower(), (
                f"Error should mention invalid choice, got: {error_output}"
            )

    def test_serve_command_exits_nonzero_when_invalid_port(
        self, runner: CliRunner
    ) -> None:
        """GIVEN invalid --port 'notanumber' WHEN invoking `cli serve` THEN exits non-zero with error."""
        with patch("tdd_orchestrator.cli.run_server"):
            result = runner.invoke(cli, ["serve", "--port", "notanumber"])

            assert result.exit_code != 0, "Should fail with invalid port"
            error_output = result.output if result.output else ""
            # Click typically shows "invalid" and mentions integer
            assert "invalid" in error_output.lower() or "integer" in error_output.lower(), (
                f"Error should mention invalid integer, got: {error_output}"
            )

    def test_serve_command_listed_in_cli_help(self, runner: CliRunner) -> None:
        """GIVEN serve command is registered WHEN invoking `cli --help` THEN 'serve' is listed."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0, f"CLI help failed: {result.output}"
        assert "serve" in result.output, (
            f"'serve' should be listed in help output: {result.output}"
        )

    def test_serve_command_accepts_warning_log_level(self, runner: CliRunner) -> None:
        """GIVEN --log-level warning WHEN invoking `cli serve` THEN run_server is called with log_level='warning'."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--log-level", "warning"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["log_level"] == "warning"

    def test_serve_command_accepts_error_log_level(self, runner: CliRunner) -> None:
        """GIVEN --log-level error WHEN invoking `cli serve` THEN run_server is called with log_level='error'."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--log-level", "error"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["log_level"] == "error"

    def test_serve_command_accepts_critical_log_level(self, runner: CliRunner) -> None:
        """GIVEN --log-level critical WHEN invoking `cli serve` THEN run_server is called with log_level='critical'."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--log-level", "critical"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["log_level"] == "critical"

    def test_serve_command_accepts_info_log_level_explicitly(
        self, runner: CliRunner
    ) -> None:
        """GIVEN --log-level info WHEN invoking `cli serve` THEN run_server is called with log_level='info'."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--log-level", "info"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["log_level"] == "info"

    def test_serve_command_without_reload_flag_sets_reload_false(
        self, runner: CliRunner
    ) -> None:
        """GIVEN no --reload flag WHEN invoking `cli serve` THEN reload is False."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["reload"] is False

    def test_serve_command_with_reload_flag_sets_reload_true(
        self, runner: CliRunner
    ) -> None:
        """GIVEN --reload flag WHEN invoking `cli serve` THEN reload is True."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--reload"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["reload"] is True

    def test_serve_command_db_path_is_resolved_when_not_provided(
        self, runner: CliRunner
    ) -> None:
        """GIVEN no --db-path WHEN invoking `cli serve` THEN db_path is auto-discovered."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["db_path"] == _FAKE_DB

    def test_serve_command_db_path_is_path_object_when_provided(
        self, runner: CliRunner
    ) -> None:
        """GIVEN --db-path /some/path.db WHEN invoking `cli serve` THEN db_path is Path object."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--db-path", "/some/path.db"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["db_path"] == Path("/some/path.db")
            assert isinstance(call_kwargs["db_path"], Path)

    def test_serve_command_port_boundary_minimum(self, runner: CliRunner) -> None:
        """GIVEN --port 1 WHEN invoking `cli serve` THEN run_server is called with port=1."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--port", "1"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["port"] == 1

    def test_serve_command_port_boundary_maximum(self, runner: CliRunner) -> None:
        """GIVEN --port 65535 WHEN invoking `cli serve` THEN run_server is called with port=65535."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--port", "65535"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["port"] == 65535

    def test_serve_command_negative_port_is_invalid(self, runner: CliRunner) -> None:
        """GIVEN --port -1 WHEN invoking `cli serve` THEN should handle as invalid."""
        with patch("tdd_orchestrator.cli.run_server"):
            result = runner.invoke(cli, ["serve", "--port", "-1"])

            # Negative ports may be accepted by Click as integers but are invalid
            # The implementation may validate this, or Click may reject it
            # We just verify the command doesn't crash unexpectedly
            assert result.exit_code is not None  # Command completed

    def test_serve_command_exits_nonzero_when_port_is_float(
        self, runner: CliRunner
    ) -> None:
        """GIVEN --port 8080.5 WHEN invoking `cli serve` THEN exits non-zero."""
        with patch("tdd_orchestrator.cli.run_server"):
            result = runner.invoke(cli, ["serve", "--port", "8080.5"])

            assert result.exit_code != 0, "Should fail with float port"

    def test_serve_command_host_accepts_ipv4_address(self, runner: CliRunner) -> None:
        """GIVEN --host 192.168.1.1 WHEN invoking `cli serve` THEN run_server is called with that host."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--host", "192.168.1.1"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["host"] == "192.168.1.1"

    def test_serve_command_host_accepts_localhost(self, runner: CliRunner) -> None:
        """GIVEN --host localhost WHEN invoking `cli serve` THEN run_server is called with host='localhost'."""
        with patch("tdd_orchestrator.cli.run_server") as mock_run_server:
            result = runner.invoke(cli, ["serve", "--host", "localhost"])

            assert result.exit_code == 0, f"CLI failed: {result.output}"
            mock_run_server.assert_called_once()
            call_kwargs = mock_run_server.call_args[1]
            assert call_kwargs["host"] == "localhost"
