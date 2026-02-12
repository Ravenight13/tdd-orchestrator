"""FastAPI dependency injection functions for OrchestratorDB and SSEBroadcaster."""

from typing import Any, AsyncGenerator

# Module-level singletons
_db_instance: Any | None = None
_broadcaster_instance: Any | None = None


async def get_db_dep() -> AsyncGenerator[Any, None]:
    """Async generator dependency that yields the OrchestratorDB singleton.

    Yields None when uninitialized, allowing route handlers to fall back
    to placeholder functions (preserving unit test compatibility).

    Yields:
        The OrchestratorDB instance, or None if not yet initialized.
    """
    yield _db_instance


def get_broadcaster_dep() -> Any:
    """Dependency that returns the SSEBroadcaster singleton.

    Raises:
        RuntimeError: If the broadcaster singleton has not been initialized.

    Returns:
        The SSEBroadcaster instance.
    """
    if _broadcaster_instance is None:
        raise RuntimeError("Broadcaster dependency is uninitialized")
    return _broadcaster_instance


def init_dependencies(db: Any, broadcaster: Any) -> None:
    """Initialize the dependency singletons.

    Args:
        db: The OrchestratorDB instance.
        broadcaster: The SSEBroadcaster instance.
    """
    global _db_instance, _broadcaster_instance
    _db_instance = db
    _broadcaster_instance = broadcaster


def shutdown_dependencies() -> None:
    """Clear the dependency singletons.

    This function is idempotent and can be called multiple times safely.
    """
    global _db_instance, _broadcaster_instance
    _db_instance = None
    _broadcaster_instance = None
