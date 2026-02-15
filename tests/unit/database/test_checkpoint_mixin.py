"""Tests for CheckpointMixin database operations.

Covers stage resume queries, run-task associations, and pipeline
checkpoint save/load.
"""

from __future__ import annotations

from tdd_orchestrator.database.singleton import get_db


class TestGetLastCompletedStage:
    """Tests for get_last_completed_stage()."""

    async def test_returns_none_when_no_attempts(self) -> None:
        """No attempts recorded returns None."""
        db = await get_db()
        # Create a task
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        await db._conn.commit()

        result = await db.get_last_completed_stage(1)
        assert result is None

    async def test_returns_latest_successful_stage(self) -> None:
        """Returns the most recent successful stage."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        # Insert two successful attempts
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (1, 'red', 1, 1, datetime('now', '-2 minutes'))""",
        )
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (1, 'green', 1, 1, datetime('now', '-1 minutes'))""",
        )
        await db._conn.commit()

        result = await db.get_last_completed_stage(1)
        assert result == "green"

    async def test_ignores_failed_attempts(self) -> None:
        """Failed attempts are not returned."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        # Red succeeded, green failed
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (1, 'red', 1, 1, datetime('now', '-2 minutes'))""",
        )
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (1, 'green', 1, 0, datetime('now', '-1 minutes'))""",
        )
        await db._conn.commit()

        result = await db.get_last_completed_stage(1)
        assert result == "red"

    async def test_with_multiple_stages_returns_latest(self) -> None:
        """With red, green, verify all successful, returns verify."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        for i, stage in enumerate(["red", "green", "verify"]):
            await db._conn.execute(
                f"""INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
                    VALUES (1, ?, 1, 1, datetime('now', '-{3-i} minutes'))""",
                (stage,),
            )
        await db._conn.commit()

        result = await db.get_last_completed_stage(1)
        assert result == "verify"


class TestAssociateTaskWithRun:
    """Tests for associate_task_with_run()."""

    async def test_creates_association(self) -> None:
        """Creates a run_tasks record."""
        db = await get_db()
        assert db._conn is not None
        # Create task and run
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status) VALUES (2, 'running')",
        )
        await db._conn.commit()

        row_id = await db.associate_task_with_run(1, 1)
        assert row_id > 0

        # Verify record exists
        async with db._conn.execute(
            "SELECT * FROM run_tasks WHERE run_id = 1 AND task_id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["resume_from_stage"] is None

    async def test_with_resume_stage(self) -> None:
        """Records resume_from_stage when provided."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status) VALUES (2, 'running')",
        )
        await db._conn.commit()

        await db.associate_task_with_run(1, 1, resume_from_stage="red")

        async with db._conn.execute(
            "SELECT resume_from_stage FROM run_tasks WHERE run_id = 1 AND task_id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["resume_from_stage"] == "red"


class TestCompleteRunTask:
    """Tests for complete_run_task()."""

    async def test_marks_task_completed(self) -> None:
        """Updates completed_at and final_status."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, phase, sequence) VALUES (?, ?, 0, 0)",
            ("T-01", "Test task"),
        )
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status) VALUES (2, 'running')",
        )
        await db._conn.commit()

        await db.associate_task_with_run(1, 1)
        await db.complete_run_task(1, 1, "completed")

        async with db._conn.execute(
            "SELECT final_status, completed_at FROM run_tasks WHERE run_id = 1 AND task_id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["final_status"] == "completed"
            assert row["completed_at"] is not None


class TestGetResumableTasks:
    """Tests for get_resumable_tasks()."""

    async def test_returns_empty_when_no_tasks(self) -> None:
        """No tasks with attempts returns empty list."""
        db = await get_db()
        result = await db.get_resumable_tasks()
        assert result == []

    async def test_finds_tasks_with_attempts(self) -> None:
        """Returns pending tasks that have successful attempts."""
        db = await get_db()
        assert db._conn is not None
        # Create a pending task with a successful red attempt
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, status, phase, sequence) "
            "VALUES ('T-01', 'Test', 'pending', 0, 0)",
        )
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (1, 'red', 1, 1, datetime('now'))""",
        )
        # Create a complete task (should NOT appear)
        await db._conn.execute(
            "INSERT INTO tasks (task_key, title, status, phase, sequence) "
            "VALUES ('T-02', 'Done', 'complete', 0, 1)",
        )
        await db._conn.execute(
            """INSERT INTO attempts (task_id, stage, attempt_number, success, started_at)
               VALUES (2, 'verify', 1, 1, datetime('now'))""",
        )
        await db._conn.commit()

        result = await db.get_resumable_tasks()
        assert len(result) == 1
        assert result[0]["task_key"] == "T-01"
        assert result[0]["last_stage"] == "red"


class TestPipelineCheckpoint:
    """Tests for save/load pipeline checkpoint."""

    async def test_save_and_load_checkpoint(self) -> None:
        """Saved checkpoint can be loaded back."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status, pipeline_type) "
            "VALUES (2, 'running', 'run-prd')",
        )
        await db._conn.commit()

        state = {"stage_reached": "decompose", "branch_name": "feat/test"}
        await db.save_pipeline_checkpoint(1, state)

        loaded = await db.load_pipeline_checkpoint(1)
        assert loaded is not None
        assert loaded["stage_reached"] == "decompose"
        assert loaded["branch_name"] == "feat/test"

    async def test_load_returns_none_for_missing(self) -> None:
        """Loading checkpoint from run without one returns None."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status) VALUES (2, 'running')",
        )
        await db._conn.commit()

        result = await db.load_pipeline_checkpoint(1)
        assert result is None


class TestFindResumableRun:
    """Tests for find_resumable_run()."""

    async def test_returns_latest_incomplete(self) -> None:
        """Returns the most recent incomplete run of the given type."""
        db = await get_db()
        assert db._conn is not None
        # Create two run-prd runs: one completed, one failed
        await db._conn.execute(
            "INSERT INTO execution_runs (id, max_workers, status, pipeline_type) "
            "VALUES (1, 2, 'completed', 'run-prd')",
        )
        await db._conn.execute(
            "INSERT INTO execution_runs (id, max_workers, status, pipeline_type) "
            "VALUES (2, 2, 'failed', 'run-prd')",
        )
        await db._conn.commit()

        result = await db.find_resumable_run("run-prd")
        assert result == 2

    async def test_ignores_completed_runs(self) -> None:
        """Completed runs are not returned."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status, pipeline_type) "
            "VALUES (2, 'completed', 'run-prd')",
        )
        await db._conn.commit()

        result = await db.find_resumable_run("run-prd")
        assert result is None

    async def test_ignores_different_pipeline_type(self) -> None:
        """Runs of different pipeline type are not returned."""
        db = await get_db()
        assert db._conn is not None
        await db._conn.execute(
            "INSERT INTO execution_runs (max_workers, status, pipeline_type) "
            "VALUES (2, 'running', 'run')",
        )
        await db._conn.commit()

        result = await db.find_resumable_run("run-prd")
        assert result is None
