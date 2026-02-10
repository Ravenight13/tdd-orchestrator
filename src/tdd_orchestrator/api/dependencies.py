"""FastAPI dependency injection functions for OrchestratorDB and SSEBroadcaster."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tdd_orchestrator.database.core import OrchestratorDB
    from tdd_orchestrator.api.sse import SSEBroadcaster

# Module-level singletons
_db_instance: OrchestratorDB | None = None
_broadcaster_instance: SSEBroadcaster | None = None


def get_db_dep() -> Any:
    """Return the OrchestratorDB singleton.

    Raises:
        RuntimeError: If the database singleton has not been initialized.

    Returns:
        The OrchestratorDB instance.
    """
    if _db_instance is None:
        raise RuntimeError("Database dependency is not initialized")
    return _db_instance


def get_broadcaster_dep() -> Any:
    """Return the SSEBroadcaster singleton.

    Raises:
        RuntimeError: If the broadcaster singleton has not been initialized.

    Returns:
        The SSEBroadcaster instance.
    """
    if _broadcaster_instance is None:
        raise RuntimeError("Broadcaster dependency is not initialized")
    return _broadcaster_instance


async def init_dependencies(db_path: str) -> None:
    """Initialize the dependency singletons.

    This function is idempotent - calling it multiple times will not create
    new instances if singletons are already initialized.

    Args:
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If db_path is empty or invalid.
    """
    global _db_instance, _broadcaster_instance

    # Validate db_path
    if not db_path or not db_path.strip():
        raise ValueError("db_path cannot be empty")

    # Idempotent: only initialize if not already initialized
    if _db_instance is None:
        from tdd_orchestrator.database.core import OrchestratorDB
        try:
            _db_instance = OrchestratorDB(db_path)
            await _db_instance.connect()
        except Exception as e:
            # Re-raise any connection errors as OSError for consistent error handling
            if "unable to open database file" in str(e):
                raise OSError(f"Unable to open database file: {db_path}") from e
            raise

    if _broadcaster_instance is None:
        from tdd_orchestrator.api.sse import SSEBroadcaster
        _broadcaster_instance = SSEBroadcaster()


async def shutdown_dependencies() -> None:
    """Shutdown and clear the dependency singletons.

    This function is idempotent and can be called multiple times safely.
    It will close the database connection if one exists.
    """
    global _db_instance, _broadcaster_instance

    # Close DB connection if it exists
    if _db_instance is not None:
        await _db_instance.close()

    # Reset singletons to None
    _db_instance = None
    _broadcaster_instance = None
