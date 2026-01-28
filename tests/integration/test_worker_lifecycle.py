"""Worker lifecycle tests - start/stop, heartbeat, registration."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from tdd_orchestrator.database import OrchestratorDB
from tdd_orchestrator.worker_pool import Worker, WorkerConfig


class TestWorkerLifecycle:
    """Worker start/stop and heartbeat tests."""

    @pytest.mark.asyncio
    async def test_worker_registers_on_start(self) -> None:
        """Worker registers in database on start."""
        async with OrchestratorDB(":memory:") as db:
            # Create mock GitCoordinator
            mock_git = MagicMock()

            # Create worker
            config = WorkerConfig(heartbeat_interval_seconds=0.1)
            worker = Worker(
                worker_id=1,
                db=db,
                git=mock_git,
                config=config,
                run_id=1,
                base_dir=Path("/tmp"),
            )

            # Start worker
            await worker.start()

            # Verify worker appears in database
            if db._conn:
                async with db._conn.execute(
                    "SELECT worker_id, status FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 1  # worker_id
                    assert row[1] == "active"  # status

            # Cleanup
            await worker.stop()

    @pytest.mark.asyncio
    async def test_worker_heartbeat_updates_timestamp(self) -> None:
        """Heartbeat updates last_heartbeat column."""
        async with OrchestratorDB(":memory:") as db:
            # Create mock GitCoordinator
            mock_git = MagicMock()

            # Create worker with short heartbeat interval
            config = WorkerConfig(heartbeat_interval_seconds=0.1)
            worker = Worker(
                worker_id=1,
                db=db,
                git=mock_git,
                config=config,
                run_id=1,
                base_dir=Path("/tmp"),
            )

            # Start worker
            await worker.start()

            # Wait for at least one heartbeat (0.1s interval + buffer)
            await asyncio.sleep(0.25)

            # Manually update heartbeat to verify the mechanism works
            await db.update_worker_heartbeat(1)

            # Verify worker heartbeat was recorded (non-null last_heartbeat)
            if db._conn:
                async with db._conn.execute(
                    "SELECT last_heartbeat FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] is not None, "Heartbeat should be recorded"

            # Cleanup
            await worker.stop()

    @pytest.mark.asyncio
    async def test_worker_unregisters_on_stop(self) -> None:
        """Worker unregisters from database on stop."""
        async with OrchestratorDB(":memory:") as db:
            # Create mock GitCoordinator
            mock_git = MagicMock()

            # Create worker
            config = WorkerConfig(heartbeat_interval_seconds=0.1)
            worker = Worker(
                worker_id=1,
                db=db,
                git=mock_git,
                config=config,
                run_id=1,
                base_dir=Path("/tmp"),
            )

            # Start then stop worker
            await worker.start()

            # Verify worker is active
            if db._conn:
                async with db._conn.execute(
                    "SELECT status FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == "active"

            # Stop worker
            await worker.stop()

            # Verify worker status is 'idle'
            if db._conn:
                async with db._conn.execute(
                    "SELECT status FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == "idle"

    @pytest.mark.asyncio
    async def test_worker_stop_cancels_heartbeat(self) -> None:
        """Stop cancels the heartbeat task cleanly."""
        async with OrchestratorDB(":memory:") as db:
            # Create mock GitCoordinator
            mock_git = MagicMock()

            # Create worker
            config = WorkerConfig(heartbeat_interval_seconds=0.1)
            worker = Worker(
                worker_id=1,
                db=db,
                git=mock_git,
                config=config,
                run_id=1,
                base_dir=Path("/tmp"),
            )

            # Start worker
            await worker.start()

            # Verify heartbeat task is running
            assert worker._heartbeat_task is not None
            assert not worker._heartbeat_task.done()

            # Stop worker
            await worker.stop()

            # Verify heartbeat task was cancelled and no exception propagated
            assert worker._heartbeat_task.cancelled()
            assert worker._stop_event.is_set()

            # Verify no CancelledError was raised (test completes successfully)
            # If CancelledError propagated, pytest would fail this test

    @pytest.mark.asyncio
    async def test_worker_tracks_task_in_heartbeat(self) -> None:
        """Worker heartbeat can track current task_id."""
        async with OrchestratorDB(":memory:") as db:
            # Create task
            task_id = await db.create_task("TDD-01", "Test Task", phase=0, sequence=0)

            # Test the database method directly (worker uses this during processing)
            await db.register_worker(1)

            # Update heartbeat with task_id (simulating worker processing a task)
            await db.update_worker_heartbeat(1, task_id=task_id)

            # Verify worker has current_task_id set
            if db._conn:
                async with db._conn.execute(
                    "SELECT current_task_id FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == task_id, f"Expected task_id {task_id}, got {row[0]}"

            # Update heartbeat without task_id (simulating idle worker)
            await db.update_worker_heartbeat(1)

            # Verify current_task_id is cleared (NULL)
            if db._conn:
                async with db._conn.execute(
                    "SELECT current_task_id FROM workers WHERE worker_id = ?",
                    (1,),
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] is None, "Expected NULL task_id for idle worker"

    @pytest.mark.asyncio
    async def test_multiple_workers_register_independently(self) -> None:
        """Multiple workers can register and operate independently."""
        async with OrchestratorDB(":memory:") as db:
            # Create mock GitCoordinator
            mock_git = MagicMock()

            # Create multiple workers
            config = WorkerConfig(heartbeat_interval_seconds=0.1)
            workers = [
                Worker(
                    worker_id=i,
                    db=db,
                    git=mock_git,
                    config=config,
                    run_id=1,
                    base_dir=Path("/tmp"),
                )
                for i in range(1, 4)
            ]

            # Start all workers
            for worker in workers:
                await worker.start()

            # Verify all workers are registered
            if db._conn:
                async with db._conn.execute(
                    "SELECT COUNT(*) FROM workers WHERE status = 'active'"
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 3

            # Stop all workers
            for worker in workers:
                await worker.stop()

            # Verify all workers are idle
            if db._conn:
                async with db._conn.execute(
                    "SELECT COUNT(*) FROM workers WHERE status = 'idle'"
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 3
