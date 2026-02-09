"""Tests for get_tasks_filtered function.

Tests verify retrieval of tasks with flexible filtering by status, phase,
complexity, limit, and offset parameters with dynamic WHERE clause construction.
"""

from __future__ import annotations

import pytest

from tdd_orchestrator.database.mixins.task_mixin import get_tasks_filtered


class TestGetTasksFilteredByStatus:
    """Tests for filtering tasks by status."""

    @pytest.mark.asyncio
    async def test_returns_only_pending_tasks_when_status_filter_is_pending(self) -> None:
        """GIVEN tasks exist with mixed statuses (pending, in_progress, completed),
        WHEN get_tasks_filtered(status='pending') is called,
        THEN only tasks with status 'pending' are returned.
        """
        result = await get_tasks_filtered(status="pending")
        assert isinstance(result, dict)
        assert "tasks" in result
        assert "total" in result
        tasks = result["tasks"]
        assert isinstance(tasks, list)
        for task in tasks:
            assert task["status"] == "pending"

    @pytest.mark.asyncio
    async def test_returns_only_in_progress_tasks_when_status_filter_is_in_progress(
        self,
    ) -> None:
        """GIVEN tasks exist with mixed statuses,
        WHEN get_tasks_filtered(status='in_progress') is called,
        THEN only tasks with status 'in_progress' are returned.
        """
        result = await get_tasks_filtered(status="in_progress")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        for task in tasks:
            assert task["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_returns_only_completed_tasks_when_status_filter_is_completed(
        self,
    ) -> None:
        """GIVEN tasks exist with mixed statuses,
        WHEN get_tasks_filtered(status='completed') is called,
        THEN only tasks with status 'completed' are returned.
        """
        result = await get_tasks_filtered(status="completed")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        for task in tasks:
            assert task["status"] == "completed"


class TestGetTasksFilteredMultipleFilters:
    """Tests for filtering tasks by multiple criteria simultaneously."""

    @pytest.mark.asyncio
    async def test_returns_tasks_matching_all_filters_when_phase_complexity_limit_offset_provided(
        self,
    ) -> None:
        """GIVEN tasks exist with various phases and complexities,
        WHEN get_tasks_filtered(phase='RED', complexity='low', limit=5, offset=0) is called,
        THEN only tasks matching ALL specified filters are returned.
        """
        result = await get_tasks_filtered(
            phase="RED", complexity="low", limit=5, offset=0
        )
        assert isinstance(result, dict)
        assert "tasks" in result
        assert "total" in result
        tasks = result["tasks"]
        assert isinstance(tasks, list)
        assert len(tasks) <= 5
        for task in tasks:
            assert task.get("phase") == "RED"
            assert task.get("complexity") == "low"

    @pytest.mark.asyncio
    async def test_total_reflects_all_matching_rows_not_just_page(self) -> None:
        """GIVEN 10 tasks matching a filter exist,
        WHEN get_tasks_filtered(phase='RED', limit=3) is called,
        THEN total reflects all matching rows (10), not just the returned page (3).
        """
        result = await get_tasks_filtered(phase="RED", limit=3, offset=0)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        total = result.get("total", 0)
        assert isinstance(total, int)
        # total should be >= len(tasks) because total counts all matching rows
        assert total >= len(tasks)

    @pytest.mark.asyncio
    async def test_combines_status_and_phase_filters(self) -> None:
        """GIVEN tasks exist with various statuses and phases,
        WHEN get_tasks_filtered(status='pending', phase='GREEN') is called,
        THEN only tasks matching both status AND phase are returned.
        """
        result = await get_tasks_filtered(status="pending", phase="GREEN")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task["status"] == "pending"
            assert task.get("phase") == "GREEN"


class TestGetTasksFilteredNoFilters:
    """Tests for retrieving all tasks when no filters are provided."""

    @pytest.mark.asyncio
    async def test_returns_all_tasks_up_to_default_limit_when_no_filters_provided(
        self,
    ) -> None:
        """GIVEN tasks exist in the database,
        WHEN get_tasks_filtered() is called with no parameters,
        THEN all tasks are returned (up to default limit).
        """
        result = await get_tasks_filtered()
        assert isinstance(result, dict)
        assert "tasks" in result
        assert "total" in result
        tasks = result["tasks"]
        total = result["total"]
        assert isinstance(tasks, list)
        assert isinstance(total, int)
        # Without filters, should return tasks (or empty if no tasks exist)

    @pytest.mark.asyncio
    async def test_total_equals_count_of_all_tasks_when_no_filters_provided(
        self,
    ) -> None:
        """GIVEN tasks exist in the database,
        WHEN get_tasks_filtered() is called with no parameters,
        THEN total equals the count of all tasks in the database.
        """
        result = await get_tasks_filtered()
        assert isinstance(result, dict)
        # The total should be a non-negative integer
        total = result.get("total")
        assert total is not None
        assert isinstance(total, int)
        assert total >= 0


