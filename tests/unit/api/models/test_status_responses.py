"""Tests for health check, run management, progress tracking, and statistics response models."""

import pytest
from pydantic import ValidationError

from src.tdd_orchestrator.api.models.responses import (
    HealthResponse,
    ProgressResponse,
    RunListResponse,
    RunResponse,
    StatsResponse,
)


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_health_response_serializes_with_all_fields(self) -> None:
        """HealthResponse with valid data serializes to dict with correct types."""
        response = HealthResponse(
            status="ok",
            version="1.0.0",
            uptime_seconds=123.45,
        )
        data = response.model_dump()

        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["uptime_seconds"] == 123.45
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["uptime_seconds"], float)

    def test_health_response_accepts_degraded_status(self) -> None:
        """HealthResponse accepts 'degraded' as a valid status."""
        response = HealthResponse(
            status="degraded",
            version="2.0.0",
            uptime_seconds=0.0,
        )

        assert response.status == "degraded"

    def test_health_response_rejects_invalid_status(self) -> None:
        """HealthResponse raises ValidationError for invalid status values."""
        with pytest.raises(ValidationError) as exc_info:
            HealthResponse(
                status="unknown",
                version="1.0.0",
                uptime_seconds=100.0,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_health_response_rejects_empty_status(self) -> None:
        """HealthResponse raises ValidationError for empty status."""
        with pytest.raises(ValidationError) as exc_info:
            HealthResponse(
                status="",
                version="1.0.0",
                uptime_seconds=100.0,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1


class TestRunResponse:
    """Tests for RunResponse model."""

    def test_run_response_round_trips_with_all_fields(self) -> None:
        """RunResponse round-trips through model_validate preserving all values."""
        original = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440000",
            status="pending",
            created_at="2024-01-15T10:30:00Z",
            task_count=5,
            progress=0.5,
        )

        dumped = original.model_dump()
        restored = RunResponse.model_validate(dumped)

        assert restored.run_id == "550e8400-e29b-41d4-a716-446655440000"
        assert restored.status == "pending"
        assert restored.created_at == "2024-01-15T10:30:00Z"
        assert restored.task_count == 5
        assert restored.progress == 0.5

    def test_run_response_round_trips_with_none_progress(self) -> None:
        """RunResponse preserves None for omitted optional progress field."""
        original = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440000",
            status="running",
            created_at="2024-01-15T10:30:00Z",
            task_count=10,
        )

        dumped = original.model_dump()
        restored = RunResponse.model_validate(dumped)

        assert restored.progress is None

    def test_run_response_accepts_all_valid_statuses(self) -> None:
        """RunResponse accepts all defined status literals."""
        valid_statuses = ["pending", "running", "completed", "failed"]

        for status in valid_statuses:
            response = RunResponse(
                run_id="550e8400-e29b-41d4-a716-446655440000",
                status=status,
                created_at="2024-01-15T10:30:00Z",
                task_count=1,
            )
            assert response.status == status

    def test_run_response_rejects_invalid_status(self) -> None:
        """RunResponse raises ValidationError for invalid status values."""
        with pytest.raises(ValidationError) as exc_info:
            RunResponse(
                run_id="550e8400-e29b-41d4-a716-446655440000",
                status="unknown",
                created_at="2024-01-15T10:30:00Z",
                task_count=1,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_run_response_progress_at_boundaries(self) -> None:
        """RunResponse accepts progress at boundary values 0.0 and 1.0."""
        response_zero = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440000",
            status="pending",
            created_at="2024-01-15T10:30:00Z",
            task_count=1,
            progress=0.0,
        )
        assert response_zero.progress == 0.0

        response_one = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440000",
            status="completed",
            created_at="2024-01-15T10:30:00Z",
            task_count=1,
            progress=1.0,
        )
        assert response_one.progress == 1.0


