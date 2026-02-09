"""Tests for get_all_workers function.

Tests verify retrieval of aggregated worker statistics from v_worker_stats view.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tdd_orchestrator.database.mixins.worker_mixin import get_all_workers
from src.tdd_orchestrator.database.singleton import get_db, reset_db, set_db_path


class TestGetAllWorkersMultipleWorkers:
    """Tests for retrieving statistics when multiple workers exist."""

    @pytest.fixture(autouse=True)
    async def setup_database_with_workers(self) -> None:
        """Set up database with multiple workers having varying task counts."""
        await reset_db()
        set_db_path(":memory:")
        db = await get_db()

        if db._conn:
            # Insert multiple workers with different statuses
            await db._conn.executemany(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (?, ?, datetime('now'))
                """,
                [
                    (1, "active"),
                    (2, "idle"),
                    (3, "active"),
                ],
            )

            # Insert task claims with different outcomes
            await db._conn.executemany(
                """
                INSERT INTO task_claims (task_id, worker_id, claimed_at, released_at, outcome)
                VALUES (?, ?, datetime('now', ?), datetime('now'), ?)
                """,
                [
                    # Worker 1: 3 total claims, 2 completed, 1 failed
                    (1, 1, "-5 minutes", "completed"),
                    (2, 1, "-4 minutes", "completed"),
                    (3, 1, "-3 minutes", "failed"),
                    # Worker 2: 2 total claims, 1 completed, 1 failed
                    (4, 2, "-2 minutes", "completed"),
                    (5, 2, "-1 minutes", "failed"),
                    # Worker 3: 1 total claim, 1 completed, 0 failed
                    (6, 3, "-30 seconds", "completed"),
                ],
            )
            await db._conn.commit()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts_for_multiple_workers(self) -> None:
        """GIVEN the database contains rows in v_worker_stats for multiple workers,
        WHEN get_all_workers() is called with no arguments,
        THEN it returns a list of dicts (one per worker).
        """
        result = await get_all_workers()

        assert isinstance(result, list)
        assert len(result) == 3
        for worker in result:
            assert isinstance(worker, dict)

    @pytest.mark.asyncio
    async def test_each_worker_dict_contains_required_fields(self) -> None:
        """GIVEN the database contains multiple workers with varying task counts,
        WHEN get_all_workers() is called,
        THEN each dict contains worker_id, total_tasks, completed_tasks, failed_tasks, and current_status.
        """
        result = await get_all_workers()

        assert len(result) == 3
        required_fields = {"worker_id", "total_tasks", "completed_tasks", "failed_tasks", "current_status"}

        for worker in result:
            assert required_fields.issubset(set(worker.keys())), (
                f"Missing fields. Expected {required_fields}, got {set(worker.keys())}"
            )

    @pytest.mark.asyncio
    async def test_aggregated_data_matches_view_data(self) -> None:
        """GIVEN the database contains workers with known task counts,
        WHEN get_all_workers() is called,
        THEN the returned data matches the aggregated view data.
        """
        result = await get_all_workers()

        # Find worker 1 in results
        worker_1 = next((w for w in result if w.get("worker_id") == 1), None)
        assert worker_1 is not None, "Worker 1 not found in results"
        assert worker_1.get("total_tasks") == 3
        assert worker_1.get("completed_tasks") == 2
        assert worker_1.get("failed_tasks") == 1

        # Find worker 2 in results
        worker_2 = next((w for w in result if w.get("worker_id") == 2), None)
        assert worker_2 is not None, "Worker 2 not found in results"
        assert worker_2.get("total_tasks") == 2
        assert worker_2.get("completed_tasks") == 1
        assert worker_2.get("failed_tasks") == 1

        # Find worker 3 in results
        worker_3 = next((w for w in result if w.get("worker_id") == 3), None)
        assert worker_3 is not None, "Worker 3 not found in results"
        assert worker_3.get("total_tasks") == 1
        assert worker_3.get("completed_tasks") == 1
        assert worker_3.get("failed_tasks") == 0


class TestGetAllWorkersEmptyDatabase:
    """Tests for scenarios with no worker records."""

    @pytest.fixture(autouse=True)
    async def setup_empty_database(self) -> None:
        """Set up database with no workers."""
        await reset_db()
        set_db_path(":memory:")
        await get_db()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_workers(self) -> None:
        """GIVEN the database has no worker records (v_worker_stats returns zero rows),
        WHEN get_all_workers() is called,
        THEN it returns an empty list.
        """
        result = await get_all_workers()

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_empty_list_is_not_none(self) -> None:
        """GIVEN an empty workers table,
        WHEN get_all_workers() is called,
        THEN it returns an empty list (not None).
        """
        result = await get_all_workers()

        assert result is not None
        assert result == []


