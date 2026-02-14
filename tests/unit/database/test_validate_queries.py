"""Tests for validate-related DB query methods.

Tests for get_all_phases() on TaskMixin and get_latest_run_id() on RunsMixin.
"""

from __future__ import annotations

from tdd_orchestrator.database.singleton import get_db


class TestGetAllPhases:
    """Tests for get_all_phases() returning all distinct phases."""

    async def test_returns_all_phases_with_mixed_statuses(self) -> None:
        """Phases 0,1,2 with mixed statuses -> returns [0, 1, 2]."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "pending", 0, 0),
                ("TDD-0B", "Task 0B", "complete", 0, 1),
                ("TDD-1A", "Task 1A", "complete", 1, 0),
                ("TDD-2A", "Task 2A", "blocked", 2, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_all_phases()
        assert result == [0, 1, 2]

    async def test_returns_empty_when_no_tasks(self) -> None:
        """No tasks at all -> returns []."""
        db = await get_db()
        result = await db.get_all_phases()
        assert result == []

    async def test_returns_single_phase(self) -> None:
        """All tasks in phase 0 -> returns [0]."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "pending", 0, 0),
                ("TDD-0B", "Task 0B", "complete", 0, 1),
            ],
        )
        await db._conn.commit()

        result = await db.get_all_phases()
        assert result == [0]

    async def test_returns_int_types(self) -> None:
        """Verify elements are int, not Any."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.execute(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("TDD-0A", "Task 0A", "pending", 0, 0),
        )
        await db._conn.commit()

        result = await db.get_all_phases()
        assert len(result) == 1
        assert isinstance(result[0], int)


class TestGetLatestRunId:
    """Tests for get_latest_run_id() returning the most recent run."""

    async def test_returns_most_recent_run_id(self) -> None:
        """Three runs -> returns the last one started."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO execution_runs (id, status, started_at, max_workers)
            VALUES (?, ?, datetime('now', ?), ?)
            """,
            [
                (1, "completed", "-3 minutes", 2),
                (2, "completed", "-2 minutes", 2),
                (3, "running", "-1 minutes", 2),
            ],
        )
        await db._conn.commit()

        result = await db.get_latest_run_id()
        assert result == 3

    async def test_returns_none_when_no_runs(self) -> None:
        """No execution runs -> returns None."""
        db = await get_db()
        result = await db.get_latest_run_id()
        assert result is None
