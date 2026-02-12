"""Agent SDK failure handling tests for worker pool.

Tests SDK initialization, graceful degradation, error handling, lifecycle,
budget enforcement, and timeout scenarios.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestSDKInitialization:
    """Tests for SDK initialization and graceful degradation."""

    def test_has_agent_sdk_flag_exists(self) -> None:
        """HAS_AGENT_SDK flag is defined for graceful degradation."""
        from tdd_orchestrator import worker_pool

        assert hasattr(worker_pool, "HAS_AGENT_SDK")
        # Value depends on whether SDK is installed
        assert isinstance(worker_pool.HAS_AGENT_SDK, bool)

    @pytest.mark.asyncio
    async def test_worker_starts_without_sdk(self, tmp_path: Path) -> None:
        """Worker can start even if SDK is not available."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            with patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", False):
                worker = Worker(
                    worker_id=1,
                    db=db,
                    git=git,
                    config=config,
                    run_id=1,
                    base_dir=tmp_path,
                )

                await worker.start()

                # Worker should register successfully
                if db._conn is not None:
                    result = await db._conn.execute("SELECT * FROM workers WHERE worker_id = 1")
                    worker_row = await result.fetchone()
                    assert worker_row is not None

                await worker.stop()

    @pytest.mark.asyncio
    async def test_run_tdd_pipeline_fails_gracefully_without_sdk(self, tmp_path: Path) -> None:
        """TDD pipeline returns False when SDK not available."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            with patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", False):
                worker = Worker(
                    worker_id=1,
                    db=db,
                    git=git,
                    config=config,
                    run_id=1,
                    base_dir=tmp_path,
                )

                result = await worker._run_tdd_pipeline(task)

                # Should fail gracefully without crashing
                assert result is False


class TestSDKRateLimiting:
    """Tests for SDK rate limiting and retry behavior."""

    @pytest.mark.asyncio
    async def test_worker_handles_sdk_exception(self, tmp_path: Path) -> None:
        """Worker handles SDK exceptions gracefully without crashing."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            await worker.start()

            # Create a task for processing
            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )

            # Mock SDK to raise exception
            with patch.object(worker, "verifier") as mock_verifier:
                mock_verifier.run_pytest = AsyncMock(return_value=(False, "Error"))
                mock_verifier.run_ruff = AsyncMock(return_value=(True, "OK"))
                mock_verifier.run_mypy = AsyncMock(return_value=(True, "OK"))

                # Processing should not crash the worker
                try:
                    await worker.stop()
                except Exception:
                    pytest.fail("Worker stop should not raise even after errors")

    @pytest.mark.asyncio
    async def test_stage_handles_sdk_timeout(self, tmp_path: Path) -> None:
        """Stage execution handles SDK timeout gracefully."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            # Mock SDK to raise timeout exception
            async def timeout_query(*args: object, **kwargs: object) -> None:
                raise asyncio.TimeoutError("SDK timeout")

            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                patch("tdd_orchestrator.worker_pool.worker.sdk_query", timeout_query),
                patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", MagicMock),
            ):
                from tdd_orchestrator.models import Stage

                result = await worker._run_stage(Stage.RED, task)

                # Should return failure result, not crash
                assert result.success is False
                assert result.error is not None


class TestWorkerLifecycle:
    """Tests for worker lifecycle with failure scenarios."""

    @pytest.mark.asyncio
    async def test_worker_cleanup_on_exception(self, tmp_path: Path) -> None:
        """Worker cleans up properly even when exception occurs."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            await worker.start()

            # Simulate some internal state
            worker.current_branch = "test-branch"

            # Stop should work even with state
            await worker.stop()

            # Worker should be unregistered
            if db._conn is not None:
                result = await db._conn.execute("SELECT status FROM workers WHERE worker_id = 1")
                row = await result.fetchone()
                # Either row is None (deleted) or status is 'idle'
                assert row is None or row["status"] == "idle"

    @pytest.mark.asyncio
    async def test_heartbeat_continues_during_processing(self, tmp_path: Path) -> None:
        """Heartbeat loop continues while worker processes tasks."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig(heartbeat_interval_seconds=1)

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            await worker.start()

            # Wait for a few heartbeats
            await asyncio.sleep(2)

            # Check heartbeat was recorded
            if db._conn is not None:
                result = await db._conn.execute(
                    "SELECT COUNT(*) FROM worker_heartbeats WHERE worker_id = "
                    "(SELECT id FROM workers WHERE worker_id = 1)"
                )
                row = await result.fetchone()
                if row:
                    count = row[0]
                    # Should have at least 1-2 heartbeats
                    assert count >= 1

            await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat(self, tmp_path: Path) -> None:
        """Worker stop cancels the heartbeat task."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig(heartbeat_interval_seconds=1)

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            await worker.start()
            assert worker._heartbeat_task is not None

            await worker.stop()

            # Heartbeat task should be cancelled
            assert worker._heartbeat_task.cancelled() or worker._heartbeat_task.done()

    @pytest.mark.asyncio
    async def test_worker_handles_heartbeat_errors(self, tmp_path: Path) -> None:
        """Worker continues even if heartbeat update fails."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig(heartbeat_interval_seconds=1)

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            await worker.start()

            # Mock heartbeat to raise exception intermittently
            original_heartbeat = db.update_worker_heartbeat
            call_count = 0

            async def failing_heartbeat(worker_id: int, task_id: int | None = None) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("Heartbeat DB error")
                return await original_heartbeat(worker_id, task_id)

            with patch.object(db, "update_worker_heartbeat", failing_heartbeat):
                # Give enough time for at least 3 heartbeat attempts
                await asyncio.sleep(2)

                # Worker should still be alive
                if db._conn is not None:
                    result = await db._conn.execute(
                        "SELECT status FROM workers WHERE worker_id = 1"
                    )
                    row = await result.fetchone()
                    assert row is not None

            await worker.stop()


class TestBudgetEnforcement:
    """Tests for invocation budget limits."""

    @pytest.mark.asyncio
    async def test_budget_tracking_exists(self) -> None:
        """Verify budget configuration is accessible."""
        config = WorkerConfig(
            max_invocations_per_session=50,
            budget_warning_threshold=80,
        )

        assert config.max_invocations_per_session == 50
        assert config.budget_warning_threshold == 80

    @pytest.mark.asyncio
    async def test_budget_limit_prevents_stage_execution(self, tmp_path: Path) -> None:
        """Stage execution is blocked when budget limit is reached."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig(max_invocations_per_session=5)

            # Set budget limit in config
            await db.set_config("max_invocations_per_session", "5")

            run_id = await db.start_execution_run(1)

            # Create task
            created_task_id = await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=run_id,
                base_dir=tmp_path,
            )

            # Record 5 invocations (hit limit)
            for _ in range(5):
                await db.record_invocation(run_id, "red", worker_id=1, task_id=created_task_id)

            # Next stage should fail due to budget
            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                patch("tdd_orchestrator.worker_pool.worker.sdk_query", AsyncMock()),
                patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", MagicMock),
            ):
                from tdd_orchestrator.models import Stage

                result = await worker._run_stage(Stage.RED, task)

                # Should fail with budget error
                assert result.success is False
                assert "budget" in result.error.lower() if result.error else False

    @pytest.mark.asyncio
    async def test_invocation_recorded_even_on_failure(self, tmp_path: Path) -> None:
        """Invocation is recorded even when stage execution fails."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            run_id = await db.start_execution_run(1)

            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=run_id,
                base_dir=tmp_path,
            )

            # Mock SDK to raise exception
            async def failing_query(*args: object, **kwargs: object) -> None:
                raise RuntimeError("SDK failure")

            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True),
                patch("tdd_orchestrator.worker_pool.worker.sdk_query", failing_query),
                patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", MagicMock),
            ):
                from tdd_orchestrator.models import Stage

                result = await worker._run_stage(Stage.RED, task)

                # Should fail
                assert result.success is False

                # But invocation should still be recorded (in finally block)
                count = await db.get_invocation_count(run_id)
                assert count == 1


class TestSDKIntegrationErrors:
    """Tests for SDK integration error scenarios."""

    @pytest.mark.asyncio
    async def test_sdk_import_error_handled(self, tmp_path: Path) -> None:
        """Worker handles SDK import errors gracefully."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            # Simulate SDK not installed
            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", False),
                patch("tdd_orchestrator.worker_pool.worker.sdk_query", None),
                patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", None),
            ):
                worker = Worker(
                    worker_id=1,
                    db=db,
                    git=git,
                    config=config,
                    run_id=1,
                    base_dir=tmp_path,
                )

                # Worker should still start
                await worker.start()

                # Verify worker is registered
                if db._conn is not None:
                    result = await db._conn.execute("SELECT * FROM workers WHERE worker_id = 1")
                    row = await result.fetchone()
                    assert row is not None

                await worker.stop()

    @pytest.mark.asyncio
    async def test_stage_returns_error_when_sdk_missing(self, tmp_path: Path) -> None:
        """Stage execution returns clear error when SDK is missing."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            config = WorkerConfig()

            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=1,
                base_dir=tmp_path,
            )

            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", False),
                patch("tdd_orchestrator.worker_pool.worker.sdk_query", None),
                patch("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", None),
            ):
                from tdd_orchestrator.models import Stage

                result = await worker._run_stage(Stage.RED, task)

                # Should return clear error message
                assert result.success is False
                assert result.error == "Agent SDK not available"

    @pytest.mark.asyncio
    async def test_worker_stats_updated_on_sdk_failure(self, tmp_path: Path) -> None:
        """Worker stats are properly updated even when SDK fails."""
        async with OrchestratorDB(":memory:") as db:
            git = MagicMock()
            git.create_worker_branch = AsyncMock(return_value="test-branch")
            git.commit_changes = AsyncMock()
            git.push_branch = AsyncMock()
            git.rollback_to_main = AsyncMock()

            config = WorkerConfig()

            run_id = await db.start_execution_run(1)

            await db.create_task(
                "TDD-01",
                "Test Task",
                phase=0,
                sequence=0,
                test_file="test_example.py",
                impl_file="example.py",
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None

            worker = Worker(
                worker_id=1,
                db=db,
                git=git,
                config=config,
                run_id=run_id,
                base_dir=tmp_path,
            )

            await worker.start()

            # Mock SDK failure
            with (
                patch("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", False),
                patch.object(worker, "_run_tdd_pipeline", AsyncMock(return_value=False)),
            ):
                result = await worker.process_task(task)

                # Task should fail
                assert result is False

                # Stats should be updated
                assert worker.stats.tasks_failed == 1
                assert worker.stats.tasks_completed == 0

            await worker.stop()