class TestProgressResponse:
    """Tests for ProgressResponse model."""

    def test_progress_response_computes_completion_percentage(self) -> None:
        """ProgressResponse correctly computes completion_percentage property."""
        response = ProgressResponse(
            total_tasks=10,
            completed_tasks=5,
            failed_tasks=2,
            pending_tasks=3,
        )

        assert response.completion_percentage == 50.0

    def test_progress_response_completion_percentage_is_read_only(self) -> None:
        """completion_percentage is a read-only computed property."""
        response = ProgressResponse(
            total_tasks=10,
            completed_tasks=5,
            failed_tasks=2,
            pending_tasks=3,
        )

        with pytest.raises((AttributeError, ValidationError)):
            response.completion_percentage = 100.0  # type: ignore[misc]

    def test_progress_response_zero_total_tasks_returns_zero_percentage(self) -> None:
        """When total_tasks is 0, completion_percentage is 0.0 (no ZeroDivisionError)."""
        response = ProgressResponse(
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            pending_tasks=0,
        )

        assert response.completion_percentage == 0.0

    def test_progress_response_validates_task_sum_equals_total(self) -> None:
        """ProgressResponse raises ValidationError when task counts don't sum to total."""
        with pytest.raises(ValidationError) as exc_info:
            ProgressResponse(
                total_tasks=10,
                completed_tasks=5,
                failed_tasks=2,
                pending_tasks=1,  # Sum is 8, not 10
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_progress_response_accepts_matching_task_sum(self) -> None:
        """ProgressResponse accepts when completed + failed + pending equals total."""
        response = ProgressResponse(
            total_tasks=100,
            completed_tasks=50,
            failed_tasks=30,
            pending_tasks=20,
        )

        assert response.total_tasks == 100
        assert response.completed_tasks == 50
        assert response.failed_tasks == 30
        assert response.pending_tasks == 20

    def test_progress_response_rejects_negative_total_tasks(self) -> None:
        """ProgressResponse rejects negative total_tasks."""
        with pytest.raises(ValidationError) as exc_info:
            ProgressResponse(
                total_tasks=-1,
                completed_tasks=0,
                failed_tasks=0,
                pending_tasks=0,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_progress_response_rejects_negative_completed_tasks(self) -> None:
        """ProgressResponse rejects negative completed_tasks."""
        with pytest.raises(ValidationError) as exc_info:
            ProgressResponse(
                total_tasks=10,
                completed_tasks=-1,
                failed_tasks=5,
                pending_tasks=6,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_progress_response_rejects_negative_failed_tasks(self) -> None:
        """ProgressResponse rejects negative failed_tasks."""
        with pytest.raises(ValidationError) as exc_info:
            ProgressResponse(
                total_tasks=10,
                completed_tasks=5,
                failed_tasks=-1,
                pending_tasks=6,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_progress_response_rejects_negative_pending_tasks(self) -> None:
        """ProgressResponse rejects negative pending_tasks."""
        with pytest.raises(ValidationError) as exc_info:
            ProgressResponse(
                total_tasks=10,
                completed_tasks=5,
                failed_tasks=6,
                pending_tasks=-1,
            )

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_progress_response_completion_percentage_calculation_accuracy(self) -> None:
        """completion_percentage calculates as (completed_tasks / total_tasks * 100.0)."""
        response = ProgressResponse(
            total_tasks=3,
            completed_tasks=1,
            failed_tasks=1,
            pending_tasks=1,
        )

        expected = 1 / 3 * 100.0
        assert abs(response.completion_percentage - expected) < 0.0001


class TestRunListResponse:
    """Tests for RunListResponse model."""

    def test_run_list_response_contains_list_of_runs(self) -> None:
        """RunListResponse holds a list of RunResponse objects."""
        run1 = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440001",
            status="completed",
            created_at="2024-01-15T10:30:00Z",
            task_count=5,
            progress=1.0,
        )
        run2 = RunResponse(
            run_id="550e8400-e29b-41d4-a716-446655440002",
            status="running",
            created_at="2024-01-15T11:30:00Z",
            task_count=10,
            progress=0.3,
        )

        response = RunListResponse(runs=[run1, run2])

        assert len(response.runs) == 2
        assert response.runs[0].run_id == "550e8400-e29b-41d4-a716-446655440001"
        assert response.runs[1].run_id == "550e8400-e29b-41d4-a716-446655440002"

    def test_run_list_response_empty_list(self) -> None:
        """RunListResponse accepts an empty list of runs."""
        response = RunListResponse(runs=[])

        assert response.runs == []
        assert len(response.runs) == 0


class TestStatsResponse:
    """Tests for StatsResponse model."""

    def test_stats_response_instantiation(self) -> None:
        """StatsResponse can be instantiated (basic existence test)."""
        # This test verifies the model exists and can be imported
        # Specific fields will depend on implementation requirements
        response = StatsResponse()

        assert response is not None

    def test_stats_response_serializes_to_dict(self) -> None:
        """StatsResponse serializes to a dictionary."""
        response = StatsResponse()
        data = response.model_dump()

        assert isinstance(data, dict)
