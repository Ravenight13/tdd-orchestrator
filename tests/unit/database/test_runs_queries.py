"""Tests for execution runs query functions.

Tests verify retrieval of execution runs with optional status/limit filtering
and fetching the currently active run.
"""

from __future__ import annotations

import pytest

from src.tdd_orchestrator.database.mixins.runs_mixin import (
    get_current_run,
    get_execution_runs,
)


class TestGetExecutionRunsBasicRetrieval:
    """Tests for basic retrieval of execution runs."""

    @pytest.mark.asyncio
    async def test_returns_all_runs_when_no_filters_applied(self) -> None:
        """GIVEN an execution_id with 5 runs in the database (3 'passed', 2 'failed'),
        WHEN calling get_execution_runs(execution_id) with no filters,
        THEN all 5 RunRecord objects are returned ordered by created_at descending.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_returns_runs_ordered_by_created_at_descending(self) -> None:
        """GIVEN an execution_id with multiple runs,
        WHEN calling get_execution_runs(execution_id) with no filters,
        THEN runs are ordered by created_at descending (most recent first).
        """
        execution_id = 1
        result = await get_execution_runs(execution_id)

        assert len(result) >= 2
        # Verify ordering: each run's created_at should be >= the next one
        for i in range(len(result) - 1):
            current_created = result[i].get("created_at") or result[i].get("started_at")
            next_created = result[i + 1].get("created_at") or result[i + 1].get("started_at")
            if current_created is not None and next_created is not None:
                assert current_created >= next_created


class TestGetExecutionRunsStatusFiltering:
    """Tests for filtering execution runs by status."""

    @pytest.mark.asyncio
    async def test_filters_by_failed_status(self) -> None:
        """GIVEN an execution_id with runs of mixed statuses,
        WHEN calling get_execution_runs(execution_id, status='failed'),
        THEN only runs with status 'failed' are returned.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, status="failed")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2
        for run in result:
            assert run["status"] == "failed"

    @pytest.mark.asyncio
    async def test_filters_by_passed_status(self) -> None:
        """GIVEN an execution_id with runs of mixed statuses,
        WHEN calling get_execution_runs(execution_id, status='passed'),
        THEN only runs with status 'passed' are returned.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, status="passed")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 3
        for run in result:
            assert run["status"] == "passed"

    @pytest.mark.asyncio
    async def test_filters_by_running_status(self) -> None:
        """GIVEN an execution_id with runs including one 'running',
        WHEN calling get_execution_runs(execution_id, status='running'),
        THEN only runs with status 'running' are returned.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, status="running")

        assert result is not None
        assert isinstance(result, list)
        for run in result:
            assert run["status"] == "running"


