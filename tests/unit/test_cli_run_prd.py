"""Tests for CLI run-prd command.

Tests the `tdd-orchestrator run-prd` command using Click's CliRunner
with mocked pipeline and project config.

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
from tdd_orchestrator.cli_run_prd import _parse_phases
from tdd_orchestrator.prd_pipeline import PrdPipelineConfig, PrdPipelineResult
from tdd_orchestrator.project_config import GitConfig, ProjectConfig, TDDConfig
from tdd_orchestrator.worker_pool import PoolResult


def _make_config(prefix: str = "TDD", base_branch: str = "main") -> ProjectConfig:
    """Create a ProjectConfig for testing."""
    return ProjectConfig(
        name="test-project",
        tdd=TDDConfig(prefix=prefix),
        git=GitConfig(base_branch=base_branch),
    )


def _make_pipeline_result(
    *,
    exit_code: int = 0,
    task_count: int = 5,
    stage: str = "done",
    error: str | None = None,
    pool_result: PoolResult | None = None,
) -> PrdPipelineResult:
    """Create a PrdPipelineResult for testing."""
    return PrdPipelineResult(
        decomposition_exit_code=exit_code,
        task_count=task_count,
        pool_result=pool_result or PoolResult(
            tasks_completed=task_count, tasks_failed=0,
            total_invocations=20, worker_stats=[],
        ),
        stage_reached=stage,
        error_message=error,
    )


class TestRunPrdHelp:
    """Tests for help text and registration."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_help_exits_zero(self, runner: CliRunner) -> None:
        """--help exits 0 and shows key options."""
        result = runner.invoke(cli, ["run-prd", "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output
        assert "--workers" in result.output
        assert "--branch" in result.output
        assert "--create-pr" in result.output
        assert "--dry-run" in result.output
        assert "--prefix" in result.output
        assert "PRD_FILE" in result.output

    def test_registered_in_main_help(self, runner: CliRunner) -> None:
        """run-prd appears in main --help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "run-prd" in result.output

    def test_prd_file_required(self, runner: CliRunner) -> None:
        """Missing PRD_FILE argument exits with error."""
        result = runner.invoke(cli, ["run-prd"])
        assert result.exit_code != 0

    def test_mock_llm_hidden_from_help(self, runner: CliRunner) -> None:
        """--mock-llm is not shown in help."""
        result = runner.invoke(cli, ["run-prd", "--help"])
        assert result.exit_code == 0
        assert "--mock-llm" not in result.output


class TestRunPrdProjectDiscovery:
    """Tests for project root discovery."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_auto_discovers_project(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Finds .tdd/ via find_project_root when no --project given."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        tdd_dir = tmp_path / ".tdd"
        tdd_dir.mkdir()

        with (
            patch(
                "tdd_orchestrator.cli_run_prd.find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "tdd_orchestrator.cli_run_prd.load_project_config",
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_run_prd._run_prd_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(cli, ["run-prd", str(prd_file)])

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()

    def test_explicit_project_overrides_discovery(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--project overrides auto-discovery."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        with (
            patch(
                "tdd_orchestrator.cli_run_prd.load_project_config",
                return_value=_make_config(),
            ),
            patch(
                "tdd_orchestrator.cli_run_prd._run_prd_async",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = runner.invoke(
                cli,
                ["run-prd", str(prd_file), "--project", str(project_dir)],
            )

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.project_root == Path(str(project_dir))

    def test_no_project_found_errors(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """No .tdd/ and no --project exits with error and hint."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")

        with patch(
            "tdd_orchestrator.cli_run_prd.find_project_root",
            return_value=None,
        ):
            result = runner.invoke(cli, ["run-prd", str(prd_file)])

        assert result.exit_code != 0
        assert "tdd-orchestrator init" in result.output


class TestRunPrdConfigResolution:
    """Tests for config value resolution."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def _run_with_config(
        self,
        runner: CliRunner,
        prd_file: Path,
        project_dir: Path,
        config: ProjectConfig | None = None,
        extra_args: list[str] | None = None,
    ) -> tuple[object, AsyncMock]:
        """Run CLI with config patches, return result and mock."""
        cfg = config or _make_config()
        mock_run = AsyncMock()

        args = ["run-prd", str(prd_file), "--project", str(project_dir)]
        if extra_args:
            args.extend(extra_args)

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config", return_value=cfg),
            patch("tdd_orchestrator.cli_run_prd._run_prd_async", mock_run),
        ):
            result = runner.invoke(cli, args)
        return result, mock_run

    def test_workers_from_flag(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--workers overrides config."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        result, mock_run = self._run_with_config(
            runner, prd_file, project_dir, extra_args=["--workers", "3"],
        )
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.workers == 3

    def test_workers_from_config(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Workers from config when not specified."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        result, mock_run = self._run_with_config(runner, prd_file, project_dir)
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.workers == 2  # TDDConfig default

    def test_prefix_from_flag(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--prefix overrides config."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        result, mock_run = self._run_with_config(
            runner, prd_file, project_dir, extra_args=["--prefix", "MYAPP"],
        )
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.prefix == "MYAPP"

    def test_branch_from_flag(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--branch overrides auto-derivation."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        result, mock_run = self._run_with_config(
            runner, prd_file, project_dir,
            extra_args=["--branch", "feat/custom"],
        )
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.branch_name == "feat/custom"

    def test_branch_auto_derived_from_prd(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Branch auto-derived from PRD filename when not specified."""
        prd_file = tmp_path / "user-auth.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        result, mock_run = self._run_with_config(runner, prd_file, project_dir)
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.branch_name == "feat/user-auth"

    def test_base_branch_from_config(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """base_branch comes from config.git.base_branch."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        config = _make_config(base_branch="develop")
        result, mock_run = self._run_with_config(
            runner, prd_file, project_dir, config=config,
        )
        assert result.exit_code == 0, result.output
        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        assert config_arg.base_branch == "develop"


class TestRunPrdFlagPassthrough:
    """Tests for flag passthrough to pipeline config."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def _run(
        self,
        runner: CliRunner,
        tmp_path: Path,
        extra_args: list[str] | None = None,
    ) -> tuple[object, PrdPipelineConfig]:
        """Run CLI and return the PrdPipelineConfig passed to _run_prd_async."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        mock_run = AsyncMock()
        args = ["run-prd", str(prd_file), "--project", str(project_dir)]
        if extra_args:
            args.extend(extra_args)

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config",
                  return_value=_make_config()),
            patch("tdd_orchestrator.cli_run_prd._run_prd_async", mock_run),
        ):
            result = runner.invoke(cli, args)

        config_arg: PrdPipelineConfig = mock_run.call_args[0][0]
        return result, config_arg

    def test_dry_run_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--dry-run"])
        assert result.exit_code == 0, result.output
        assert cfg.dry_run is True

    def test_clear_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--clear"])
        assert result.exit_code == 0, result.output
        assert cfg.clear_existing is True

    def test_create_pr_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--create-pr"])
        assert result.exit_code == 0, result.output
        assert cfg.create_pr is True

    def test_scaffolding_ref_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--scaffolding-ref"])
        assert result.exit_code == 0, result.output
        assert cfg.scaffolding_ref is True

    def test_mock_llm_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--mock-llm"])
        assert result.exit_code == 0, result.output
        assert cfg.use_mock_llm is True

    def test_no_phase_gates_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--no-phase-gates"])
        assert result.exit_code == 0, result.output
        assert cfg.enable_phase_gates is False

    def test_max_invocations_flag(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--max-invocations", "50"])
        assert result.exit_code == 0, result.output
        assert cfg.max_invocations == 50

    def test_phases_filter(self, runner: CliRunner, tmp_path: Path) -> None:
        result, cfg = self._run(runner, tmp_path, ["--phases", "1,2,3"])
        assert result.exit_code == 0, result.output
        assert cfg.phases_filter == {1, 2, 3}


class TestRunPrdErrorHandling:
    """Tests for error paths."""

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_pipeline_failure_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Pipeline error -> exit 1."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        failed_result = _make_pipeline_result(error="something broke")

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config",
                  return_value=_make_config()),
            patch("tdd_orchestrator.cli_run_prd.run_prd_pipeline",
                  new_callable=AsyncMock, return_value=failed_result),
            patch("tdd_orchestrator.cli_run_prd.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_run_prd._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli, ["run-prd", str(prd_file), "--project", str(project_dir)],
            )

        assert result.exit_code != 0

    def test_exception_exits_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Exception in pipeline -> exit 1 with message."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config",
                  return_value=_make_config()),
            patch("tdd_orchestrator.cli_run_prd.run_prd_pipeline",
                  new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch("tdd_orchestrator.cli_run_prd.reset_db", new_callable=AsyncMock),
            patch("tdd_orchestrator.cli_run_prd._cleanup_sdk"),
        ):
            result = runner.invoke(
                cli, ["run-prd", str(prd_file), "--project", str(project_dir)],
            )

        assert result.exit_code != 0
        assert "boom" in result.output

    def test_cleanup_runs_on_success(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """reset_db and _cleanup_sdk called on success."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        mock_reset = AsyncMock()
        mock_cleanup = MagicMock()

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config",
                  return_value=_make_config()),
            patch("tdd_orchestrator.cli_run_prd.run_prd_pipeline",
                  new_callable=AsyncMock, return_value=_make_pipeline_result()),
            patch("tdd_orchestrator.cli_run_prd.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_run_prd._cleanup_sdk", mock_cleanup),
        ):
            runner.invoke(
                cli, ["run-prd", str(prd_file), "--project", str(project_dir)],
            )

        mock_reset.assert_awaited_once()
        mock_cleanup.assert_called_once()

    def test_cleanup_runs_on_failure(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """reset_db and _cleanup_sdk called even on failure."""
        prd_file = tmp_path / "spec.md"
        prd_file.write_text("test", encoding="utf-8")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()

        mock_reset = AsyncMock()
        mock_cleanup = MagicMock()

        with (
            patch("tdd_orchestrator.cli_run_prd.load_project_config",
                  return_value=_make_config()),
            patch("tdd_orchestrator.cli_run_prd.run_prd_pipeline",
                  new_callable=AsyncMock, side_effect=RuntimeError("fail")),
            patch("tdd_orchestrator.cli_run_prd.reset_db", mock_reset),
            patch("tdd_orchestrator.cli_run_prd._cleanup_sdk", mock_cleanup),
        ):
            runner.invoke(
                cli, ["run-prd", str(prd_file), "--project", str(project_dir)],
            )

        mock_reset.assert_awaited_once()
        mock_cleanup.assert_called_once()


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
