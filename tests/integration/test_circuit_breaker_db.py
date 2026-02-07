"""Integration tests for circuit breaker database operations.

Tests use real SQLite database (in-memory) to verify:
- Schema creation
- Circuit CRUD operations
- Event logging
- View queries
- State persistence
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

import pytest
import pytest_asyncio

# Use relative import to match project structure
from tdd_orchestrator.database import OrchestratorDB

if TYPE_CHECKING:
    pass


@pytest.fixture
def schema_path() -> Path:
    """Get path to schema.sql."""
    return Path(__file__).resolve().parent.parent.parent / "schema" / "schema.sql"


@pytest_asyncio.fixture
async def db(schema_path: Path) -> AsyncGenerator[OrchestratorDB, None]:
    """Create in-memory database with schema."""
    database = OrchestratorDB(":memory:")
    await database.connect()

    # Load schema
    schema_sql = schema_path.read_text()
    # Split by semicolon and execute each statement
    for statement in schema_sql.split(";"):
        statement = statement.strip()
        if statement and not statement.startswith("--"):
            try:
                await database._conn.executescript(statement + ";")  # type: ignore[union-attr]
            except Exception:
                pass  # Ignore errors from CREATE IF NOT EXISTS, etc.

    yield database
    await database.close()


@pytest_asyncio.fixture
async def db_simple() -> AsyncGenerator[OrchestratorDB, None]:
    """Create in-memory database with schema (uses built-in initialization)."""
    database = OrchestratorDB(":memory:")
    await database.connect()
    yield database
    await database.close()


class TestSchemaCreation:
    """Tests for database schema creation."""

    @pytest.mark.asyncio
    async def test_circuit_breakers_table_exists(self, db_simple: OrchestratorDB) -> None:
        """Circuit breakers table should exist."""
        result = await db_simple.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='circuit_breakers'"
        )
        assert len(result) == 1
        assert result[0]["name"] == "circuit_breakers"

    @pytest.mark.asyncio
    async def test_circuit_breaker_events_table_exists(self, db_simple: OrchestratorDB) -> None:
        """Circuit breaker events table should exist."""
        result = await db_simple.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='circuit_breaker_events'"
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_views_exist(self, db_simple: OrchestratorDB) -> None:
        """All circuit breaker views should exist."""
        expected_views = [
            "v_open_circuits",
            "v_flapping_circuits",
            "v_circuit_health_summary",
            "v_circuit_breaker_status",
            "v_notification_history",
            "v_time_to_recovery",
        ]

        result = await db_simple.execute_query("SELECT name FROM sqlite_master WHERE type='view'")
        view_names = [row["name"] for row in result]

        for view in expected_views:
            assert view in view_names, f"Missing view: {view}"


class TestCircuitBreakerCRUD:
    """Tests for circuit breaker CRUD operations."""

    @pytest.mark.asyncio
    async def test_insert_circuit(self, db_simple: OrchestratorDB) -> None:
        """Should insert a new circuit breaker."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        result = await db_simple.execute_query(
            "SELECT * FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        assert len(result) == 1
        assert result[0]["level"] == "worker"
        assert result[0]["state"] == "closed"
        assert result[0]["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_update_circuit_state(self, db_simple: OrchestratorDB) -> None:
        """Should update circuit breaker state."""
        # Insert
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        # Update
        await db_simple.execute_update(
            """
            UPDATE circuit_breakers
            SET state = 'open',
                failure_count = 3,
                opened_at = datetime('now'),
                version = version + 1
            WHERE identifier = 'worker_1'
            """
        )

        result = await db_simple.execute_query(
            "SELECT * FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        assert result[0]["state"] == "open"
        assert result[0]["failure_count"] == 3
        assert result[0]["version"] == 2

    @pytest.mark.asyncio
    async def test_unique_level_identifier_constraint(self, db_simple: OrchestratorDB) -> None:
        """Should enforce unique (level, identifier) constraint."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        with pytest.raises(Exception):  # Should raise integrity error
            await db_simple.execute_update(
                """
                INSERT INTO circuit_breakers (level, identifier, state)
                VALUES ('worker', 'worker_1', 'open')
                """
            )


class TestCircuitBreakerEvents:
    """Tests for circuit breaker event logging."""

    @pytest.mark.asyncio
    async def test_log_state_change_event(self, db_simple: OrchestratorDB) -> None:
        """Should log state change events."""
        # Insert circuit
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        # Get circuit ID
        result = await db_simple.execute_query(
            "SELECT id FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        circuit_id = result[0]["id"]

        # Log event
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breaker_events
            (circuit_id, event_type, from_state, to_state)
            VALUES (?, 'state_change', 'closed', 'open')
            """,
            (circuit_id,),
        )

        events = await db_simple.execute_query(
            "SELECT * FROM circuit_breaker_events WHERE circuit_id = ?",
            (circuit_id,),
        )
        assert len(events) == 1
        assert events[0]["event_type"] == "state_change"
        assert events[0]["from_state"] == "closed"
        assert events[0]["to_state"] == "open"

    @pytest.mark.asyncio
    async def test_event_types_constraint(self, db_simple: OrchestratorDB) -> None:
        """Should enforce valid event types."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        result = await db_simple.execute_query(
            "SELECT id FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        circuit_id = result[0]["id"]

        # Valid event types should work
        valid_types = [
            "state_change",
            "failure_recorded",
            "success_recorded",
            "manual_reset",
        ]
        for event_type in valid_types:
            await db_simple.execute_update(
                """
                INSERT INTO circuit_breaker_events (circuit_id, event_type)
                VALUES (?, ?)
                """,
                (circuit_id, event_type),
            )


class TestCircuitBreakerViews:
    """Tests for circuit breaker monitoring views."""

    @pytest.mark.asyncio
    async def test_v_open_circuits(self, db_simple: OrchestratorDB) -> None:
        """Should return open circuits."""
        # Insert open circuit
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state, failure_count, opened_at)
            VALUES ('worker', 'worker_1', 'open', 5, datetime('now', '-10 minutes'))
            """
        )
        # Insert closed circuit
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_2', 'closed')
            """
        )

        result = await db_simple.execute_query("SELECT * FROM v_open_circuits")
        assert len(result) == 1
        assert result[0]["identifier"] == "worker_1"
        assert result[0]["state"] == "open"
        assert result[0]["minutes_open"] >= 10

    @pytest.mark.asyncio
    async def test_v_circuit_health_summary(self, db_simple: OrchestratorDB) -> None:
        """Should return health summary by level."""
        # Insert circuits at different levels and states
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state) VALUES
            ('stage', 's1', 'closed'),
            ('stage', 's2', 'closed'),
            ('worker', 'w1', 'open'),
            ('worker', 'w2', 'closed'),
            ('system', 'system', 'closed')
            """
        )

        result = await db_simple.execute_query(
            "SELECT * FROM v_circuit_health_summary ORDER BY level"
        )

        # Find worker level
        worker_summary = next(r for r in result if r["level"] == "worker")
        assert worker_summary["total_circuits"] == 2
        assert worker_summary["closed_count"] == 1
        assert worker_summary["open_count"] == 1

    @pytest.mark.asyncio
    async def test_v_circuit_breaker_status(self, db_simple: OrchestratorDB) -> None:
        """Should return complete status of all circuits."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state, failure_count, success_count)
            VALUES ('worker', 'worker_1', 'closed', 2, 10)
            """
        )

        result = await db_simple.execute_query("SELECT * FROM v_circuit_breaker_status")
        assert len(result) == 1
        assert result[0]["failure_count"] == 2
        assert result[0]["success_count"] == 10

    @pytest.mark.asyncio
    async def test_v_flapping_circuits(self, db_simple: OrchestratorDB) -> None:
        """Should detect flapping circuits (5+ state changes in 5 min)."""
        # Insert circuit
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        result = await db_simple.execute_query(
            "SELECT id FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        circuit_id = result[0]["id"]

        # Insert 6 state change events within last 5 minutes
        for i in range(6):
            await db_simple.execute_update(
                """
                INSERT INTO circuit_breaker_events
                (circuit_id, event_type, from_state, to_state, created_at)
                VALUES (?, 'state_change', 'closed', 'open', datetime('now', '-1 minutes'))
                """,
                (circuit_id,),
            )

        result = await db_simple.execute_query("SELECT * FROM v_flapping_circuits")
        assert len(result) == 1
        assert result[0]["identifier"] == "worker_1"
        assert result[0]["state_changes_5min"] == 6


class TestStatePersistence:
    """Tests for state persistence across operations."""

    @pytest.mark.asyncio
    async def test_version_increment(self, db_simple: OrchestratorDB) -> None:
        """Version should increment on updates."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        # Check initial version
        result = await db_simple.execute_query(
            "SELECT version FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        assert result[0]["version"] == 1

        # Update multiple times
        for i in range(3):
            await db_simple.execute_update(
                """
                UPDATE circuit_breakers
                SET failure_count = failure_count + 1,
                    version = version + 1
                WHERE identifier = 'worker_1'
                """
            )

        result = await db_simple.execute_query(
            "SELECT version, failure_count FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        assert result[0]["version"] == 4
        assert result[0]["failure_count"] == 3

    @pytest.mark.asyncio
    async def test_timestamps_updated(self, db_simple: OrchestratorDB) -> None:
        """Timestamps should be set on creation."""
        await db_simple.execute_update(
            """
            INSERT INTO circuit_breakers (level, identifier, state)
            VALUES ('worker', 'worker_1', 'closed')
            """
        )

        result = await db_simple.execute_query(
            "SELECT created_at, updated_at FROM circuit_breakers WHERE identifier = 'worker_1'"
        )
        assert result[0]["created_at"] is not None
        assert result[0]["updated_at"] is not None
