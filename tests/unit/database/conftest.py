"""Shared fixtures for database unit tests.

Sets up an in-memory database via the singleton for testing mixins.
"""

from __future__ import annotations

import pytest

from tdd_orchestrator.database.singleton import get_db, reset_db, set_db_path


@pytest.fixture(autouse=True)
async def reset_database_singleton(request: pytest.FixtureRequest) -> None:
    """Reset database singleton before each test to ensure isolation.

    Uses an in-memory database for fast, isolated tests.
    Seeds test data based on the test class to support runs_mixin tests.
    """
    # Reset any existing singleton
    await reset_db()

    # Configure to use in-memory database
    set_db_path(":memory:")

    # Initialize the database (connects and creates schema)
    db = await get_db()

    # Seed test data based on test class
    test_class = request.node.parent.name if request.node.parent else ""

    # Tests that expect seeded run data
    needs_runs_data = test_class in (
        "TestGetExecutionRunsBasicRetrieval",
        "TestGetExecutionRunsStatusFiltering",
        "TestGetExecutionRunsLimitParameter",
        "TestRunRecordStructure",
        "TestReturnTypeConsistency",
    )

    # Tests that expect a running run
    needs_running_run = test_class == "TestGetCurrentRunBasicRetrieval" and (
        "running_run_when_one_exists" in request.node.name
    )

    # Tests that expect seeded task data
    needs_tasks_data = test_class in (
        "TestGetTasksByStatusBasicRetrieval",
        "TestGetTasksByStatusRowContents",
    )

    if needs_runs_data and db._conn:
        # Seed 5 runs: 3 passed, 2 failed (for execution_id=1)
        await db._conn.executemany(
            """
            INSERT INTO execution_runs (id, status, started_at, max_workers)
            VALUES (?, ?, datetime('now', ?), 4)
            """,
            [
                (1, "passed", "-5 minutes"),
                (2, "passed", "-4 minutes"),
                (3, "passed", "-3 minutes"),
                (4, "failed", "-2 minutes"),
                (5, "failed", "-1 minutes"),
            ],
        )
        await db._conn.commit()

    if needs_running_run and db._conn:
        # Seed a running run for get_current_run tests
        await db._conn.execute(
            """
            INSERT INTO execution_runs (id, status, started_at, max_workers)
            VALUES (1, 'running', datetime('now'), 4)
            """
        )
        await db._conn.commit()

    if needs_tasks_data and db._conn:
        # Determine number of tasks based on test class
        if test_class == "TestGetTasksByStatusBasicRetrieval":
            # Seed 3 pending and 2 in_progress tasks
            await db._conn.executemany(
                """
                INSERT INTO tasks (id, spec_id, task_key, title, status, phase, sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (1, 1, "TDD-1", "Task 1", "pending", 0, 1),
                    (2, 1, "TDD-2", "Task 2", "pending", 0, 2),
                    (3, 1, "TDD-3", "Task 3", "pending", 0, 3),
                    (4, 1, "TDD-4", "Task 4", "in_progress", 0, 4),
                    (5, 1, "TDD-5", "Task 5", "in_progress", 0, 5),
                ],
            )
            await db._conn.commit()
        elif test_class == "TestGetTasksByStatusRowContents":
            # Seed 5 pending tasks with distinct spec_ids
            await db._conn.executemany(
                """
                INSERT INTO tasks (id, spec_id, task_key, title, status, phase, sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (1, 1, "TDD-1", "Task 1", "pending", 0, 1),
                    (2, 2, "TDD-2", "Task 2", "pending", 0, 2),
                    (3, 3, "TDD-3", "Task 3", "pending", 0, 3),
                    (4, 4, "TDD-4", "Task 4", "pending", 0, 4),
                    (5, 5, "TDD-5", "Task 5", "pending", 0, 5),
                ],
            )
            await db._conn.commit()

    yield

    # Clean up after test
    await reset_db()
