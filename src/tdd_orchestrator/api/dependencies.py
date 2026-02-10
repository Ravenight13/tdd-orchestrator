"""FastAPI dependency injection functions for OrchestratorDB and SSEBroadcaster."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tdd_orchestrator.api.sse import SSEBroadcaster
    from tdd_orchestrator.database.core import OrchestratorDB

# Module-level singletons
_db_instance: OrchestratorDB | None = None
_broadcaster_instance: SSEBroadcaster | None = None


async def get_db_dep() -> AsyncGenerator[Any, None]:
    """Yield the OrchestratorDB singleton as an async generator.

    This is compatible with FastAPI's Depends() for async generator dependencies.

    Raises:
        RuntimeError: If the database singleton has not been initialized.

    Yields:
        The OrchestratorDB instance.
    """
    if _db_instance is None:
        raise RuntimeError("Database dependency is not initialized")
    yield _db_instance


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


def init_dependencies(db: Any, broadcaster: Any) -> None:
    """Initialize the dependency singletons.

    Args:
        db: The OrchestratorDB instance to use as the singleton.
        broadcaster: The SSEBroadcaster instance to use as the singleton.
    """
    global _db_instance, _broadcaster_instance
    _db_instance = db
    _broadcaster_instance = broadcaster


def shutdown_dependencies() -> None:
    """Shutdown and clear the dependency singletons.

    This function is idempotent and can be called multiple times safely.
    """
    global _db_instance, _broadcaster_instance
    _db_instance = None
    _broadcaster_instance = None
