"""Tests for PRD pipeline orchestration.

Tests the prd_pipeline module: pure functions, gh helpers, and
the main run_prd_pipeline orchestrator with mocked stages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdd_orchestrator.prd_pipeline import (
    PrdPipelineConfig,
    PrdPipelineResult,
    _check_gh_available,
    _create_pull_request,
    _generate_pr_body,
    derive_branch_name,
    run_prd_pipeline,
    sanitize_branch_name,
)
from tdd_orchestrator.worker_pool import PoolResult, WorkerStats


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestSanitizeBranchName:
    """Tests for sanitize_branch_name()."""

    def test_lowercases_input(self) -> None:
        assert sanitize_branch_name("MyFeature") == "myfeature"

    def test_replaces_spaces_with_hyphens(self) -> None:
        assert sanitize_branch_name("my feature") == "my-feature"

    def test_replaces_special_chars_with_hyphens(self) -> None:
        assert sanitize_branch_name("feat@v2!") == "feat-v2"

    def test_collapses_consecutive_hyphens(self) -> None:
        assert sanitize_branch_name("a---b") == "a-b"

    def test_preserves_forward_slashes(self) -> None:
        assert sanitize_branch_name("feat/my-branch") == "feat/my-branch"

    def test_strips_leading_trailing_hyphens_per_segment(self) -> None:
        assert sanitize_branch_name("-feat-/-branch-") == "feat/branch"

    def test_handles_empty_string(self) -> None:
        assert sanitize_branch_name("") == ""

    def test_handles_underscores(self) -> None:
        assert sanitize_branch_name("user_auth") == "user-auth"


class TestDeriveBranchName:
    """Tests for derive_branch_name()."""

    def test_strips_md_extension(self) -> None:
        assert derive_branch_name(Path("user-auth.md")) == "feat/user-auth"

    def test_strips_txt_extension(self) -> None:
        assert derive_branch_name(Path("user-auth.txt")) == "feat/user-auth"

    def test_adds_feat_prefix(self) -> None:
        result = derive_branch_name(Path("login-flow.md"))
        assert result.startswith("feat/")

    def test_uses_stem_only_for_paths_with_dirs(self) -> None:
        result = derive_branch_name(Path("docs/plans/user-auth.md"))
        assert result == "feat/user-auth"

    def test_handles_names_with_spaces(self) -> None:
        result = derive_branch_name(Path("my feature spec.md"))
        assert result == "feat/my-feature-spec"

    def test_handles_underscores_in_name(self) -> None:
        result = derive_branch_name(Path("app_spec.md"))
        assert result == "feat/app-spec"


# ---------------------------------------------------------------------------
# gh helper tests
# ---------------------------------------------------------------------------


class TestCheckGhAvailable:
    """Tests for _check_gh_available()."""

    async def test_returns_true_when_installed(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"gh version 2.0", b""))

        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    return_value=mock_proc):
            assert await _check_gh_available() is True

    async def test_returns_false_on_file_not_found(self) -> None:
        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    side_effect=FileNotFoundError):
            assert await _check_gh_available() is False

    async def test_returns_false_on_nonzero_exit(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    return_value=mock_proc):
            assert await _check_gh_available() is False


class TestCreatePullRequest:
    """Tests for _create_pull_request()."""

    async def test_calls_gh_with_list_args(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"https://github.com/org/repo/pull/42\n", b"")
        )

        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    return_value=mock_proc) as mock_exec:
            success, url = await _create_pull_request(
                Path("/repo"), "feat/test", "main", "My PR", "Body text"
            )

        assert success is True
        assert url == "https://github.com/org/repo/pull/42"
        # Verify list-form args (no shell=True)
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "gh"
        assert "pr" in call_args
        assert "create" in call_args

    async def test_parses_pr_url_from_stdout(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"https://github.com/org/repo/pull/99\n", b"")
        )

        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    return_value=mock_proc):
            success, url = await _create_pull_request(
                Path("/repo"), "feat/x", "main", "Title", "Body"
            )

        assert success is True
        assert url == "https://github.com/org/repo/pull/99"

    async def test_returns_false_when_gh_not_installed(self) -> None:
        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    side_effect=FileNotFoundError):
            success, url = await _create_pull_request(
                Path("/repo"), "feat/x", "main", "Title", "Body"
            )

        assert success is False
        assert url is None

    async def test_returns_false_when_gh_fails(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"auth required"))

        with patch("tdd_orchestrator.prd_pipeline.asyncio.create_subprocess_exec",
                    return_value=mock_proc):
            success, url = await _create_pull_request(
                Path("/repo"), "feat/x", "main", "Title", "Body"
            )

        assert success is False
        assert url is None


class TestGeneratePrBody:
    """Tests for _generate_pr_body()."""

    def _make_pool_result(
        self,
        completed: int = 5,
        failed: int = 0,
        invocations: int = 20,
    ) -> PoolResult:
        return PoolResult(
            tasks_completed=completed,
            tasks_failed=failed,
            total_invocations=invocations,
            worker_stats=[
                WorkerStats(worker_id=1, tasks_completed=3, tasks_failed=0, invocations=12),
                WorkerStats(worker_id=2, tasks_completed=2, tasks_failed=0, invocations=8),
            ],
        )

    def test_includes_prd_filename(self) -> None:
        body = _generate_pr_body(Path("user-auth.md"), 10, self._make_pool_result())
        assert "user-auth.md" in body

    def test_includes_task_count(self) -> None:
        body = _generate_pr_body(Path("spec.md"), 15, self._make_pool_result())
        assert "15" in body

    def test_includes_worker_stats(self) -> None:
        body = _generate_pr_body(Path("spec.md"), 5, self._make_pool_result())
        assert "Worker 1" in body
        assert "Worker 2" in body

    def test_includes_completion_stats(self) -> None:
        result = self._make_pool_result(completed=5, failed=1, invocations=30)
        body = _generate_pr_body(Path("spec.md"), 6, result)
        assert "5" in body  # completed
        assert "1" in body  # failed
        assert "30" in body  # invocations


# ---------------------------------------------------------------------------
# Pipeline orchestration tests
# ---------------------------------------------------------------------------


def _make_config(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    create_pr: bool = False,
    pr_title: str | None = None,
    use_mock_llm: bool = True,
) -> PrdPipelineConfig:
    """Create a PrdPipelineConfig for testing."""
    prd_file = tmp_path / "spec.md"
    prd_file.write_text("test spec", encoding="utf-8")
    db_path = tmp_path / ".tdd" / "orchestrator.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return PrdPipelineConfig(
        prd_path=prd_file,
        project_root=tmp_path,
        db_path=db_path,
        prefix="TEST",
        branch_name="feat/spec",
        base_branch="main",
        workers=2,
        max_invocations=50,
        create_pr=create_pr,
        pr_title=pr_title,
        dry_run=dry_run,
        use_mock_llm=use_mock_llm,
    )


class TestRunPrdPipeline:
    """Tests for run_prd_pipeline() with mocked stages."""

    def _setup_mocks(
        self,
        decomp_exit_code: int = 0,
        task_count: int = 5,
        pool_result: PoolResult | None = None,
    ) -> dict[str, MagicMock | AsyncMock]:
        """Create standard mocks for all pipeline stages."""
        mock_git = MagicMock()
        mock_git.get_current_branch = AsyncMock(return_value="main")
        mock_git.create_feature_branch = AsyncMock(return_value="feat/spec")
        mock_git.push_branch = AsyncMock()

        mock_db_instance = MagicMock()
        mock_db_instance.execute_query = AsyncMock(
            return_value=[{"cnt": task_count}]
        )

        if pool_result is None:
            pool_result = PoolResult(
                tasks_completed=task_count,
                tasks_failed=0,
                total_invocations=20,
                worker_stats=[],
            )

        mock_pool = MagicMock()
        mock_pool.run_all_phases = AsyncMock(return_value=pool_result)

        mock_explicit_db = MagicMock()
        mock_explicit_db.connect = AsyncMock()
        mock_explicit_db.close = AsyncMock()

        return {
            "git": mock_git,
            "setup_context": AsyncMock(),
            "decomposition": AsyncMock(return_value=decomp_exit_code),
            "get_db": AsyncMock(return_value=mock_db_instance),
            "reset_db": AsyncMock(),
            "cleanup_sdk": MagicMock(),
            "pool_cls": MagicMock(return_value=mock_pool),
            "explicit_db_cls": MagicMock(return_value=mock_explicit_db),
            "pool_result": pool_result,
            "mock_pool": mock_pool,
        }

    def _apply_patches(self, mocks: dict[str, MagicMock | AsyncMock]) -> list[object]:
        """Create context managers for all patches."""
        return [
            patch("tdd_orchestrator.prd_pipeline.GitCoordinator", return_value=mocks["git"]),
            patch("tdd_orchestrator.prd_pipeline.setup_project_context", mocks["setup_context"]),
            patch("tdd_orchestrator.prd_pipeline.run_decomposition", mocks["decomposition"]),
            patch("tdd_orchestrator.prd_pipeline.get_db", mocks["get_db"]),
            patch("tdd_orchestrator.prd_pipeline.reset_db", mocks["reset_db"]),
            patch("tdd_orchestrator.prd_pipeline._cleanup_sdk_processes", mocks["cleanup_sdk"]),
            patch("tdd_orchestrator.prd_pipeline.WorkerPool", mocks["pool_cls"]),
            patch("tdd_orchestrator.prd_pipeline.OrchestratorDB", mocks["explicit_db_cls"]),
        ]

    async def test_decomposition_called_with_correct_args(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            await run_prd_pipeline(config)

        mocks["decomposition"].assert_awaited_once()
        call_kwargs = mocks["decomposition"].call_args[1]
        assert call_kwargs["spec_path"] == config.prd_path
        assert call_kwargs["prefix"] == "TEST"
        assert call_kwargs["use_mock_llm"] is True

    async def test_execution_runs_on_decomposition_success(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mocks = self._setup_mocks(decomp_exit_code=0)

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            result = await run_prd_pipeline(config)

        assert result.stage_reached == "done"
        mocks["mock_pool"].run_all_phases.assert_awaited_once()

    async def test_execution_skipped_on_decomposition_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mocks = self._setup_mocks(decomp_exit_code=1)

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            result = await run_prd_pipeline(config)

        assert result.decomposition_exit_code == 1
        assert result.error_message == "Decomposition failed"
        assert result.stage_reached == "decompose"
        mocks["mock_pool"].run_all_phases.assert_not_awaited()

    async def test_execution_skipped_in_dry_run(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, dry_run=True)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            result = await run_prd_pipeline(config)

        assert result.stage_reached == "done"
        assert result.decomposition_exit_code == 0
        mocks["mock_pool"].run_all_phases.assert_not_awaited()

    async def test_branch_creation_skipped_in_dry_run(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, dry_run=True)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            await run_prd_pipeline(config)

        mocks["git"].create_feature_branch.assert_not_awaited()

    async def test_pr_creation_on_success_with_create_pr(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, create_pr=True)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"],
                            _check_gh_available=AsyncMock(return_value=True),
                            _create_pull_request=AsyncMock(
                                return_value=(True, "https://github.com/org/repo/pull/1")
                            )):
            result = await run_prd_pipeline(config)

        assert result.pr_url == "https://github.com/org/repo/pull/1"
        assert result.stage_reached == "done"

    async def test_pr_skipped_when_create_pr_not_set(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, create_pr=False)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            result = await run_prd_pipeline(config)

        assert result.pr_url is None
        assert result.stage_reached == "done"

    async def test_pr_skipped_when_tasks_failed(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, create_pr=True)
        failed_result = PoolResult(
            tasks_completed=3, tasks_failed=2, total_invocations=20, worker_stats=[],
        )
        mocks = self._setup_mocks(pool_result=failed_result)

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"],
                            _check_gh_available=AsyncMock(return_value=True)):
            result = await run_prd_pipeline(config)

        assert result.pr_url is None

    async def test_cleanup_runs_on_success(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            await run_prd_pipeline(config)

        # reset_db called in pipeline body + finally
        assert mocks["reset_db"].await_count >= 1
        assert mocks["cleanup_sdk"].call_count >= 1

    async def test_cleanup_runs_on_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        mocks = self._setup_mocks()
        mocks["decomposition"].side_effect = RuntimeError("boom")

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"]):
            result = await run_prd_pipeline(config)

        assert result.error_message is not None
        # Cleanup still runs in finally
        assert mocks["reset_db"].await_count >= 1
        assert mocks["cleanup_sdk"].call_count >= 1

    async def test_gh_not_available_fails_fast(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, create_pr=True)
        mocks = self._setup_mocks()

        with patch.multiple("tdd_orchestrator.prd_pipeline",
                            GitCoordinator=MagicMock(return_value=mocks["git"]),
                            setup_project_context=mocks["setup_context"],
                            run_decomposition=mocks["decomposition"],
                            get_db=mocks["get_db"],
                            reset_db=mocks["reset_db"],
                            _cleanup_sdk_processes=mocks["cleanup_sdk"],
                            WorkerPool=mocks["pool_cls"],
                            OrchestratorDB=mocks["explicit_db_cls"],
                            _check_gh_available=AsyncMock(return_value=False)):
            result = await run_prd_pipeline(config)

        assert "gh" in (result.error_message or "").lower()
        # Pipeline didn't even start decomposition
        mocks["decomposition"].assert_not_awaited()
