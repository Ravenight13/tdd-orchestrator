"""Worker processing tests - TDD pipeline stage execution."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.models import Stage, VerifyResult
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestTaskProcessing:
    """TDD pipeline stage execution tests."""

    @pytest.mark.asyncio
    async def test_red_stage_succeeds_when_pytest_fails(self, tmp_path: Path) -> None:
        """RED stage succeeds when pytest fails (tests not yet implemented)."""
        async with OrchestratorDB(":memory:") as db:
            # Create test data
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_foo.py",
                impl_file="src/foo.py",
            )

            # Mock git coordinator and agent SDK
            mock_git = MagicMock()
            mock_git.create_worker_branch = AsyncMock(return_value="worker-1/TDD-01")

            # Create worker with single_branch_mode to avoid Git operations
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Create test file so RED verification finds it
            test_dir = tmp_path / "tests"
            test_dir.mkdir()
            (test_dir / "test_foo.py").write_text("def test_placeholder(): pass\n")

            # Mock verifier to return failing pytest (expected for RED stage)
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.return_value = (False, "FAILED: ImportError")

                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Created test file"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        # Run RED stage
                        task = await db.get_task_by_key("TDD-01")
                        assert task is not None  # Type guard
                        result = await worker._run_stage(Stage.RED, task)

                        # RED stage should SUCCEED when pytest FAILS
                        assert result.success is True
                        assert "FAILED" in result.output

    @pytest.mark.asyncio
    async def test_green_stage_succeeds_when_pytest_passes(self, tmp_path: Path) -> None:
        """GREEN stage succeeds when pytest passes."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-02",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_bar.py",
                impl_file="src/bar.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock verifier to return passing pytest
            with patch.object(worker.verifier, "run_pytest", new_callable=AsyncMock) as mock_pytest:
                mock_pytest.return_value = (True, "1 passed")

                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Implementation complete"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-02")
                        assert task is not None  # Type guard
                        # GREEN stage requires test_output parameter
                        result = await worker._run_stage(
                            Stage.GREEN, task, test_output="FAILED: tests not implemented"
                        )

                        # GREEN stage should succeed when pytest PASSES
                        assert result.success is True
                        assert "1 passed" in result.output

    @pytest.mark.asyncio
    async def test_verify_stage_collects_issues(self, tmp_path: Path) -> None:
        """VERIFY stage collects issues from failed tools."""
        async with OrchestratorDB(":memory:") as db:
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-03",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_baz.py",
                impl_file="src/baz.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock verifier with some failures
            mock_verify_result = VerifyResult(
                pytest_passed=True,
                pytest_output="1 passed",
                ruff_passed=False,
                ruff_output="F401 unused import",
                mypy_passed=False,
                mypy_output="error: Missing type annotation",
            )
            with patch.object(worker.verifier, "verify_all", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = mock_verify_result

                # Mock Agent SDK
                async def mock_query_gen(*args: object, **kwargs: object) -> object:
                    mock_message = MagicMock()
                    mock_message.text = "Verification complete"
                    yield mock_message

                with (
                    patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                    patch("tdd_orchestrator.worker_pool.worker.sdk_query", side_effect=mock_query_gen),
                ):
                    with patch(
                        "tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions",
                        return_value=MagicMock(),
                    ):
                        task = await db.get_task_by_key("TDD-03")
                        assert task is not None  # Type guard
                        result = await worker._run_stage(Stage.VERIFY, task)

                        # VERIFY should fail and populate issues
                        assert result.success is False
                        assert result.issues is not None
                        assert len(result.issues) == 2  # ruff + mypy failures

                        # Check issue structure
                        tool_names = [issue["tool"] for issue in result.issues]
                        assert "ruff" in tool_names
                        assert "mypy" in tool_names

    @pytest.mark.asyncio
    async def test_process_task_claims_before_processing(self, tmp_path: Path) -> None:
        """process_task claims task before running pipeline."""
        # Initialize git repo in tmp_path for GitStashGuard compatibility
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path, capture_output=True, check=True,
        )
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-04",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_claim.py",
                impl_file="src/claim.py",
            )

            mock_git = MagicMock()
            mock_git.commit_changes = AsyncMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock successful TDD pipeline
            with patch.object(worker, "_run_tdd_pipeline", new_callable=AsyncMock) as mock_pipeline:
                mock_pipeline.return_value = True

                task = await db.get_task_by_key("TDD-04")
                assert task is not None

                # Task should initially be pending
                assert task["status"] == "pending"
                assert task["claimed_by"] is None

                # Process task
                await worker.process_task(task)

                # Verify task was claimed (check updated status)
                updated_task = await db.get_task_by_key("TDD-04")
                assert updated_task is not None
                # Task should be complete after successful processing
                assert updated_task["status"] == "complete"

    @pytest.mark.asyncio
    async def test_process_task_releases_on_success(self, tmp_path: Path) -> None:
        """process_task releases task with 'completed' outcome on success."""
        # Initialize git repo in tmp_path for GitStashGuard compatibility
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path, capture_output=True, check=True,
        )
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-05",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_success.py",
                impl_file="src/success.py",
            )

            mock_git = MagicMock()
            mock_git.commit_changes = AsyncMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock successful pipeline
            with patch.object(worker, "_run_tdd_pipeline", new_callable=AsyncMock) as mock_pipeline:
                mock_pipeline.return_value = True

                task = await db.get_task_by_key("TDD-05")
                assert task is not None

                # Process task
                success = await worker.process_task(task)

                # Verify success
                assert success is True

                # Verify task status and release
                final_task = await db.get_task_by_key("TDD-05")
                assert final_task is not None
                assert final_task["status"] == "complete"
                assert final_task["claimed_by"] is None  # Released

                # Verify worker stats
                assert worker.stats.tasks_completed == 1
                assert worker.stats.tasks_failed == 0

    @pytest.mark.asyncio
    async def test_process_task_releases_on_failure(self, tmp_path: Path) -> None:
        """process_task releases task with 'failed' outcome on failure."""
        # Initialize git repo in tmp_path for GitStashGuard compatibility
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path, capture_output=True, check=True,
        )
        async with OrchestratorDB(":memory:") as db:
            await db.register_worker(1)
            run_id = await db.start_execution_run(max_workers=1)
            await db.create_task(
                "TDD-06",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="tests/test_failure.py",
                impl_file="src/failure.py",
            )

            mock_git = MagicMock()
            config = WorkerConfig(single_branch_mode=True)
            worker = Worker(1, db, mock_git, config, run_id, tmp_path)

            # Mock failed pipeline
            with patch.object(worker, "_run_tdd_pipeline", new_callable=AsyncMock) as mock_pipeline:
                mock_pipeline.return_value = False

                task = await db.get_task_by_key("TDD-06")
                assert task is not None

                # Process task
                success = await worker.process_task(task)

                # Verify failure
                assert success is False

                # Verify task status and release
                final_task = await db.get_task_by_key("TDD-06")
                assert final_task is not None
                assert final_task["status"] == "blocked"
                assert final_task["claimed_by"] is None  # Released

                # Verify worker stats
                assert worker.stats.tasks_completed == 0
                assert worker.stats.tasks_failed == 1
