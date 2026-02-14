"""Tests for get_pending_phases() in TaskMixin.

Verifies that pending phases are returned correctly, in ascending order,
skipping phases where all tasks are complete.
"""

from __future__ import annotations

import pytest

from tdd_orchestrator.database.singleton import get_db


class TestGetPendingPhasesBasicRetrieval:
    """Tests for basic pending phase retrieval."""

    async def test_returns_phases_with_pending_tasks(self) -> None:
        """Phases 0, 1, 2 each have pending tasks -> returns [0, 1, 2]."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "pending", 0, 0),
                ("TDD-1A", "Task 1A", "pending", 1, 0),
                ("TDD-2A", "Task 2A", "pending", 2, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_pending_phases()
        assert result == [0, 1, 2]

    async def test_returns_empty_when_no_pending(self) -> None:
        """All tasks complete -> returns []."""
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
            ],
        )
        await db._conn.commit()

        result = await db.get_pending_phases()
        assert result == []

    async def test_returns_empty_on_empty_db(self) -> None:
        """No tasks at all -> returns []."""
        db = await get_db()
        result = await db.get_pending_phases()
        assert result == []


class TestGetPendingPhasesFiltering:
    """Tests for phase filtering behavior."""

    async def test_skips_completed_phases(self) -> None:
        """Phase 0 all complete, phase 1 pending -> returns [1]."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0),
                ("TDD-0B", "Task 0B", "complete", 0, 1),
                ("TDD-1A", "Task 1A", "pending", 1, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_pending_phases()
        assert result == [1]

    async def test_phases_in_ascending_order(self) -> None:
        """Phases seeded as 2, 0, 1 -> returns [0, 1, 2]."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-2A", "Task 2A", "pending", 2, 0),
                ("TDD-0A", "Task 0A", "pending", 0, 0),
                ("TDD-1A", "Task 1A", "pending", 1, 0),
            ],
        )
        await db._conn.commit()

        result = await db.get_pending_phases()
        assert result == [0, 1, 2]

    async def test_returns_int_types(self) -> None:
        """Verify elements are int, not Any or str."""
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

        result = await db.get_pending_phases()
        assert len(result) == 1
        assert isinstance(result[0], int)

    async def test_includes_phase_with_mixed_statuses(self) -> None:
        """Phase with both pending and complete tasks -> phase is included."""
        db = await get_db()
        assert db._conn is not None

        await db._conn.executemany(
            """
            INSERT INTO tasks (task_key, title, status, phase, sequence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("TDD-0A", "Task 0A", "complete", 0, 0),
                ("TDD-0B", "Task 0B", "pending", 0, 1),
            ],
        )
        await db._conn.commit()

        result = await db.get_pending_phases()
        assert result == [0]