class TestGetAllWorkersSingleWorker:
    """Tests for scenarios with exactly one worker."""

    @pytest.fixture(autouse=True)
    async def setup_single_worker(self) -> None:
        """Set up database with exactly one worker."""
        await reset_db()
        set_db_path(":memory:")
        db = await get_db()

        if db._conn:
            # Insert single worker
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (42, 'active', datetime('now'))
                """
            )

            # Insert some task claims for this worker
            await db._conn.executemany(
                """
                INSERT INTO task_claims (task_id, worker_id, claimed_at, released_at, outcome)
                VALUES (?, 1, datetime('now', ?), datetime('now'), ?)
                """,
                [
                    (1, "-5 minutes", "completed"),
                    (2, "-4 minutes", "completed"),
                    (3, "-3 minutes", "failed"),
                    (4, "-2 minutes", "completed"),
                ],
            )
            await db._conn.commit()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_returns_single_element_list_for_one_worker(self) -> None:
        """GIVEN the database contains exactly one worker in v_worker_stats,
        WHEN get_all_workers() is called,
        THEN it returns a single-element list.
        """
        result = await get_all_workers()

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_single_worker_has_all_expected_fields(self) -> None:
        """GIVEN the database contains exactly one worker,
        WHEN get_all_workers() is called,
        THEN the returned worker dict contains all expected fields.
        """
        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]

        required_fields = {"worker_id", "total_tasks", "completed_tasks", "failed_tasks", "current_status"}
        assert required_fields.issubset(set(worker.keys())), (
            f"Missing fields. Expected {required_fields}, got {set(worker.keys())}"
        )

    @pytest.mark.asyncio
    async def test_single_worker_aggregated_statistics_correct(self) -> None:
        """GIVEN the database contains exactly one worker with known task claims,
        WHEN get_all_workers() is called,
        THEN the worker's aggregated statistics are correct.
        """
        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]

        assert worker.get("worker_id") == 42
        assert worker.get("total_tasks") == 4
        assert worker.get("completed_tasks") == 3
        assert worker.get("failed_tasks") == 1
        assert worker.get("current_status") == "active"


class TestGetAllWorkersDatabaseError:
    """Tests for error handling when database is unavailable."""

    @pytest.mark.asyncio
    async def test_raises_database_error_when_connection_closed(self) -> None:
        """GIVEN the database connection is closed or unavailable,
        WHEN get_all_workers() is called,
        THEN it raises a DatabaseError (or appropriate wrapped exception).
        """
        await reset_db()
        set_db_path(":memory:")
        db = await get_db()

        # Close the connection to simulate unavailability
        if db._conn:
            await db._conn.close()
            db._conn = None

        with pytest.raises(Exception):
            await get_all_workers()

    @pytest.mark.asyncio
    async def test_does_not_return_partial_results_on_error(self) -> None:
        """GIVEN the database connection becomes unavailable during query,
        WHEN get_all_workers() is called,
        THEN it raises an exception rather than returning partial results.
        """
        await reset_db()
        set_db_path(":memory:")
        db = await get_db()

        if db._conn:
            # Insert a worker first
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'active', datetime('now'))
                """
            )
            await db._conn.commit()

            # Close connection to simulate failure
            await db._conn.close()
            db._conn = None

        # Should raise, not return partial data
        with pytest.raises(Exception):
            await get_all_workers()


