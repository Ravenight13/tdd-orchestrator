"""Shared fixtures for database unit tests.

Sets up an in-memory database via the singleton for testing mixins.
"""

from __future__ import annotations

import pytest

from src.tdd_orchestrator.database.singleton import get_db, reset_db, set_db_path


@pytest.fixture(autouse=True)
async def reset_database_singleton() -> None:
    """Reset database singleton before each test to ensure isolation.

    Uses an in-memory database for fast, isolated tests.
    """
    # Reset any existing singleton
    await reset_db()

    # Configure to use in-memory database
    set_db_path(":memory:")

    # Initialize the database (connects and creates schema)
    await get_db()

    yield

    # Clean up after test
    await reset_db()
