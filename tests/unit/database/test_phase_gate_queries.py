"""Tests for phase gate query methods in TaskMixin.

Verifies get_tasks_in_phases_before() and get_test_files_from_phases_before()
return correct results for phase gate validation.
"""

from __future__ import annotations

from tdd_orchestrator.database.singleton import get_db


class TestGetTasksInPhasesBefore:
    """Tests for get_tasks_in_phases_before()."""

    async def test_returns_prior_tasks(self) -> None:
        """Phases 0, 1, 2 seeded -> query(2) returns phase 0 and 1 tasks."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0),
                ("TDD-1A", "Task 1A", "complete", 1, 0),
                ("TDD-2A", "Task 2A", "pending", 2, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_tasks_in_phases_before(2)
        keys = [r["task_key"] for r in result]
        assert "TDD-0A" in keys
        assert "TDD-1A" in keys
        assert "TDD-2A" not in keys

    async def test_returns_empty_for_first_phase(self) -> None:
        """query(0) -> [] since no phases < 0."""
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

        result = await db.get_tasks_in_phases_before(0)
        assert result == []

    async def test_includes_all_statuses(self) -> None:
        """Complete, blocked, and pending tasks all returned."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0),
                ("TDD-0B", "Task 0B", "blocked", 0, 1),
                ("TDD-0C", "Task 0C", "pending", 0, 2),
                ("TDD-1A", "Task 1A", "pending", 1, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_tasks_in_phases_before(1)
        keys = [r["task_key"] for r in result]
        assert "TDD-0A" in keys
        assert "TDD-0B" in keys
        assert "TDD-0C" in keys

    async def test_ordered_by_phase_sequence(self) -> None:
        """Results are ordered by phase ASC, then sequence ASC."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-1B", "Task 1B", "complete", 1, 1),
                ("TDD-0A", "Task 0A", "complete", 0, 0),
                ("TDD-1A", "Task 1A", "complete", 1, 0),
                ("TDD-0B", "Task 0B", "complete", 0, 1),
            ],
        )
        await db._conn.commit()

        result = await db.get_tasks_in_phases_before(2)
        keys = [r["task_key"] for r in result]
        assert keys == ["TDD-0A", "TDD-0B", "TDD-1A", "TDD-1B"]


class TestGetTestFilesFromPhasesBefore:
    """Tests for get_test_files_from_phases_before()."""

    async def test_returns_test_file_paths(self) -> None:
        """Phases 0, 1 with test_files -> query(2) returns those paths."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence, test_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0, "tests/test_a.py"),
                ("TDD-1A", "Task 1A", "complete", 1, 0, "tests/test_b.py"),
                ("TDD-2A", "Task 2A", "pending", 2, 0, "tests/test_c.py"),
            ],
        )
        await db._conn.commit()

        result = await db.get_test_files_from_phases_before(2)
        assert "tests/test_a.py" in result
        assert "tests/test_b.py" in result
        assert "tests/test_c.py" not in result

    async def test_filters_nulls(self) -> None:
        """Tasks with NULL test_file excluded from results."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence, test_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0, "tests/test_a.py"),
                ("TDD-0B", "Task 0B", "complete", 0, 1, None),
            ],
        )
        await db._conn.commit()

        result = await db.get_test_files_from_phases_before(1)
        assert result == ["tests/test_a.py"]

    async def test_returns_distinct(self) -> None:
        """Same test_file in two tasks -> returned once."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence, test_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0, "tests/test_shared.py"),
                ("TDD-0B", "Task 0B", "complete", 0, 1, "tests/test_shared.py"),
            ],
        )
        await db._conn.commit()

        result = await db.get_test_files_from_phases_before(1)
        assert result == ["tests/test_shared.py"]

    async def test_returns_empty_for_first_phase(self) -> None:
        """query(0) -> [] since no phases < 0."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.execute(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence, test_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("TDD-0A", "Task 0A", "pending", 0, 0, "tests/test_a.py"),
        )
        await db._conn.commit()

        result = await db.get_test_files_from_phases_before(0)
        assert result == []