class TestGetAllWorkersNullAndZeroValues:
    """Tests for handling NULL or zero values in aggregate columns."""

    @pytest.fixture(autouse=True)
    async def setup_workers_with_zero_values(self) -> None:
        """Set up database with workers having zero task counts."""
        await reset_db()
        set_db_path(":memory:")
        db = await get_db()

        if db._conn:
            # Insert workers with no task claims (zero values)
            await db._conn.executemany(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (?, ?, datetime('now'))
                """,
                [
                    (1, "active"),
                    (2, "idle"),
                ],
            )
            await db._conn.commit()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_zero_values_returned_as_integers(self) -> None:
        """GIVEN v_worker_stats contains workers with zero completed_tasks and failed_tasks,
        WHEN get_all_workers() is called,
        THEN those fields are returned as 0 (integers) rather than None.
        """
        result = await get_all_workers()

        assert len(result) == 2
        for worker in result:
            assert worker.get("total_tasks") == 0
            assert worker.get("completed_tasks") == 0
            assert worker.get("failed_tasks") == 0
            # Verify they are integers, not None
            assert isinstance(worker.get("total_tasks"), int)
            assert isinstance(worker.get("completed_tasks"), int)
            assert isinstance(worker.get("failed_tasks"), int)

    @pytest.mark.asyncio
    async def test_consistent_typing_across_all_rows(self) -> None:
        """GIVEN v_worker_stats contains workers with varying aggregate values,
        WHEN get_all_workers() is called,
        THEN all fields have consistent typing across all rows.
        """
        result = await get_all_workers()

        assert len(result) == 2

        # All worker_id values should be integers
        for worker in result:
            worker_id = worker.get("worker_id")
            assert worker_id is not None
            assert isinstance(worker_id, int)

            total_tasks = worker.get("total_tasks")
            assert total_tasks is not None
            assert isinstance(total_tasks, int)

            completed_tasks = worker.get("completed_tasks")
            assert completed_tasks is not None
            assert isinstance(completed_tasks, int)

            failed_tasks = worker.get("failed_tasks")
            assert failed_tasks is not None
            assert isinstance(failed_tasks, int)

            current_status = worker.get("current_status")
            assert current_status is not None
            assert isinstance(current_status, str)


class TestGetAllWorkersReturnType:
    """Tests for verifying correct return types."""

    @pytest.fixture(autouse=True)
    async def setup_database(self) -> None:
        """Set up database for return type tests."""
        await reset_db()
        set_db_path(":memory:")
        await get_db()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_return_type_is_list(self) -> None:
        """GIVEN any database state,
        WHEN get_all_workers() is called,
        THEN the return type is always a list.
        """
        result = await get_all_workers()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_elements_are_dictionaries(self) -> None:
        """GIVEN a database with workers,
        WHEN get_all_workers() is called,
        THEN list elements are dict objects with key access.
        """
        db = await get_db()
        if db._conn:
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'active', datetime('now'))
                """
            )
            await db._conn.commit()

        result = await get_all_workers()

        if len(result) > 0:
            first_row = result[0]
            assert isinstance(first_row, dict)
            # Should support dict-like key access
            assert "worker_id" in first_row


class TestGetAllWorkersEdgeCases:
    """Edge case tests for get_all_workers."""

    @pytest.fixture(autouse=True)
    async def setup_database(self) -> None:
        """Set up database for edge case tests."""
        await reset_db()
        set_db_path(":memory:")
        await get_db()

        yield

        await reset_db()

    @pytest.mark.asyncio
    async def test_worker_with_only_completed_tasks(self) -> None:
        """GIVEN a worker with only completed tasks (no failures),
        WHEN get_all_workers() is called,
        THEN failed_tasks is 0.
        """
        db = await get_db()
        if db._conn:
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'active', datetime('now'))
                """
            )
            await db._conn.executemany(
                """
                INSERT INTO task_claims (task_id, worker_id, claimed_at, released_at, outcome)
                VALUES (?, 1, datetime('now'), datetime('now'), 'completed')
                """,
                [(1,), (2,), (3,)],
            )
            await db._conn.commit()

        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]
        assert worker.get("total_tasks") == 3
        assert worker.get("completed_tasks") == 3
        assert worker.get("failed_tasks") == 0

    @pytest.mark.asyncio
    async def test_worker_with_only_failed_tasks(self) -> None:
        """GIVEN a worker with only failed tasks (no completions),
        WHEN get_all_workers() is called,
        THEN completed_tasks is 0.
        """
        db = await get_db()
        if db._conn:
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'active', datetime('now'))
                """
            )
            await db._conn.executemany(
                """
                INSERT INTO task_claims (task_id, worker_id, claimed_at, released_at, outcome)
                VALUES (?, 1, datetime('now'), datetime('now'), 'failed')
                """,
                [(1,), (2,)],
            )
            await db._conn.commit()

        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]
        assert worker.get("total_tasks") == 2
        assert worker.get("completed_tasks") == 0
        assert worker.get("failed_tasks") == 2

    @pytest.mark.asyncio
    async def test_worker_with_dead_status(self) -> None:
        """GIVEN a worker with 'dead' status,
        WHEN get_all_workers() is called,
        THEN that worker is included with current_status='dead'.
        """
        db = await get_db()
        if db._conn:
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'dead', datetime('now'))
                """
            )
            await db._conn.commit()

        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]
        assert worker.get("current_status") == "dead"

    @pytest.mark.asyncio
    async def test_worker_with_idle_status(self) -> None:
        """GIVEN a worker with 'idle' status,
        WHEN get_all_workers() is called,
        THEN that worker is included with current_status='idle'.
        """
        db = await get_db()
        if db._conn:
            await db._conn.execute(
                """
                INSERT INTO workers (worker_id, status, last_heartbeat)
                VALUES (1, 'idle', datetime('now'))
                """
            )
            await db._conn.commit()

        result = await get_all_workers()

        assert len(result) == 1
        worker = result[0]
        assert worker.get("current_status") == "idle"
