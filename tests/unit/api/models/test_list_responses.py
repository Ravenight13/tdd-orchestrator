"""Tests for compound API response models (detail and list wrappers).

These tests verify that compound response models correctly handle:
- TaskDetailResponse wrapping TaskResponse with metadata
- TaskListResponse wrapping list of TaskResponse with pagination
- WorkerListResponse wrapping list of WorkerResponse with pagination
- CircuitBreakerListResponse wrapping list of CircuitBreakerResponse with pagination
- Validation errors for missing/invalid fields
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tdd_orchestrator.api.models.responses import (
    CircuitBreakerListResponse,
    CircuitBreakerResponse,
    TaskDetailResponse,
    TaskListResponse,
    TaskResponse,
    WorkerListResponse,
    WorkerResponse,
)


class TestTaskDetailResponse:
    """Tests for TaskDetailResponse model."""

    def test_task_detail_response_wraps_task_in_task_field(self) -> None:
        """GIVEN a valid TaskResponse dict WHEN constructing TaskDetailResponse THEN task is wrapped in 'task' field."""
        task_data = {
            "id": "task-123",
            "spec": "Test specification",
            "status": "pending",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "subtasks": [],
            "config": {},
        }
        data = {
            "task": task_data,
            "metadata": {"retrieved_at": "2024-01-15T10:30:00Z"},
        }

        result = TaskDetailResponse.model_validate(data)

        assert result.task.id == "task-123"
        assert result.task.spec == "Test specification"
        assert result.task.status == "pending"

    def test_task_detail_response_includes_metadata_with_retrieved_at(self) -> None:
        """GIVEN a TaskDetailResponse WHEN metadata is provided THEN it includes retrieved_at ISO-8601 timestamp."""
        task_data = {
            "id": "task-456",
            "spec": "Another spec",
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
            "subtasks": [],
            "config": {},
        }
        retrieved_at = "2024-06-15T14:30:00Z"
        data = {
            "task": task_data,
            "metadata": {"retrieved_at": retrieved_at},
        }

        result = TaskDetailResponse.model_validate(data)

        assert result.metadata["retrieved_at"] == retrieved_at
        assert isinstance(result.metadata, dict)

    def test_task_detail_response_round_trips_through_model_dump_validate(self) -> None:
        """GIVEN a TaskDetailResponse WHEN serializing and revalidating THEN data round-trips correctly."""
        task_data = {
            "id": "task-789",
            "spec": "Round trip spec",
            "status": "running",
            "created_at": datetime(2024, 3, 20, 8, 0, 0, tzinfo=timezone.utc),
            "subtasks": [{"id": "sub-1"}],
            "config": {"key": "value"},
        }
        data = {
            "task": task_data,
            "metadata": {"retrieved_at": "2024-03-20T08:05:00Z"},
        }

        original = TaskDetailResponse.model_validate(data)
        dumped = original.model_dump()
        restored = TaskDetailResponse.model_validate(dumped)

        assert restored.task.id == original.task.id
        assert restored.task.spec == original.task.spec
        assert restored.task.status == original.task.status
        assert restored.metadata["retrieved_at"] == original.metadata["retrieved_at"]

    def test_task_detail_response_raises_validation_error_when_task_missing(
        self,
    ) -> None:
        """GIVEN data without 'task' field WHEN constructing TaskDetailResponse THEN ValidationError is raised."""
        data = {
            "metadata": {"retrieved_at": "2024-01-15T10:30:00Z"},
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskDetailResponse.model_validate(data)

        assert "task" in str(exc_info.value).lower()

    def test_task_detail_response_raises_validation_error_when_metadata_missing(
        self,
    ) -> None:
        """GIVEN data without 'metadata' field WHEN constructing TaskDetailResponse THEN ValidationError is raised."""
        task_data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": [],
            "config": {},
        }
        data = {"task": task_data}

        with pytest.raises(ValidationError) as exc_info:
            TaskDetailResponse.model_validate(data)

        assert "metadata" in str(exc_info.value).lower()


class TestTaskListResponse:
    """Tests for TaskListResponse model."""

    def test_task_list_response_wraps_tasks_in_tasks_field(self) -> None:
        """GIVEN a list of TaskResponse dicts WHEN constructing TaskListResponse THEN tasks are wrapped in 'tasks' field."""
        tasks_data = [
            {
                "id": "task-1",
                "spec": "Spec 1",
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "subtasks": [],
                "config": {},
            },
            {
                "id": "task-2",
                "spec": "Spec 2",
                "status": "completed",
                "created_at": datetime.now(timezone.utc),
                "subtasks": [],
                "config": {},
            },
        ]
        data = {
            "tasks": tasks_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = TaskListResponse.model_validate(data)

        assert len(result.tasks) == 2
        assert result.tasks[0].id == "task-1"
        assert result.tasks[1].id == "task-2"

    def test_task_list_response_includes_pagination_fields(self) -> None:
        """GIVEN TaskListResponse with pagination WHEN constructed THEN total, limit, offset fields are present."""
        tasks_data = [
            {
                "id": f"task-{i}",
                "spec": f"Spec {i}",
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "subtasks": [],
                "config": {},
            }
            for i in range(10)
        ]
        data = {
            "tasks": tasks_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = TaskListResponse.model_validate(data)

        assert result.total == 50
        assert result.limit == 10
        assert result.offset == 20

    def test_task_list_response_serializes_all_fields_correctly(self) -> None:
        """GIVEN TaskListResponse with 10 tasks WHEN serializing THEN all fields are correctly serialized."""
        tasks_data = [
            {
                "id": f"task-{i}",
                "spec": f"Spec {i}",
                "status": "pending",
                "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
                "subtasks": [],
                "config": {},
            }
            for i in range(10)
        ]
        data = {
            "tasks": tasks_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = TaskListResponse.model_validate(data)
        dumped = result.model_dump()

        assert len(dumped["tasks"]) == 10
        assert dumped["total"] == 50
        assert dumped["limit"] == 10
        assert dumped["offset"] == 20

    def test_task_list_response_tasks_length_matches_provided_list(self) -> None:
        """GIVEN a list of 10 TaskResponse objects WHEN constructing TaskListResponse THEN tasks length matches."""
        tasks_data = [
            {
                "id": f"task-{i}",
                "spec": f"Spec {i}",
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "subtasks": [],
                "config": {},
            }
            for i in range(10)
        ]
        data = {
            "tasks": tasks_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = TaskListResponse.model_validate(data)

        assert len(result.tasks) == len(tasks_data)

    def test_task_list_response_handles_empty_tasks_list(self) -> None:
        """GIVEN empty tasks list WHEN constructing TaskListResponse THEN serializes with tasks=[] and total=0."""
        data = {
            "tasks": [],
            "total": 0,
            "limit": 10,
            "offset": 0,
        }

        result = TaskListResponse.model_validate(data)
        dumped = result.model_dump()

        assert result.tasks == []
        assert dumped["tasks"] == []
        assert dumped["total"] == 0
        assert dumped["limit"] == 10
        assert dumped["offset"] == 0

    def test_task_list_response_raises_validation_error_when_total_missing(
        self,
    ) -> None:
        """GIVEN data without 'total' field WHEN constructing TaskListResponse THEN ValidationError is raised."""
        data = {
            "tasks": [],
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskListResponse.model_validate(data)

        assert "total" in str(exc_info.value).lower()

    def test_task_list_response_raises_validation_error_when_limit_missing(
        self,
    ) -> None:
        """GIVEN data without 'limit' field WHEN constructing TaskListResponse THEN ValidationError is raised."""
        data = {
            "tasks": [],
            "total": 0,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskListResponse.model_validate(data)

        assert "limit" in str(exc_info.value).lower()

    def test_task_list_response_raises_validation_error_when_offset_missing(
        self,
    ) -> None:
        """GIVEN data without 'offset' field WHEN constructing TaskListResponse THEN ValidationError is raised."""
        data = {
            "tasks": [],
            "total": 0,
            "limit": 10,
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskListResponse.model_validate(data)

        assert "offset" in str(exc_info.value).lower()

    def test_task_list_response_raises_validation_error_when_total_wrong_type(
        self,
    ) -> None:
        """GIVEN total as string 'abc' WHEN constructing TaskListResponse THEN ValidationError is raised."""
        data = {
            "tasks": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskListResponse.model_validate(data)

        error_str = str(exc_info.value).lower()
        assert "total" in error_str or "int" in error_str


class TestWorkerResponse:
    """Tests for WorkerResponse model."""

    def test_worker_response_can_be_constructed_with_valid_data(self) -> None:
        """GIVEN valid worker data WHEN constructing WorkerResponse THEN model is created successfully."""
        data = {
            "id": "worker-123",
            "status": "active",
            "current_task_id": "task-456",
            "started_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }

        result = WorkerResponse.model_validate(data)

        assert result.id == "worker-123"
        assert result.status == "active"


class TestWorkerListResponse:
    """Tests for WorkerListResponse model."""

    def test_worker_list_response_wraps_workers_in_workers_field(self) -> None:
        """GIVEN a list of WorkerResponse dicts WHEN constructing WorkerListResponse THEN workers are wrapped in 'workers' field."""
        workers_data = [
            {
                "id": "worker-1",
                "status": "active",
                "current_task_id": None,
                "started_at": datetime.now(timezone.utc),
            },
            {
                "id": "worker-2",
                "status": "idle",
                "current_task_id": None,
                "started_at": datetime.now(timezone.utc),
            },
        ]
        data = {
            "workers": workers_data,
            "total": 2,
            "limit": 10,
            "offset": 0,
        }

        result = WorkerListResponse.model_validate(data)

        assert len(result.workers) == 2
        assert result.workers[0].id == "worker-1"
        assert result.workers[1].id == "worker-2"

    def test_worker_list_response_includes_pagination_fields(self) -> None:
        """GIVEN WorkerListResponse with pagination WHEN constructed THEN total, limit, offset fields are present."""
        workers_data = [
            {
                "id": "worker-1",
                "status": "active",
                "current_task_id": None,
                "started_at": datetime.now(timezone.utc),
            },
        ]
        data = {
            "workers": workers_data,
            "total": 100,
            "limit": 25,
            "offset": 50,
        }

        result = WorkerListResponse.model_validate(data)

        assert result.total == 100
        assert result.limit == 25
        assert result.offset == 50

    def test_worker_list_response_raises_validation_error_when_total_missing(
        self,
    ) -> None:
        """GIVEN data without 'total' field WHEN constructing WorkerListResponse THEN ValidationError is raised."""
        data = {
            "workers": [],
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            WorkerListResponse.model_validate(data)

        assert "total" in str(exc_info.value).lower()

    def test_worker_list_response_raises_validation_error_when_total_wrong_type(
        self,
    ) -> None:
        """GIVEN total as string 'abc' WHEN constructing WorkerListResponse THEN ValidationError is raised."""
        data = {
            "workers": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            WorkerListResponse.model_validate(data)

        error_str = str(exc_info.value).lower()
        assert "total" in error_str or "int" in error_str

    def test_worker_list_response_follows_same_pattern_as_task_list(self) -> None:
        """GIVEN WorkerListResponse WHEN structured THEN it follows the same pagination pattern as TaskListResponse."""
        workers_data = [
            {
                "id": f"worker-{i}",
                "status": "active",
                "current_task_id": None,
                "started_at": datetime.now(timezone.utc),
            }
            for i in range(5)
        ]
        data = {
            "workers": workers_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = WorkerListResponse.model_validate(data)
        dumped = result.model_dump()

        assert "workers" in dumped
        assert "total" in dumped
        assert "limit" in dumped
        assert "offset" in dumped
        assert len(dumped["workers"]) == 5


class TestCircuitBreakerResponse:
    """Tests for CircuitBreakerResponse model."""

    def test_circuit_breaker_response_can_be_constructed_with_valid_data(self) -> None:
        """GIVEN valid circuit breaker data WHEN constructing CircuitBreakerResponse THEN model is created successfully."""
        data = {
            "id": "cb-123",
            "name": "api-circuit-breaker",
            "state": "closed",
            "failure_count": 0,
            "last_failure_at": None,
        }

        result = CircuitBreakerResponse.model_validate(data)

        assert result.id == "cb-123"
        assert result.name == "api-circuit-breaker"
        assert result.state == "closed"


class TestCircuitBreakerListResponse:
    """Tests for CircuitBreakerListResponse model."""

    def test_circuit_breaker_list_response_wraps_in_circuit_breakers_field(
        self,
    ) -> None:
        """GIVEN a list of CircuitBreakerResponse dicts WHEN constructing CircuitBreakerListResponse THEN items are wrapped in 'circuit_breakers' field."""
        cb_data = [
            {
                "id": "cb-1",
                "name": "cb-one",
                "state": "closed",
                "failure_count": 0,
                "last_failure_at": None,
            },
            {
                "id": "cb-2",
                "name": "cb-two",
                "state": "open",
                "failure_count": 5,
                "last_failure_at": datetime.now(timezone.utc),
            },
        ]
        data = {
            "circuit_breakers": cb_data,
            "total": 2,
            "limit": 10,
            "offset": 0,
        }

        result = CircuitBreakerListResponse.model_validate(data)

        assert len(result.circuit_breakers) == 2
        assert result.circuit_breakers[0].id == "cb-1"
        assert result.circuit_breakers[1].id == "cb-2"

    def test_circuit_breaker_list_response_includes_pagination_fields(self) -> None:
        """GIVEN CircuitBreakerListResponse with pagination WHEN constructed THEN total, limit, offset fields are present."""
        cb_data = [
            {
                "id": "cb-1",
                "name": "cb-one",
                "state": "closed",
                "failure_count": 0,
                "last_failure_at": None,
            },
        ]
        data = {
            "circuit_breakers": cb_data,
            "total": 100,
            "limit": 25,
            "offset": 50,
        }

        result = CircuitBreakerListResponse.model_validate(data)

        assert result.total == 100
        assert result.limit == 25
        assert result.offset == 50

    def test_circuit_breaker_list_response_raises_validation_error_when_total_missing(
        self,
    ) -> None:
        """GIVEN data without 'total' field WHEN constructing CircuitBreakerListResponse THEN ValidationError is raised."""
        data = {
            "circuit_breakers": [],
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            CircuitBreakerListResponse.model_validate(data)

        assert "total" in str(exc_info.value).lower()

    def test_circuit_breaker_list_response_raises_validation_error_when_total_wrong_type(
        self,
    ) -> None:
        """GIVEN total as string 'abc' WHEN constructing CircuitBreakerListResponse THEN ValidationError is raised."""
        data = {
            "circuit_breakers": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError) as exc_info:
            CircuitBreakerListResponse.model_validate(data)

        error_str = str(exc_info.value).lower()
        assert "total" in error_str or "int" in error_str

    def test_circuit_breaker_list_response_follows_same_pattern_as_task_list(
        self,
    ) -> None:
        """GIVEN CircuitBreakerListResponse WHEN structured THEN it follows the same pagination pattern as TaskListResponse."""
        cb_data = [
            {
                "id": f"cb-{i}",
                "name": f"cb-{i}",
                "state": "closed",
                "failure_count": 0,
                "last_failure_at": None,
            }
            for i in range(5)
        ]
        data = {
            "circuit_breakers": cb_data,
            "total": 50,
            "limit": 10,
            "offset": 20,
        }

        result = CircuitBreakerListResponse.model_validate(data)
        dumped = result.model_dump()

        assert "circuit_breakers" in dumped
        assert "total" in dumped
        assert "limit" in dumped
        assert "offset" in dumped
        assert len(dumped["circuit_breakers"]) == 5


class TestValidationErrorsAcrossAllListResponses:
    """Cross-cutting validation tests for all list response models."""

    def test_all_list_responses_require_total_field(self) -> None:
        """GIVEN list responses without 'total' WHEN constructed THEN all raise ValidationError."""
        task_data: dict[str, object] = {"tasks": [], "limit": 10, "offset": 0}
        worker_data: dict[str, object] = {"workers": [], "limit": 10, "offset": 0}
        cb_data: dict[str, object] = {"circuit_breakers": [], "limit": 10, "offset": 0}

        with pytest.raises(ValidationError):
            TaskListResponse.model_validate(task_data)

        with pytest.raises(ValidationError):
            WorkerListResponse.model_validate(worker_data)

        with pytest.raises(ValidationError):
            CircuitBreakerListResponse.model_validate(cb_data)

    def test_all_list_responses_reject_invalid_type_for_total(self) -> None:
        """GIVEN list responses with total='abc' WHEN constructed THEN all raise ValidationError."""
        task_data: dict[str, object] = {
            "tasks": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }
        worker_data: dict[str, object] = {
            "workers": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }
        cb_data: dict[str, object] = {
            "circuit_breakers": [],
            "total": "abc",
            "limit": 10,
            "offset": 0,
        }

        with pytest.raises(ValidationError):
            TaskListResponse.model_validate(task_data)

        with pytest.raises(ValidationError):
            WorkerListResponse.model_validate(worker_data)

        with pytest.raises(ValidationError):
            CircuitBreakerListResponse.model_validate(cb_data)

    def test_all_list_responses_require_limit_field(self) -> None:
        """GIVEN list responses without 'limit' WHEN constructed THEN all raise ValidationError."""
        task_data: dict[str, object] = {"tasks": [], "total": 0, "offset": 0}
        worker_data: dict[str, object] = {"workers": [], "total": 0, "offset": 0}
        cb_data: dict[str, object] = {"circuit_breakers": [], "total": 0, "offset": 0}

        with pytest.raises(ValidationError):
            TaskListResponse.model_validate(task_data)

        with pytest.raises(ValidationError):
            WorkerListResponse.model_validate(worker_data)

        with pytest.raises(ValidationError):
            CircuitBreakerListResponse.model_validate(cb_data)

    def test_all_list_responses_require_offset_field(self) -> None:
        """GIVEN list responses without 'offset' WHEN constructed THEN all raise ValidationError."""
        task_data: dict[str, object] = {"tasks": [], "total": 0, "limit": 10}
        worker_data: dict[str, object] = {"workers": [], "total": 0, "limit": 10}
        cb_data: dict[str, object] = {"circuit_breakers": [], "total": 0, "limit": 10}

        with pytest.raises(ValidationError):
            TaskListResponse.model_validate(task_data)

        with pytest.raises(ValidationError):
            WorkerListResponse.model_validate(worker_data)

        with pytest.raises(ValidationError):
            CircuitBreakerListResponse.model_validate(cb_data)
