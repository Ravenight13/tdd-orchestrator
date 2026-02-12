"""Database connection management tests.

Tests that verify the OrchestratorDB connection lifecycle, including:
- Context manager entry/exit
- Connection establishment and cleanup
- Schema initialization
- Reconnection after close
- Proper resource cleanup
"""

from pathlib import Path

import pytest

from tdd_orchestrator.database import OrchestratorDB


class TestDatabaseConnection:
    """Connection lifecycle tests.

    These tests verify that the database connection is properly managed
    through its lifecycle, from opening through closing, and that schema
    initialization happens correctly on first connection.
    """

    @pytest.mark.asyncio
    async def test_context_manager_opens_connection(self) -> None:
        """DB connection is established in context manager.

        Verifies that using OrchestratorDB as an async context manager
        establishes a database connection that is available for use.
        """
        async with OrchestratorDB(":memory:") as db:
            # Connection should be established
            assert db._conn is not None, "Connection should be established in context manager"

            # Connection should be functional (can execute queries)
            async with db._conn.execute("SELECT 1 as test") as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Should be able to execute queries"
                assert row[0] == 1, "Query should return expected result"

    @pytest.mark.asyncio
    async def test_context_manager_closes_connection(self) -> None:
        """DB connection is closed after context manager exit.

        Verifies that the connection is properly cleaned up when exiting
        the context manager, ensuring no resource leaks.
        """
        db = OrchestratorDB(":memory:")

        async with db:
            # Connection is open inside context
            assert db._conn is not None, "Connection should be open inside context"

        # Connection should be closed after exit
        assert db._conn is None, "Connection should be closed after context exit"

    @pytest.mark.asyncio
    async def test_schema_initialized_on_first_connect(self) -> None:
        """Schema tables are created on first connection.

        Verifies that the database schema is automatically initialized
        when connecting to a new database, creating all required tables
        and views.
        """
        async with OrchestratorDB(":memory:") as db:
            # Schema should be initialized - verify by attempting a query
            # that would fail if schema doesn't exist
            result = await db.get_task_by_key("NONEXISTENT-KEY")

            # Should return None (not found) rather than throwing error
            assert result is None, "Should return None for non-existent task"

            # Verify core tables exist by checking sqlite_master
            assert db._conn is not None, "Connection should be established"
            async with db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ) as cursor:
                tables = [row[0] for row in await cursor.fetchall()]

            # Check for essential tables
            required_tables = {"tasks", "attempts", "workers", "config", "specs"}
            assert required_tables.issubset(set(tables)), (
                f"Missing required tables. Found: {tables}"
            )

    @pytest.mark.asyncio
    async def test_reconnection_after_close(self) -> None:
        """Can reconnect after closing.

        Verifies that a database instance can be reused by reconnecting
        after the connection has been closed, supporting connection pooling
        and retry patterns.
        """
        import tempfile

        # Use a temporary file database so data persists across reconnections
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            db = OrchestratorDB(tmp_path)

            # First connection
            await db.connect()
            assert db._conn is not None, "First connection should succeed"

            # Create a task to verify persistence
            task_id = await db.create_task(
                task_key="TEST-001",
                title="Test Task",
                phase=0,
                sequence=1,
            )
            assert task_id > 0, "Task creation should succeed"

            # Close connection
            await db.close()
            assert db._conn is None, "Connection should be closed"

            # Reconnect to same database file
            await db.connect()
            assert db._conn is not None, "Reconnection should succeed"

            # Verify data persisted across reconnection
            task = await db.get_task_by_key("TEST-001")
            assert task is not None, "Task should persist after reconnection"
            assert task["title"] == "Test Task", "Task data should be intact"

            # Cleanup
            await db.close()
        finally:
            # Delete temporary database file
            if tmp_path.exists():
                tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_manual_connect_and_close(self) -> None:
        """Direct connect() and close() calls work correctly.

        Verifies that the database can be managed without the context
        manager, supporting manual connection lifecycle management.
        """
        db = OrchestratorDB(":memory:")

        # Initially not connected
        assert db._conn is None, "Should not be connected initially"

        # Manual connect
        await db.connect()
        assert db._conn is not None, "Should be connected after connect()"

        # Verify functional
        result = await db.get_task_by_key("NONEXISTENT")
        assert result is None, "Should be able to query after manual connect"

        # Manual close
        await db.close()
        assert db._conn is None, "Should be disconnected after close()"

    @pytest.mark.asyncio
    async def test_ensure_connected_establishes_connection(self) -> None:
        """_ensure_connected() establishes connection if needed.

        Verifies that the internal _ensure_connected() method automatically
        establishes a connection when required, supporting lazy initialization.
        """
        db = OrchestratorDB(":memory:")

        # Initially not connected
        assert db._conn is None, "Should start disconnected"

        # Call a method that uses _ensure_connected
        stats = await db.get_stats()

        # Should have auto-connected and returned valid result
        assert isinstance(stats, dict), "Should return stats dictionary"
        assert "pending" in stats, "Stats should include status counts"

        # Connection should now be established
        assert db._conn is not None, "Should be connected after query"

        # Cleanup
        await db.close()

    @pytest.mark.asyncio
    async def test_connection_survives_multiple_operations(self) -> None:
        """Connection remains stable across multiple operations.

        Verifies that a single connection can be reused for multiple
        database operations without requiring reconnection.
        """
        async with OrchestratorDB(":memory:") as db:
            # Create a task
            task_id = await db.create_task(
                task_key="TEST-MULTI",
                title="Multi-op Test",
                phase=0,
                sequence=1,
            )
            assert task_id > 0

            # Read the task
            task = await db.get_task_by_key("TEST-MULTI")
            assert task is not None
            assert task["title"] == "Multi-op Test"

            # Update task status
            updated = await db.update_task_status("TEST-MULTI", "in_progress")
            assert updated is True

            # Verify update
            task = await db.get_task_by_key("TEST-MULTI")
            assert task is not None
            assert task["status"] == "in_progress"

            # Get stats
            stats = await db.get_stats()
            assert stats["in_progress"] == 1

            # Connection should still be valid throughout
            assert db._conn is not None

    @pytest.mark.asyncio
    async def test_database_path_handling(self) -> None:
        """Database handles different path types correctly.

        Verifies that the database can be instantiated with various
        path formats: string paths, Path objects, and the special
        ":memory:" in-memory database.
        """
        # Test with :memory: string
        db1 = OrchestratorDB(":memory:")
        async with db1:
            assert db1._conn is not None

        # Test with Path object (for a file database)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            db2 = OrchestratorDB(tmp_path)
            async with db2:
                assert db2._conn is not None
                # Verify schema initialized
                task_id = await db2.create_task(
                    task_key="PATH-TEST",
                    title="Path Test",
                )
                assert task_id > 0
        finally:
            # Cleanup temporary database file
            if tmp_path.exists():
                tmp_path.unlink()

        # Test with string path
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_str = tmp.name

        try:
            db3 = OrchestratorDB(tmp_str)
            async with db3:
                assert db3._conn is not None
        finally:
            # Cleanup
            Path(tmp_str).unlink(missing_ok=True)
