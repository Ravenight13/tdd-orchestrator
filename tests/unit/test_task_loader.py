"""Tests for task_loader module."""

from __future__ import annotations

import json

import pytest

from tdd_orchestrator.database import reset_db
from tdd_orchestrator.database.core import OrchestratorDB
from tdd_orchestrator.task_loader import update_task_depends_on


@pytest.fixture(autouse=True)
async def _reset_db() -> None:
    """Reset DB singleton after each test."""
    yield  # type: ignore[misc]
    await reset_db()


@pytest.fixture
async def db_with_task() -> OrchestratorDB:
    """Create an in-memory DB with one task."""
    db = OrchestratorDB(":memory:")
    await db.connect()
    await db.create_task(
        task_key="TEST-TDD-01-01",
        title="Test task",
        goal="Test goal",
    )
    return db


async def test_update_task_depends_on_existing(db_with_task: OrchestratorDB) -> None:
    """Updating depends_on on an existing task returns True and persists."""
    result = await update_task_depends_on(
        "TEST-TDD-01-01", ["TEST-TDD-01-00"], db=db_with_task
    )
    assert result is True

    # Verify persisted
    task = await db_with_task.get_task_by_key("TEST-TDD-01-01")
    assert task is not None
    deps = json.loads(task["depends_on"]) if task["depends_on"] else []
    assert deps == ["TEST-TDD-01-00"]


async def test_update_task_depends_on_nonexistent(db_with_task: OrchestratorDB) -> None:
    """Updating depends_on on a non-existent task returns False."""
    result = await update_task_depends_on(
        "NONEXISTENT-01-01", ["TEST-TDD-01-00"], db=db_with_task
    )
    assert result is False


async def test_update_task_depends_on_empty_list(db_with_task: OrchestratorDB) -> None:
    """Updating depends_on with an empty list stores []."""
    result = await update_task_depends_on(
        "TEST-TDD-01-01", [], db=db_with_task
    )
    assert result is True

    task = await db_with_task.get_task_by_key("TEST-TDD-01-01")
    assert task is not None
    deps = json.loads(task["depends_on"]) if task["depends_on"] else []
    assert deps == []