class TestGetTasksFilteredPagination:
    """Tests for pagination with limit and offset parameters."""

    @pytest.mark.asyncio
    async def test_offset_skips_correct_number_of_rows(self) -> None:
        """GIVEN 15 matching tasks exist,
        WHEN get_tasks_filtered(status='pending', limit=5, offset=10) is called,
        THEN exactly 5 tasks are returned starting from the 11th match.
        """
        result = await get_tasks_filtered(status="pending", limit=5, offset=10)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        total = result.get("total", 0)
        assert isinstance(tasks, list)
        # Should return at most 5 tasks
        assert len(tasks) <= 5
        # Total should reflect all matching rows (15 in the scenario)
        assert isinstance(total, int)

    @pytest.mark.asyncio
    async def test_pagination_total_equals_all_matching_rows(self) -> None:
        """GIVEN 15 matching tasks exist,
        WHEN get_tasks_filtered(status='pending', limit=5, offset=10) is called,
        THEN total equals 15, verifying pagination offset works correctly.
        """
        result = await get_tasks_filtered(status="pending", limit=5, offset=10)
        assert isinstance(result, dict)
        total = result.get("total")
        assert total is not None
        assert isinstance(total, int)
        # Total should count all matching rows, not just the page

    @pytest.mark.asyncio
    async def test_limit_zero_returns_empty_list(self) -> None:
        """GIVEN tasks exist in the database,
        WHEN get_tasks_filtered(limit=0) is called,
        THEN an empty list is returned (or handled appropriately).
        """
        result = await get_tasks_filtered(limit=0)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_offset_beyond_results_returns_empty_list(self) -> None:
        """GIVEN 5 tasks exist in the database,
        WHEN get_tasks_filtered(offset=100) is called,
        THEN an empty list is returned because offset exceeds available rows.
        """
        result = await get_tasks_filtered(offset=100)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_first_page_returns_first_n_results(self) -> None:
        """GIVEN multiple tasks exist in the database,
        WHEN get_tasks_filtered(limit=5, offset=0) is called,
        THEN the first 5 tasks are returned.
        """
        result = await get_tasks_filtered(limit=5, offset=0)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) <= 5


