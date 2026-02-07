"""Shared fixtures for decomposition tests."""

from __future__ import annotations

import pytest

from tdd_orchestrator.database import reset_db


@pytest.fixture(autouse=True)
async def _reset_db_singleton() -> None:
    """Reset the database singleton after each test to prevent connection leaks."""
    yield  # type: ignore[misc]
    await reset_db()
