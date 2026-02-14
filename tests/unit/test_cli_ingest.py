"""Tests for CLI ingest command.

Tests the `tdd-orchestrator ingest` command using Click's CliRunner
with mocked decomposition pipeline and project config.

All CliRunner tests are synchronous because asyncio.run() inside
the Click command creates its own event loop.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.cli_ingest import _parse_phases
from tdd_orchestrator.decomposition.exceptions import DecompositionError
from tdd_orchestrator.project_config import ProjectConfig, TDDConfig


def _make_config(prefix: str = "TDD") -> ProjectConfig:
    """Create a ProjectConfig for testing."""
    return ProjectConfig(name="test-project", tdd=TDDConfig(prefix=prefix))


class TestIngestHelp:
    """Tests for help text and registration."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_ingest_help(self, runner: CliRunner) -> None:
        """--help exits 0 and shows key options."""
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--prd" in result.output
        assert "--project" in result.output
        assert "--clear" in result.output
        assert "--dry-run" in result.output
        assert "--phases" in result.output
        assert "--prefix" in result.output
        assert "--scaffolding-ref" in result.output

    def test_ingest_registered_in_main_help(self, runner: CliRunner) -> None:
        """ingest appears in main --help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "ingest" in result.output

    def test_ingest_requires_prd_option(self, runner: CliRunner) -> None:
        """Missing --prd exits with error."""
        result = runner.invoke(cli, ["ingest"])
        assert result.exit_code != 0

    def test_ingest_mock_llm_hidden_from_help(self, runner: CliRunner) -> None:
        """--mock-llm is not shown in --help output."""
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--mock-llm" not in result.output


class TestProjectDiscovery:
    """Tests for project root discovery."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_ingest_auto_discovers_project(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Finds .tdd/ via find_project_root when no --project given."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("test spec", encoding="utf-8")
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()

        with (
            patch(
                "tdd_orchestrator.cli_ingest.find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "tdd_orchestrator.cli_ingest._run_ingest_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["ingest", "--prd", str(spec_file)])

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["project_root"] == tmp_path

    def test_ingest_explicit_project_path(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--project overrides auto-discovery."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("test spec", encoding="utf-8")
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        with (
            patch(
                "tdd_orchestrator.cli_ingest._run_ingest_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["project_root"] == Path(str(project_dir))

    def test_ingest_no_project_found_errors(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """No .tdd/ and no --project exits with error and hint."""
        spec_file = tmp_path / "spec.txt"
        spec_file.write_text("test spec", encoding="utf-8")

        with patch(
            "tdd_orchestrator.cli_ingest.find_project_root",
            return_value=None,
        ):
            result = runner.invoke(cli, ["ingest", "--prd", str(spec_file)])

        assert result.exit_code != 0
        assert "tdd-orchestrator init" in result.output


class TestDecompositionIntegration:
    """Tests for decomposition pipeline integration."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture
    def spec_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "spec.txt"
        f.write_text("test spec content", encoding="utf-8")
        return f

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".tdd").mkdir()
        return d

    def _patch_all(
        self,
        config: ProjectConfig | None = None,
        exit_code: int = 0,
    ) -> tuple[MagicMock, ...]:
        """Create standard mocks for setup_project_context, run_decomposition, reset_db."""
        cfg = config or _make_config()
        mock_setup = AsyncMock(return_value=cfg)
        mock_run = AsyncMock(return_value=exit_code)
        mock_reset = AsyncMock()
        mock_cleanup = MagicMock()
        return mock_setup, mock_run, mock_reset, mock_cleanup

    def _run_with_patches(
        self,
        runner: CliRunner,
        args: list[str],
        config: ProjectConfig | None = None,
        exit_code: int = 0,
    ) -> tuple[object, AsyncMock, AsyncMock, AsyncMock]:
        """Run CLI with standard patches, return result and mocks."""
        mock_setup, mock_run, mock_reset, mock_cleanup = self._patch_all(config, exit_code)
        with (
            patch("tdd_orchestrator.cli_ingest.setup_project_context", mock_setup),
            patch("tdd_orchestrator.cli_ingest.run_decomposition", mock_run),
            patch("tdd_orchestrator.cli_ingest.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk", mock_cleanup),
        ):
            result = runner.invoke(cli, args)
        return result, mock_setup, mock_run, mock_reset

    def test_ingest_calls_run_decomposition(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """Verifies run_decomposition is called with correct args."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
        )
        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        kwargs = mock_run.call_args[1]
        assert kwargs["spec_path"] == spec_file
        assert kwargs["prefix"] == "TDD"
        assert kwargs["clear_existing"] is False
        assert kwargs["dry_run"] is False

    def test_ingest_uses_config_prefix(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """Without --prefix, uses config.tdd.prefix."""
        config = _make_config(prefix="MYAPP")
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            config=config,
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["prefix"] == "MYAPP"

    def test_ingest_prefix_override(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--prefix FOO overrides config prefix."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            [
                "ingest", "--prd", str(spec_file),
                "--project", str(project_dir), "--prefix", "FOO",
            ],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["prefix"] == "FOO"

    def test_ingest_dry_run_flag(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--dry-run passes through."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            ["ingest", "--prd", str(spec_file), "--project", str(project_dir), "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["dry_run"] is True

    def test_ingest_clear_flag(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--clear passes through."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            ["ingest", "--prd", str(spec_file), "--project", str(project_dir), "--clear"],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["clear_existing"] is True

    def test_ingest_phases_filter(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--phases "1,2,3" passes through as {1, 2, 3}."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            [
                "ingest", "--prd", str(spec_file),
                "--project", str(project_dir), "--phases", "1,2,3",
            ],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["phases_filter"] == {1, 2, 3}

    def test_ingest_scaffolding_ref_flag(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--scaffolding-ref passes through."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            [
                "ingest", "--prd", str(spec_file),
                "--project", str(project_dir), "--scaffolding-ref",
            ],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["scaffolding_ref"] is True

    def test_ingest_mock_llm_flag(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--mock-llm passes through."""
        result, _, mock_run, _ = self._run_with_patches(
            runner,
            [
                "ingest", "--prd", str(spec_file),
                "--project", str(project_dir), "--mock-llm",
            ],
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args[1]["use_mock_llm"] is True


class TestErrorHandling:
    """Tests for error paths."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture
    def spec_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "spec.txt"
        f.write_text("test spec", encoding="utf-8")
        return f

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "proj"
        d.mkdir()
        return d

    def test_ingest_missing_prd_file_errors(self, runner: CliRunner) -> None:
        """Nonexistent --prd file produces Click error."""
        result = runner.invoke(cli, ["ingest", "--prd", "/nonexistent/spec.txt"])
        assert result.exit_code != 0

    def test_ingest_decomposition_failure_exits_nonzero(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """run_decomposition returns 1 -> exit 1."""
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_ingest.run_decomposition",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        assert result.exit_code != 0

    def test_ingest_decomposition_error_reported(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """DecompositionError -> exit 1 with message."""
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_ingest.run_decomposition",
                new_callable=AsyncMock,
                side_effect=DecompositionError("circular deps"),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        assert result.exit_code != 0
        assert "circular deps" in result.output

    def test_ingest_unexpected_error_reported(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """Generic Exception -> exit 1 with message."""
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_ingest.run_decomposition",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        assert result.exit_code != 0
        assert "boom" in result.output

    def test_ingest_empty_prefix_override_errors(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--prefix "" exits with error."""
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir), "--prefix", ""],
            )
        assert result.exit_code != 0
        assert "empty" in result.output.lower()

    def test_ingest_whitespace_prefix_override_errors(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """--prefix "has space" exits with error."""
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                [
                    "ingest", "--prd", str(spec_file),
                    "--project", str(project_dir), "--prefix", "has space",
                ],
            )
        assert result.exit_code != 0
        assert "whitespace" in result.output.lower()


class TestCleanup:
    """Tests for DB singleton cleanup."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture
    def spec_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "spec.txt"
        f.write_text("test spec", encoding="utf-8")
        return f

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "proj"
        d.mkdir()
        return d

    def test_ingest_resets_db_on_success(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """reset_db() called after success."""
        mock_reset = AsyncMock()
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_ingest.run_decomposition",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        assert result.exit_code == 0, result.output
        mock_reset.assert_awaited_once()

    def test_ingest_resets_db_on_failure(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """reset_db() called even after decomposition failure."""
        mock_reset = AsyncMock()
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_ingest.run_decomposition",
                new_callable=AsyncMock,
                side_effect=DecompositionError("fail"),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        mock_reset.assert_awaited_once()

    def test_ingest_resets_db_on_setup_failure(
        self, runner: CliRunner, spec_file: Path, project_dir: Path
    ) -> None:
        """reset_db() called even when setup_project_context fails."""
        mock_reset = AsyncMock()
        with (
            patch(
                "tdd_orchestrator.cli_ingest.setup_project_context",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("no config"),
            ),
            patch("tdd_orchestrator.cli_ingest.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_ingest._cleanup_sdk"),
        ):
            runner.invoke(
                cli,
                ["ingest", "--prd", str(spec_file), "--project", str(project_dir)],
            )
        mock_reset.assert_awaited_once()


class TestParsePhases:
    """Tests for _parse_phases helper."""

    def test_parse_phases_none(self) -> None:
        assert _parse_phases(None) is None

    def test_parse_phases_single(self) -> None:
        assert _parse_phases("5") == {5}

    def test_parse_phases_multiple(self) -> None:
        assert _parse_phases("1,2,3") == {1, 2, 3}

    def test_parse_phases_with_spaces(self) -> None:
        assert _parse_phases(" 1 , 2 ") == {1, 2}

    def test_parse_phases_invalid_raises(self) -> None:
        with pytest.raises(click.BadParameter):
            _parse_phases("abc")
