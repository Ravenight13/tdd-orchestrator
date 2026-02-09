"""Dependency initialization and management for API singletons.

This module manages module-level singletons for OrchestratorDB and SSEBroadcaster
during application lifespan (startup/shutdown).
"""

from __future__ import annotations

from src.tdd_orchestrator.api.sse import SSEBroadcaster
from src.tdd_orchestrator.database.core import OrchestratorDB

# Module-level singletons
_db: OrchestratorDB | None = None
_broadcaster: SSEBroadcaster | None = None


def get_db_dep() -> OrchestratorDB:
    """Get the OrchestratorDB singleton.

    Returns:
        The initialized OrchestratorDB instance.

    Raises:
        RuntimeError: If dependencies are not initialized.
    """
    if _db is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _db


def get_broadcaster_dep() -> SSEBroadcaster:
    """Get the SSEBroadcaster singleton.

    Returns:
        The initialized SSEBroadcaster instance.

    Raises:
        RuntimeError: If dependencies are not initialized.
    """
    if _broadcaster is None:
        raise RuntimeError("Dependencies not initialized. Call init_dependencies() first.")
    return _broadcaster


async def init_dependencies(db_path: str) -> None:
    """Initialize module-level singletons for OrchestratorDB and SSEBroadcaster.

    This function is idempotent - calling it multiple times will reuse the existing
    singletons rather than creating new ones.

    Args:
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If db_path is empty or invalid.
        OSError: If database path is not accessible.
        RuntimeError: If database initialization fails.
    """
    global _db, _broadcaster

    # Idempotency: if already initialized, do nothing
    if _db is not None and _broadcaster is not None:
        return

    # Validate db_path
    if not db_path:
        raise ValueError("db_path cannot be empty")

    # Initialize OrchestratorDB singleton
    if _db is None:
        try:
            _db = OrchestratorDB(db_path=db_path)
            await _db.connect()
        except Exception as e:
            # Clean up on error
            _db = None
            # Convert sqlite3.OperationalError and similar to OSError
            if "unable to open database" in str(e).lower():
                raise OSError(f"Unable to open database at {db_path}") from e
            raise

    # Initialize SSEBroadcaster singleton
    if _broadcaster is None:
        _broadcaster = SSEBroadcaster()


async def shutdown_dependencies() -> None:
    """Shutdown and reset module-level singletons.

    This function is safe to call multiple times - it's a no-op if already shutdown
    or never initialized.
    """
    global _db, _broadcaster

    # Close database connection if it exists
    if _db is not None:
        await _db.close()
        _db = None

    # Shutdown broadcaster if it exists
    if _broadcaster is not None:
        await _broadcaster.shutdown()
        _broadcaster = None