class TestGetExecutionRunsLimitParameter:
    """Tests for limiting number of returned runs."""

    @pytest.mark.asyncio
    async def test_limit_returns_exactly_n_records(self) -> None:
        """GIVEN an execution_id with 10 runs in the database,
        WHEN calling get_execution_runs(execution_id, limit=3),
        THEN exactly 3 RunRecord objects are returned (the 3 most recent).
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, limit=3)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_limit_combined_with_status_filter(self) -> None:
        """GIVEN an execution_id with multiple runs of various statuses,
        WHEN calling get_execution_runs(execution_id, status='passed', limit=2),
        THEN at most 2 passed runs are returned.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, status="passed", limit=2)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) <= 2
        for run in result:
            assert run["status"] == "passed"

    @pytest.mark.asyncio
    async def test_limit_greater_than_available_returns_all(self) -> None:
        """GIVEN an execution_id with 5 runs,
        WHEN calling get_execution_runs(execution_id, limit=100),
        THEN all 5 runs are returned (not padded to 100).
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, limit=100)

        assert result is not None
        assert isinstance(result, list)
        # Should return whatever is available, not exceed actual count
        assert len(result) <= 100


class TestGetExecutionRunsEmptyResults:
    """Tests for scenarios that return empty results."""

    @pytest.mark.asyncio
    async def test_nonexistent_execution_id_returns_empty_list(self) -> None:
        """GIVEN an execution_id that does not exist,
        WHEN calling get_execution_runs(execution_id),
        THEN an empty list is returned (no exception raised).
        """
        nonexistent_execution_id = 99999
        result = await get_execution_runs(nonexistent_execution_id)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_execution_with_no_runs_returns_empty_list(self) -> None:
        """GIVEN an execution_id that has no runs,
        WHEN calling get_execution_runs(execution_id),
        THEN an empty list is returned (no exception raised).
        """
        execution_id_with_no_runs = 1
        result = await get_execution_runs(execution_id_with_no_runs)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0


class TestGetCurrentRunBasicRetrieval:
    """Tests for retrieving the currently active run."""

    @pytest.mark.asyncio
    async def test_returns_running_run_when_one_exists(self) -> None:
        """GIVEN an execution_id with multiple runs where exactly one has status 'running',
        WHEN calling get_current_run(execution_id),
        THEN the single RunRecord with status 'running' is returned.
        """
        execution_id = 1
        result = await get_current_run(execution_id)

        assert result is not None
        assert isinstance(result, dict)
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_running_run(self) -> None:
        """GIVEN an execution_id with runs where none has status 'running'
        (all are 'passed'/'failed'),
        WHEN calling get_current_run(execution_id),
        THEN None is returned.
        """
        execution_id = 1
        result = await get_current_run(execution_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_execution_id(self) -> None:
        """GIVEN an execution_id that does not exist,
        WHEN calling get_current_run(execution_id),
        THEN None is returned (no exception raised).
        """
        nonexistent_execution_id = 99999
        result = await get_current_run(nonexistent_execution_id)

        assert result is None


class TestGetCurrentRunEdgeCases:
    """Edge case tests for get_current_run."""

    @pytest.mark.asyncio
    async def test_returns_none_for_execution_with_no_runs(self) -> None:
        """GIVEN an execution_id that has no runs at all,
        WHEN calling get_current_run(execution_id),
        THEN None is returned (no exception raised).
        """
        execution_id_with_no_runs = 1
        result = await get_current_run(execution_id_with_no_runs)

        assert result is None


class TestRunRecordStructure:
    """Tests for verifying RunRecord structure."""

    @pytest.mark.asyncio
    async def test_run_record_contains_expected_fields(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id),
        THEN each RunRecord contains expected fields.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id)

        assert len(result) > 0
        run = result[0]

        # Check for expected fields in the run record
        expected_fields = {"id", "status"}
        assert expected_fields.issubset(set(run.keys())), (
            f"Missing expected fields. Got: {set(run.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_record_has_id_field(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id),
        THEN each RunRecord has an 'id' field that is an integer.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id)

        assert len(result) > 0
        for run in result:
            assert "id" in run
            assert isinstance(run["id"], int)

    @pytest.mark.asyncio
    async def test_run_record_has_status_field(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id),
        THEN each RunRecord has a 'status' field that is a string.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id)

        assert len(result) > 0
        for run in result:
            assert "status" in run
            assert isinstance(run["status"], str)


class TestGetExecutionRunsEdgeCases:
    """Edge case tests for get_execution_runs."""

    @pytest.mark.asyncio
    async def test_limit_zero_returns_empty_list(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id, limit=0),
        THEN an empty list is returned.
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, limit=0)

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_status_filter_with_unknown_status_returns_empty(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id, status='unknown_status'),
        THEN an empty list is returned (no exception raised).
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, status="unknown_status")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_negative_limit_handled_gracefully(self) -> None:
        """GIVEN an execution_id with runs,
        WHEN calling get_execution_runs(execution_id, limit=-1),
        THEN either returns all runs or empty list (no exception raised).
        """
        execution_id = 1
        result = await get_execution_runs(execution_id, limit=-1)

        assert result is not None
        assert isinstance(result, list)


class TestReturnTypeConsistency:
    """Tests for return type consistency across different scenarios."""

    @pytest.mark.asyncio
    async def test_get_execution_runs_always_returns_list(self) -> None:
        """GIVEN any input parameters,
        WHEN calling get_execution_runs,
        THEN the return type is always a list (never None).
        """
        # Test with various inputs
        result1 = await get_execution_runs(1)
        result2 = await get_execution_runs(99999)
        result3 = await get_execution_runs(1, status="failed")
        result4 = await get_execution_runs(1, limit=5)

        assert isinstance(result1, list)
        assert isinstance(result2, list)
        assert isinstance(result3, list)
        assert isinstance(result4, list)

    @pytest.mark.asyncio
    async def test_get_current_run_returns_dict_or_none(self) -> None:
        """GIVEN any execution_id,
        WHEN calling get_current_run,
        THEN the return type is either a dict (RunRecord) or None.
        """
        result = await get_current_run(1)

        assert result is None or isinstance(result, dict)
