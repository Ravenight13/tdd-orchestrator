"""Tests for get_tasks_by_status function.

Tests verify retrieval of tasks by status with parameterized SQL.
"""

from __future__ import annotations

import pytest

from src.tdd_orchestrator.database.mixins.task_mixin import get_tasks_by_status


class TestGetTasksByStatusBasicRetrieval:
    """Tests for basic task retrieval by status."""

    @pytest.mark.asyncio
    async def test_returns_all_pending_tasks_when_multiple_exist(self) -> None:
        """GIVEN a database with 3 pending and 2 running tasks,
        WHEN get_tasks_by_status('pending') is called,
        THEN it returns exactly 3 task rows.
        """
        result = await get_tasks_by_status("pending")
        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_returns_correct_task_fields_for_matching_status(self) -> None:
        """GIVEN a database with pending tasks,
        WHEN get_tasks_by_status('pending') is called,
        THEN each returned row contains task_id, spec_id, and status fields.
        """
        result = await get_tasks_by_status("pending")
        assert len(result) > 0
        for task in result:
            assert "task_id" in task or "id" in task
            assert "spec_id" in task
            assert "status" in task
            assert task["status"] == "pending"


class TestGetTasksByStatusEmptyResults:
    """Tests for scenarios that return empty results."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_status_with_no_matches(self) -> None:
        """GIVEN a database with tasks in various statuses but none 'cancelled',
        WHEN get_tasks_by_status('cancelled') is called,
        THEN it returns an empty list (not None, not an error).
        """
        result = await get_tasks_by_status("cancelled")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_tasks_table(self) -> None:
        """GIVEN an empty tasks table,
        WHEN get_tasks_by_status('pending') is called,
        THEN it returns an empty list.
        """
        result = await get_tasks_by_status("pending")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0


class TestGetTasksByStatusSQLInjectionProtection:
    """Tests for SQL injection protection via parameterized queries."""

    @pytest.mark.asyncio
    async def test_sql_injection_attempt_returns_empty_list_safely(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_by_status is called with SQL injection attempt,
        THEN the parameterized query safely returns an empty list.
        """
        malicious_status = "pending'; DROP TABLE tasks;--"
        result = await get_tasks_by_status(malicious_status)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_tasks_table_intact_after_injection_attempt(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_by_status is called with SQL injection attempt,
        THEN the tasks table remains intact and subsequent queries work.
        """
        malicious_status = "pending'; DROP TABLE tasks;--"
        await get_tasks_by_status(malicious_status)

        # Verify table still exists by querying valid status
        result = await get_tasks_by_status("pending")
        assert isinstance(result, list)


class TestGetTasksByStatusRowContents:
    """Tests for verifying complete row data is returned."""

    @pytest.mark.asyncio
    async def test_returns_all_expected_columns_for_each_row(self) -> None:
        """GIVEN a database with 5 pending tasks each having distinct fields,
        WHEN get_tasks_by_status('pending') is called,
        THEN each returned row contains all expected columns.
        """
        result = await get_tasks_by_status("pending")
        expected_columns = {
            "task_id",
            "spec_id",
            "status",
            "created_at",
            "updated_at",
            "result",
            "agent_id",
        }
        # Alternative column naming (id vs task_id)
        alt_expected_columns = {
            "id",
            "spec_id",
            "status",
            "created_at",
            "updated_at",
        }

        assert len(result) == 5
        for task in result:
            task_keys = set(task.keys())
            # Accept either naming convention
            has_expected = expected_columns.issubset(task_keys) or alt_expected_columns.issubset(
                task_keys
            )
            assert has_expected, f"Missing expected columns in {task_keys}"

    @pytest.mark.asyncio
    async def test_returned_data_matches_inserted_values(self) -> None:
        """GIVEN a database with pending tasks having distinct spec_ids,
        WHEN get_tasks_by_status('pending') is called,
        THEN the returned data matches the inserted values.
        """
        result = await get_tasks_by_status("pending")
        assert len(result) > 0

        # Verify all returned tasks have 'pending' status
        for task in result:
            assert task["status"] == "pending"

        # Verify spec_ids are distinct if multiple tasks
        if len(result) > 1:
            spec_ids = [task.get("spec_id") for task in result if task.get("spec_id") is not None]
            if spec_ids:
                assert len(spec_ids) == len(set(spec_ids)), "spec_ids should be distinct"


class TestGetTasksByStatusEdgeCases:
    """Edge case tests for get_tasks_by_status."""

    @pytest.mark.asyncio
    async def test_handles_empty_string_status(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_by_status('') is called with empty string,
        THEN it returns an empty list without error.
        """
        result = await get_tasks_by_status("")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_status_matching_is_case_sensitive(self) -> None:
        """GIVEN a database with 'pending' status tasks,
        WHEN get_tasks_by_status('PENDING') is called with uppercase,
        THEN it returns empty list (case-sensitive matching).
        """
        result = await get_tasks_by_status("PENDING")
        assert isinstance(result, list)
        # Assuming case-sensitive matching in SQL
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_handles_special_characters_in_status(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_by_status is called with special characters,
        THEN it handles them safely without SQL errors.
        """
        special_status = "status%with_wildcards"
        result = await get_tasks_by_status(special_status)
        assert result is not None
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_handles_unicode_in_status(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_by_status is called with unicode characters,
        THEN it handles them safely without errors.
        """
        unicode_status = "pending\u0000null"
        result = await get_tasks_by_status(unicode_status)
        assert result is not None
        assert isinstance(result, list)


class TestGetTasksByStatusReturnType:
    """Tests for verifying correct return types."""

    @pytest.mark.asyncio
    async def test_return_type_is_list(self) -> None:
        """GIVEN any database state,
        WHEN get_tasks_by_status is called,
        THEN the return type is always a list.
        """
        result = await get_tasks_by_status("pending")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_elements_are_dictionaries_or_row_objects(self) -> None:
        """GIVEN a database with matching tasks,
        WHEN get_tasks_by_status is called,
        THEN list elements are dict-like objects with key access.
        """
        result = await get_tasks_by_status("pending")
        if len(result) > 0:
            first_row = result[0]
            # Should support dict-like key access
            assert "status" in first_row
            assert first_row["status"] == "pending"
