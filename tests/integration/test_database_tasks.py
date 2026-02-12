"""Task CRUD operation tests."""

from __future__ import annotations

import json

import pytest
from tdd_orchestrator.database import OrchestratorDB


class TestTaskCreation:
    """Task creation and retrieval tests."""

    @pytest.mark.asyncio
    async def test_create_task_returns_id(self) -> None:
        """Creating a task returns its database ID."""
        async with OrchestratorDB(":memory:") as db:
            task_id = await db.create_task(
                task_key="TDD-01",
                title="Test Task",
                phase=0,
                sequence=0,
            )
            assert task_id > 0

    @pytest.mark.asyncio
    async def test_create_task_with_dependencies(self) -> None:
        """Dependencies are stored as JSON array."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq", phase=0, sequence=0)
            await db.create_task(
                "TDD-01",
                "Dependent",
                depends_on=["TDD-00"],
                phase=0,
                sequence=1,
            )
            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert json.loads(task["depends_on"]) == ["TDD-00"]

    @pytest.mark.asyncio
    async def test_duplicate_task_key_raises_error(self) -> None:
        """Duplicate task_key violates unique constraint."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "First", phase=0, sequence=0)
            with pytest.raises(Exception):  # sqlite3.IntegrityError
                await db.create_task("TDD-01", "Second", phase=0, sequence=1)

    @pytest.mark.asyncio
    async def test_get_task_returns_none_for_missing(self) -> None:
        """Getting non-existent task returns None."""
        async with OrchestratorDB(":memory:") as db:
            task = await db.get_task_by_key("TDD-NONEXISTENT")
            assert task is None

    @pytest.mark.asyncio
    async def test_get_all_tasks_returns_ordered(self) -> None:
        """Get all tasks returns them ordered by phase then sequence."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-02", "Second", phase=0, sequence=2)
            await db.create_task("TDD-01", "First", phase=0, sequence=1)
            await db.create_task("TDD-10", "Phase 1", phase=1, sequence=0)

            tasks = await db.get_all_tasks()
            task_keys = [t["task_key"] for t in tasks]
            assert task_keys == ["TDD-01", "TDD-02", "TDD-10"]


class TestTaskStatus:
    """Task status transition tests."""

    @pytest.mark.asyncio
    async def test_update_status_to_valid_state(self) -> None:
        """Valid status transitions succeed."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            result = await db.update_task_status("TDD-01", "in_progress")
            assert result is True

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_nonexistent_task_returns_false(self) -> None:
        """Updating missing task returns False, no error."""
        async with OrchestratorDB(":memory:") as db:
            result = await db.update_task_status("TDD-999", "complete")
            assert result is False

    @pytest.mark.asyncio
    async def test_all_valid_statuses_accepted(self) -> None:
        """All valid status values can be set."""
        valid_statuses = ["pending", "in_progress", "passing", "complete", "blocked"]
        async with OrchestratorDB(":memory:") as db:
            for i, status in enumerate(valid_statuses):
                task_key = f"TDD-{i:02d}"
                await db.create_task(task_key, f"Task {i}", phase=0, sequence=i)
                result = await db.update_task_status(task_key, status)
                assert result is True
                task = await db.get_task_by_key(task_key)
                assert task is not None
                assert task["status"] == status


class TestTaskEdgeCases:
    """Edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_invalid_status_raises_error(self) -> None:
        """Invalid status values are rejected."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            with pytest.raises(ValueError, match="Invalid status"):
                await db.update_task_status("TDD-01", "invalid_status")

    @pytest.mark.asyncio
    async def test_create_task_with_all_fields(self) -> None:
        """Task can be created with all optional fields populated."""
        async with OrchestratorDB(":memory:") as db:
            task_id = await db.create_task(
                task_key="TDD-FULL",
                title="Full Task",
                goal="Test all fields",
                spec_id=1,
                acceptance_criteria=["AC1", "AC2"],
                test_file="backend/tests/test_full.py",
                impl_file="backend/src/full.py",
                depends_on=["TDD-00"],
                phase=2,
                sequence=5,
            )
            assert task_id > 0

            task = await db.get_task_by_key("TDD-FULL")
            assert task is not None
            assert task["title"] == "Full Task"
            assert task["goal"] == "Test all fields"
            assert task["spec_id"] == 1
            assert json.loads(task["acceptance_criteria"]) == ["AC1", "AC2"]
            assert task["test_file"] == "backend/tests/test_full.py"
            assert task["impl_file"] == "backend/src/full.py"
            assert json.loads(task["depends_on"]) == ["TDD-00"]
            assert task["phase"] == 2
            assert task["sequence"] == 5

    @pytest.mark.asyncio
    async def test_create_task_minimal_fields(self) -> None:
        """Task can be created with only required fields."""
        async with OrchestratorDB(":memory:") as db:
            task_id = await db.create_task(
                task_key="TDD-MIN",
                title="Minimal Task",
            )
            assert task_id > 0

            task = await db.get_task_by_key("TDD-MIN")
            assert task is not None
            assert task["title"] == "Minimal Task"
            assert task["goal"] is None
            assert task["status"] == "pending"
            assert task["phase"] == 0
            assert task["sequence"] == 0

    @pytest.mark.asyncio
    async def test_empty_dependencies_stored_as_empty_array(self) -> None:
        """Task with no dependencies has empty JSON array."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "No Deps", phase=0, sequence=0)

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert json.loads(task["depends_on"]) == []

    @pytest.mark.asyncio
    async def test_multiple_dependencies_preserved(self) -> None:
        """Task with multiple dependencies stores all of them."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-00", "Prereq 1", phase=0, sequence=0)
            await db.create_task("TDD-01", "Prereq 2", phase=0, sequence=1)
            await db.create_task(
                "TDD-02",
                "Multi-Dep",
                depends_on=["TDD-00", "TDD-01"],
                phase=0,
                sequence=2,
            )

            task = await db.get_task_by_key("TDD-02")
            assert task is not None
            deps = json.loads(task["depends_on"])
            assert len(deps) == 2
            assert "TDD-00" in deps
            assert "TDD-01" in deps


class TestTaskConvenienceMethods:
    """Test convenience methods for common status transitions."""

    @pytest.mark.asyncio
    async def test_mark_task_passing(self) -> None:
        """mark_task_passing transitions to passing status."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            result = await db.mark_task_passing("TDD-01")
            assert result is True

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["status"] == "passing"

    @pytest.mark.asyncio
    async def test_mark_task_complete(self) -> None:
        """mark_task_complete transitions to complete status."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            result = await db.mark_task_complete("TDD-01")
            assert result is True

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["status"] == "complete"

    @pytest.mark.asyncio
    async def test_mark_task_blocked(self) -> None:
        """mark_task_blocked transitions to blocked status."""
        async with OrchestratorDB(":memory:") as db:
            await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            result = await db.mark_task_blocked("TDD-01")
            assert result is True

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_mark_task_failing_records_attempt(self) -> None:
        """mark_task_failing records attempt and transitions to blocked."""
        async with OrchestratorDB(":memory:") as db:
            task_id = await db.create_task("TDD-01", "Test", phase=0, sequence=0)
            result = await db.mark_task_failing("TDD-01", "Test failure reason")
            assert result is True

            task = await db.get_task_by_key("TDD-01")
            assert task is not None
            assert task["status"] == "blocked"

            # Verify attempt was recorded
            attempts = await db.get_stage_attempts(task_id)
            assert len(attempts) == 1
            assert attempts[0]["success"] == 0
            assert attempts[0]["error_message"] == "Test failure reason"