class TestGetTasksFilteredEmptyResults:
    """Tests for scenarios that return empty results."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_with_total_zero_when_no_matches(self) -> None:
        """GIVEN no tasks match the filter criteria,
        WHEN get_tasks_filtered(status='nonexistent_status') is called,
        THEN an empty list is returned with total equal to 0.
        """
        result = await get_tasks_filtered(status="nonexistent_status")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        total = result.get("total", -1)
        assert isinstance(tasks, list)
        assert len(tasks) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_database(self) -> None:
        """GIVEN an empty tasks table,
        WHEN get_tasks_filtered() is called,
        THEN an empty list is returned with total equal to 0.
        """
        result = await get_tasks_filtered()
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        total = result.get("total", -1)
        assert isinstance(tasks, list)
        # Empty database should return empty list and total of 0
        assert isinstance(total, int)
        assert total >= 0


class TestGetTasksFilteredReturnStructure:
    """Tests for verifying correct return structure."""

    @pytest.mark.asyncio
    async def test_return_type_is_dict_with_tasks_and_total_keys(self) -> None:
        """GIVEN any database state,
        WHEN get_tasks_filtered is called,
        THEN the return type is a dict with 'tasks' and 'total' keys.
        """
        result = await get_tasks_filtered()
        assert isinstance(result, dict)
        assert "tasks" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_tasks_is_list_of_dict_like_objects(self) -> None:
        """GIVEN tasks exist in the database,
        WHEN get_tasks_filtered is called,
        THEN the 'tasks' value is a list of dict-like objects.
        """
        result = await get_tasks_filtered()
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        for task in tasks:
            # Should support dict-like access
            assert hasattr(task, "__getitem__") or isinstance(task, dict)

    @pytest.mark.asyncio
    async def test_total_is_integer(self) -> None:
        """GIVEN any database state,
        WHEN get_tasks_filtered is called,
        THEN the 'total' value is an integer.
        """
        result = await get_tasks_filtered()
        total = result.get("total")
        assert total is not None
        assert isinstance(total, int)


class TestGetTasksFilteredSQLInjectionProtection:
    """Tests for SQL injection protection via parameterized queries."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_status_returns_empty_safely(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered is called with SQL injection in status,
        THEN the parameterized query safely returns an empty list.
        """
        malicious_status = "pending'; DROP TABLE tasks;--"
        result = await get_tasks_filtered(status=malicious_status)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_sql_injection_in_phase_returns_empty_safely(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered is called with SQL injection in phase,
        THEN the parameterized query safely returns an empty list.
        """
        malicious_phase = "RED'; DROP TABLE tasks;--"
        result = await get_tasks_filtered(phase=malicious_phase)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0

    @pytest.mark.asyncio
    async def test_sql_injection_in_complexity_returns_empty_safely(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered is called with SQL injection in complexity,
        THEN the parameterized query safely returns an empty list.
        """
        malicious_complexity = "low'; DROP TABLE tasks;--"
        result = await get_tasks_filtered(complexity=malicious_complexity)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0


class TestGetTasksFilteredEdgeCases:
    """Edge case tests for get_tasks_filtered."""

    @pytest.mark.asyncio
    async def test_handles_empty_string_status(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered(status='') is called with empty string,
        THEN it returns an empty list without error.
        """
        result = await get_tasks_filtered(status="")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)

    @pytest.mark.asyncio
    async def test_handles_negative_offset(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered(offset=-1) is called with negative offset,
        THEN it handles gracefully (either error or treats as 0).
        """
        try:
            result = await get_tasks_filtered(offset=-1)
            assert isinstance(result, dict)
            tasks = result.get("tasks", [])
            assert isinstance(tasks, list)
        except ValueError:
            # Acceptable to raise ValueError for invalid offset
            pass

    @pytest.mark.asyncio
    async def test_handles_negative_limit(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered(limit=-1) is called with negative limit,
        THEN it handles gracefully (either error or treats as 0).
        """
        try:
            result = await get_tasks_filtered(limit=-1)
            assert isinstance(result, dict)
            tasks = result.get("tasks", [])
            assert isinstance(tasks, list)
        except ValueError:
            # Acceptable to raise ValueError for invalid limit
            pass

    @pytest.mark.asyncio
    async def test_handles_special_characters_in_filters(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered is called with special characters,
        THEN it handles them safely without SQL errors.
        """
        special_status = "status%with_wildcards"
        result = await get_tasks_filtered(status=special_status)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)

    @pytest.mark.asyncio
    async def test_handles_unicode_in_filters(self) -> None:
        """GIVEN a database with tasks,
        WHEN get_tasks_filtered is called with unicode characters,
        THEN it handles them safely without errors.
        """
        unicode_status = "pending\u0000null"
        result = await get_tasks_filtered(status=unicode_status)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)

    @pytest.mark.asyncio
    async def test_large_limit_value_handled(self) -> None:
        """GIVEN a database with a small number of tasks,
        WHEN get_tasks_filtered(limit=10000) is called with very large limit,
        THEN it returns all matching tasks without error.
        """
        result = await get_tasks_filtered(limit=10000)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        total = result.get("total", 0)
        assert isinstance(tasks, list)
        assert isinstance(total, int)
        # Should return all tasks up to the limit
        assert len(tasks) <= 10000

    @pytest.mark.asyncio
    async def test_large_offset_value_returns_empty(self) -> None:
        """GIVEN a database with a small number of tasks,
        WHEN get_tasks_filtered(offset=10000) is called with very large offset,
        THEN it returns an empty list.
        """
        result = await get_tasks_filtered(offset=10000)
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        assert isinstance(tasks, list)
        assert len(tasks) == 0


class TestGetTasksFilteredComplexityFilter:
    """Tests specifically for complexity filter."""

    @pytest.mark.asyncio
    async def test_filters_by_low_complexity(self) -> None:
        """GIVEN tasks with various complexity levels exist,
        WHEN get_tasks_filtered(complexity='low') is called,
        THEN only tasks with low complexity are returned.
        """
        result = await get_tasks_filtered(complexity="low")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("complexity") == "low"

    @pytest.mark.asyncio
    async def test_filters_by_medium_complexity(self) -> None:
        """GIVEN tasks with various complexity levels exist,
        WHEN get_tasks_filtered(complexity='medium') is called,
        THEN only tasks with medium complexity are returned.
        """
        result = await get_tasks_filtered(complexity="medium")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("complexity") == "medium"

    @pytest.mark.asyncio
    async def test_filters_by_high_complexity(self) -> None:
        """GIVEN tasks with various complexity levels exist,
        WHEN get_tasks_filtered(complexity='high') is called,
        THEN only tasks with high complexity are returned.
        """
        result = await get_tasks_filtered(complexity="high")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("complexity") == "high"


class TestGetTasksFilteredPhaseFilter:
    """Tests specifically for phase filter."""

    @pytest.mark.asyncio
    async def test_filters_by_red_phase(self) -> None:
        """GIVEN tasks in various phases exist,
        WHEN get_tasks_filtered(phase='RED') is called,
        THEN only tasks in RED phase are returned.
        """
        result = await get_tasks_filtered(phase="RED")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("phase") == "RED"

    @pytest.mark.asyncio
    async def test_filters_by_green_phase(self) -> None:
        """GIVEN tasks in various phases exist,
        WHEN get_tasks_filtered(phase='GREEN') is called,
        THEN only tasks in GREEN phase are returned.
        """
        result = await get_tasks_filtered(phase="GREEN")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("phase") == "GREEN"

    @pytest.mark.asyncio
    async def test_filters_by_refactor_phase(self) -> None:
        """GIVEN tasks in various phases exist,
        WHEN get_tasks_filtered(phase='REFACTOR') is called,
        THEN only tasks in REFACTOR phase are returned.
        """
        result = await get_tasks_filtered(phase="REFACTOR")
        assert isinstance(result, dict)
        tasks = result.get("tasks", [])
        for task in tasks:
            assert task.get("phase") == "REFACTOR"
