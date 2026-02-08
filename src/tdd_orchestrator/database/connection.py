"""Database connection management and schema initialization.

Provides the base ConnectionMixin with connection lifecycle, schema setup,
and generic query helpers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# Path to schema file: database/connection.py -> database/ -> tdd_orchestrator/ -> src/ -> project root
SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / "schema" / "schema.sql"

# Configuration bounds for numeric values
CONFIG_BOUNDS: dict[str, tuple[int, int]] = {
    "max_green_attempts": (1, 10),
    "green_retry_delay_ms": (0, 10000),
    "max_green_retry_time_seconds": (60, 7200),  # 1 min to 2 hours
}

# Default database path
DEFAULT_DB_PATH = Path.cwd() / "orchestrator.db"


class ConnectionMixin:
    """Base mixin providing database connection management.

    Manages the aiosqlite connection lifecycle, schema initialization,
    and generic query/update helpers.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Use ":memory:" for testing.
                     Defaults to orchestrator.db in the current working directory.
        """
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        elif isinstance(db_path, str):
            self.db_path = Path(db_path) if db_path != ":memory:" else db_path  # type: ignore[assignment]
        else:
            self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._initialized = False
        self._write_lock = asyncio.Lock()

    async def __aenter__(self) -> ConnectionMixin:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Open database connection and initialize schema."""
        db_path = str(self.db_path) if isinstance(self.db_path, Path) else self.db_path
        # Resolve to absolute path if it's a file path
        if db_path != ":memory:":
            resolved_path = Path(db_path).resolve()
            db_exists = resolved_path.exists()
            logger.info("Database: %s (exists: %s)", resolved_path, db_exists)
        self._conn = await aiosqlite.connect(db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._initialize_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _ensure_connected(self) -> None:
        """Ensure database is connected."""
        if self._conn is None:
            await self.connect()

    async def _initialize_schema(self) -> None:
        """Initialize database schema from SQL file.

        Raises:
            RuntimeError: If schema initialization fails due to migration issues.
                          Delete the database file to start fresh.
        """
        if not self._conn:
            msg = "Database not connected"
            raise RuntimeError(msg)

        if self._initialized:
            return

        # Check if tasks table exists and has expected columns
        # If schema mismatch, provide clear error before executescript hangs
        try:
            async with self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Table exists - verify it has expected columns
                    async with self._conn.execute("PRAGMA table_info(tasks)") as pragma_cursor:
                        columns = {col[1] for col in await pragma_cursor.fetchall()}
                        required_columns = {
                            "claimed_by",
                            "claimed_at",
                            "claim_expires_at",
                            "version",
                        }
                        missing = required_columns - columns
                        if missing:
                            msg = (
                                f"Database schema is outdated (missing columns: {missing}).\n"
                                f"To fix: Delete {self.db_path} and run again."
                            )
                            raise RuntimeError(msg)
        except RuntimeError:
            raise
        except Exception as e:
            logger.debug("Schema check failed, continuing with initialization: %s", e)

        schema_sql = SCHEMA_PATH.read_text()
        async with self._write_lock:
            try:
                await self._conn.executescript(schema_sql)
                await self._conn.commit()
                self._initialized = True
                logger.info("Database schema initialized")
            except Exception as e:
                msg = (
                    f"Schema initialization failed: {e}\n"
                    f"This usually means the database schema is outdated.\n"
                    f"To fix: Delete {self.db_path} and run again."
                )
                raise RuntimeError(msg) from e

        # PLAN9: Check for module_exports column migration
        await self._migrate_module_exports()

    async def _migrate_module_exports(self) -> None:
        """Migrate database to add PLAN9 module_exports column if missing.

        This method handles schema migration for existing databases that
        don't have the module_exports column. It's idempotent and safe
        to run multiple times.
        """
        if not self._conn:
            return

        try:
            # Check if column exists by attempting a query
            await self._conn.execute("SELECT module_exports FROM tasks LIMIT 1")
            logger.debug("PLAN9: module_exports column already exists")
        except Exception:
            # Column doesn't exist, add it
            logger.info("PLAN9: Adding module_exports column to tasks table")
            async with self._write_lock:
                await self._conn.execute(
                    "ALTER TABLE tasks ADD COLUMN module_exports TEXT DEFAULT '[]'"
                )
                await self._conn.commit()
                logger.info("PLAN9: module_exports column added successfully")

    # =========================================================================
    # Generic Query/Update Helpers (for testing)
    # =========================================================================

    async def execute_query(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts.

        Args:
            query: SQL SELECT query.
            params: Optional query parameters.

        Returns:
            List of result rows as dictionaries.
        """
        await self._ensure_connected()
        if not self._conn:
            return []

        async with self._conn.execute(query, params or ()) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_update(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows.

        Args:
            query: SQL INSERT/UPDATE/DELETE query.
            params: Optional query parameters.

        Returns:
            Number of rows affected.
        """
        await self._ensure_connected()
        if not self._conn:
            return 0

        async with self._write_lock:
            cursor = await self._conn.execute(query, params or ())
            await self._conn.commit()
            return cursor.rowcount
