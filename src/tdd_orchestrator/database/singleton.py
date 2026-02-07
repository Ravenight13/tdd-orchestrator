"""Singleton database instance management.

Provides module-level get_db(), reset_db(), and set_db_path() functions
for managing a shared OrchestratorDB instance.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .core import OrchestratorDB

logger = logging.getLogger(__name__)

# Singleton instance for MCP tools
_db_instance: OrchestratorDB | None = None

# Custom path for database (allows configuration before first get_db call)
_custom_db_path: str | Path | None = None


def set_db_path(path: str | Path) -> None:
    """Set custom database path before first get_db() call.

    This allows configuring where the database is created before
    the singleton is initialized. Useful for testing.

    Args:
        path: Path to SQLite database file.

    Raises:
        RuntimeError: If database is already initialized.
    """
    global _custom_db_path, _db_instance
    if _db_instance is not None:
        msg = "Cannot set db_path after database is initialized. Call reset_db() first."
        raise RuntimeError(msg)
    _custom_db_path = path
    logger.info("Database path set to: %s", path)


async def get_db() -> OrchestratorDB:
    """Get the singleton database instance.

    Returns:
        The singleton OrchestratorDB instance, connected and ready.
    """
    global _db_instance, _custom_db_path
    if _db_instance is None:
        _db_instance = OrchestratorDB(_custom_db_path)
        await _db_instance.connect()
    return _db_instance


async def reset_db() -> None:
    """Reset the singleton database instance.

    Useful for testing to ensure a fresh database.
    Also clears any custom db_path setting.
    """
    global _db_instance, _custom_db_path
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
    _custom_db_path = None
