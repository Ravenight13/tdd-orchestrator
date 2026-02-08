"""Tests for core API response models.

These tests verify that Pydantic response models correctly handle:
- JSON-encoded columns (subtasks, config, test_output) with automatic deserialization
- ConfigDict(from_attributes=True) for ORM compatibility
- Optional fields accepting None values
- Error responses with proper structure
- Malformed JSON validation errors
"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.tdd_orchestrator.api.models.responses import (
    AttemptResponse,
    ErrorResponse,
    SSEEventData,
    TaskResponse,
)


class TestTaskResponse:
    """Tests for TaskResponse model."""

    def test_task_response_maps_scalar_fields_when_valid_dict_provided(self) -> None:
        """GIVEN a dict with valid task fields WHEN constructing TaskResponse THEN scalar fields are correctly mapped."""
        data = {
            "id": "task-123",
            "spec": "Test specification content",
            "status": "pending",
            "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "subtasks": "[]",
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        assert result.id == "task-123"
        assert result.spec == "Test specification content"
        assert result.status == "pending"
        assert result.created_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_task_response_deserializes_subtasks_json_string_to_list(self) -> None:
        """GIVEN subtasks as JSON string WHEN constructing TaskResponse THEN subtasks is deserialized to Python list."""
        subtasks_data = [
            {"id": "sub-1", "name": "First subtask"},
            {"id": "sub-2", "name": "Second subtask"},
        ]
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": json.dumps(subtasks_data),
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        assert isinstance(result.subtasks, list)
        assert len(result.subtasks) == 2
        assert result.subtasks[0]["id"] == "sub-1"
        assert result.subtasks[1]["name"] == "Second subtask"

    def test_task_response_deserializes_config_json_string_to_dict(self) -> None:
        """GIVEN config as JSON string WHEN constructing TaskResponse THEN config is deserialized to Python dict."""
        config_data = {"max_retries": 3, "timeout": 60, "debug": True}
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "[]",
            "config": json.dumps(config_data),
        }

        result = TaskResponse.model_validate(data)

        assert isinstance(result.config, dict)
        assert result.config["max_retries"] == 3
        assert result.config["timeout"] == 60
        assert result.config["debug"] is True

    def test_task_response_passes_through_subtasks_when_already_list(self) -> None:
        """GIVEN subtasks as native Python list WHEN constructing TaskResponse THEN value passes through unchanged."""
        subtasks_list = [{"id": "sub-1"}, {"id": "sub-2"}]
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": subtasks_list,
            "config": {},
        }

        result = TaskResponse.model_validate(data)

        assert result.subtasks == subtasks_list
        assert isinstance(result.subtasks, list)

    def test_task_response_passes_through_config_when_already_dict(self) -> None:
        """GIVEN config as native Python dict WHEN constructing TaskResponse THEN value passes through unchanged."""
        config_dict = {"key": "value", "nested": {"inner": 42}}
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": [],
            "config": config_dict,
        }

        result = TaskResponse.model_validate(data)

        assert result.config == config_dict
        assert isinstance(result.config, dict)

    def test_task_response_raises_validation_error_when_subtasks_malformed_json(self) -> None:
        """GIVEN malformed JSON in subtasks WHEN constructing TaskResponse THEN ValidationError is raised with field name."""
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "{invalid json",
            "config": "{}",
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskResponse.model_validate(data)

        error_str = str(exc_info.value)
        assert "subtasks" in error_str.lower() or "subtask" in error_str.lower()

    def test_task_response_raises_validation_error_when_config_malformed_json(self) -> None:
        """GIVEN malformed JSON in config WHEN constructing TaskResponse THEN ValidationError is raised with field name."""
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "[]",
            "config": "not valid json at all",
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskResponse.model_validate(data)

        error_str = str(exc_info.value)
        assert "config" in error_str.lower()

    def test_task_response_handles_empty_subtasks_json_array(self) -> None:
        """GIVEN empty JSON array for subtasks WHEN constructing TaskResponse THEN empty list is returned."""
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "[]",
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        assert result.subtasks == []
        assert isinstance(result.subtasks, list)

    def test_task_response_handles_empty_config_json_object(self) -> None:
        """GIVEN empty JSON object for config WHEN constructing TaskResponse THEN empty dict is returned."""
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "[]",
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        assert result.config == {}
        assert isinstance(result.config, dict)

    def test_task_response_works_with_from_attributes_true(self) -> None:
        """GIVEN an object with attributes WHEN using model_validate with from_attributes THEN fields are mapped."""

        class MockORMTask:
            id = "task-orm-1"
            spec = "ORM spec"
            status = "completed"
            created_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
            subtasks = '[{"id": "orm-sub"}]'
            config = '{"orm_key": "orm_value"}'

        result = TaskResponse.model_validate(MockORMTask(), from_attributes=True)

        assert result.id == "task-orm-1"
        assert result.spec == "ORM spec"
        assert result.status == "completed"
        assert result.subtasks == [{"id": "orm-sub"}]
        assert result.config == {"orm_key": "orm_value"}


class TestAttemptResponse:
    """Tests for AttemptResponse model."""

    def test_attempt_response_maps_all_fields_when_valid_dict_provided(self) -> None:
        """GIVEN a dict with valid attempt fields WHEN constructing AttemptResponse THEN all fields are correctly mapped."""
        started_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        finished_at = datetime(2024, 1, 15, 10, 35, 0, tzinfo=timezone.utc)
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 2,
            "status": "success",
            "started_at": started_at,
            "finished_at": finished_at,
            "test_output": '{"passed": 10, "failed": 0}',
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert result.id == "attempt-456"
        assert result.task_id == "task-123"
        assert result.attempt_number == 2
        assert result.status == "success"
        assert result.started_at == started_at
        assert result.finished_at == finished_at

    def test_attempt_response_deserializes_test_output_json_string(self) -> None:
        """GIVEN test_output as JSON string WHEN constructing AttemptResponse THEN it is deserialized to Python dict."""
        test_output_data = {
            "passed": 5,
            "failed": 2,
            "skipped": 1,
            "details": ["test1", "test2"],
        }
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "failed",
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "test_output": json.dumps(test_output_data),
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert isinstance(result.test_output, dict)
        assert result.test_output["passed"] == 5
        assert result.test_output["failed"] == 2
        assert result.test_output["details"] == ["test1", "test2"]

    def test_attempt_response_accepts_none_for_optional_error_info(self) -> None:
        """GIVEN error_info as None WHEN constructing AttemptResponse THEN no error is raised."""
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "success",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "test_output": "{}",
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert result.error_info is None

    def test_attempt_response_accepts_none_for_optional_finished_at(self) -> None:
        """GIVEN finished_at as None WHEN constructing AttemptResponse THEN no error is raised."""
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "test_output": "{}",
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert result.finished_at is None

    def test_attempt_response_passes_through_test_output_when_already_dict(self) -> None:
        """GIVEN test_output as native Python dict WHEN constructing AttemptResponse THEN value passes through unchanged."""
        test_output_dict = {"result": "success", "count": 42}
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "success",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "test_output": test_output_dict,
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert result.test_output == test_output_dict
        assert isinstance(result.test_output, dict)

    def test_attempt_response_raises_validation_error_when_test_output_malformed(self) -> None:
        """GIVEN malformed JSON in test_output WHEN constructing AttemptResponse THEN ValidationError is raised."""
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "failed",
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "test_output": "{broken json here",
            "error_info": None,
        }

        with pytest.raises(ValidationError) as exc_info:
            AttemptResponse.model_validate(data)

        error_str = str(exc_info.value)
        assert "test_output" in error_str.lower() or "test" in error_str.lower()

    def test_attempt_response_handles_error_info_as_json_string(self) -> None:
        """GIVEN error_info as JSON string WHEN constructing AttemptResponse THEN it is deserialized."""
        error_info_data = {"code": "TIMEOUT", "message": "Task timed out"}
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "failed",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "test_output": "{}",
            "error_info": json.dumps(error_info_data),
        }

        result = AttemptResponse.model_validate(data)

        assert isinstance(result.error_info, dict)
        assert result.error_info is not None
        assert result.error_info["code"] == "TIMEOUT"
        assert result.error_info["message"] == "Task timed out"

    def test_attempt_response_passes_through_error_info_when_already_dict(self) -> None:
        """GIVEN error_info as native Python dict WHEN constructing AttemptResponse THEN value passes through unchanged."""
        error_info_dict = {"error": "something went wrong"}
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "failed",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "test_output": {},
            "error_info": error_info_dict,
        }

        result = AttemptResponse.model_validate(data)

        assert result.error_info == error_info_dict

    def test_attempt_response_works_with_from_attributes_true(self) -> None:
        """GIVEN an object with attributes WHEN using model_validate with from_attributes THEN fields are mapped."""

        class MockORMAttempt:
            id = "attempt-orm-1"
            task_id = "task-orm-1"
            attempt_number = 3
            status = "success"
            started_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
            finished_at = datetime(2024, 6, 1, 12, 5, 0, tzinfo=timezone.utc)
            test_output = '{"tests": 15}'
            error_info = None

        result = AttemptResponse.model_validate(MockORMAttempt(), from_attributes=True)

        assert result.id == "attempt-orm-1"
        assert result.task_id == "task-orm-1"
        assert result.attempt_number == 3
        assert result.test_output == {"tests": 15}
        assert result.error_info is None


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response_exposes_required_fields(self) -> None:
        """GIVEN error_code and message WHEN constructing ErrorResponse THEN fields are exposed correctly."""
        data = {
            "error_code": "TASK_NOT_FOUND",
            "message": "The requested task does not exist",
            "details": None,
        }

        result = ErrorResponse.model_validate(data)

        assert result.error_code == "TASK_NOT_FOUND"
        assert result.message == "The requested task does not exist"
        assert result.details is None

    def test_error_response_accepts_optional_details_dict(self) -> None:
        """GIVEN details as a dict WHEN constructing ErrorResponse THEN details is available."""
        details_data = {"task_id": "task-123", "attempted_action": "delete"}
        data = {
            "error_code": "PERMISSION_DENIED",
            "message": "You do not have permission to perform this action",
            "details": details_data,
        }

        result = ErrorResponse.model_validate(data)

        assert result.details is not None
        assert result.details["task_id"] == "task-123"
        assert result.details["attempted_action"] == "delete"

    def test_error_response_serializes_to_expected_json_structure(self) -> None:
        """GIVEN an ErrorResponse WHEN serializing to JSON THEN expected structure is produced."""
        data = {
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid input provided",
            "details": {"field": "name", "reason": "too short"},
        }

        result = ErrorResponse.model_validate(data)
        json_output = result.model_dump()

        assert json_output == {
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid input provided",
            "details": {"field": "name", "reason": "too short"},
        }

    def test_error_response_serializes_to_json_string(self) -> None:
        """GIVEN an ErrorResponse WHEN serializing to JSON string THEN valid JSON is produced."""
        data = {
            "error_code": "SERVER_ERROR",
            "message": "Internal server error",
            "details": None,
        }

        result = ErrorResponse.model_validate(data)
        json_str = result.model_dump_json()

        parsed = json.loads(json_str)
        assert parsed["error_code"] == "SERVER_ERROR"
        assert parsed["message"] == "Internal server error"
        assert parsed["details"] is None

    def test_error_response_details_defaults_to_none(self) -> None:
        """GIVEN only error_code and message WHEN constructing ErrorResponse THEN details defaults to None."""
        data = {
            "error_code": "NOT_FOUND",
            "message": "Resource not found",
        }

        result = ErrorResponse.model_validate(data)

        assert result.details is None


class TestSSEEventData:
    """Tests for SSEEventData model."""

    def test_sse_event_data_can_be_constructed(self) -> None:
        """GIVEN valid SSE event data WHEN constructing SSEEventData THEN model is created."""
        data = {
            "event": "task_status",
            "data": {"task_id": "task-123", "status": "completed"},
        }

        result = SSEEventData.model_validate(data)

        assert result.event == "task_status"
        assert result.data["task_id"] == "task-123"

    def test_sse_event_data_serializes_correctly(self) -> None:
        """GIVEN an SSEEventData WHEN serializing THEN expected structure is produced."""
        data = {
            "event": "progress",
            "data": {"percent": 75, "message": "Processing..."},
        }

        result = SSEEventData.model_validate(data)
        output = result.model_dump()

        assert output["event"] == "progress"
        assert output["data"]["percent"] == 75


class TestEdgeCases:
    """Edge case tests for response models."""

    def test_task_response_with_deeply_nested_subtasks(self) -> None:
        """GIVEN deeply nested subtasks structure WHEN constructing TaskResponse THEN it deserializes correctly."""
        nested_subtasks = [
            {
                "id": "sub-1",
                "children": [
                    {"id": "sub-1-1", "metadata": {"level": 2}},
                    {"id": "sub-1-2", "metadata": {"level": 2}},
                ],
            }
        ]
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": json.dumps(nested_subtasks),
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        assert result.subtasks[0]["children"][0]["id"] == "sub-1-1"
        assert result.subtasks[0]["children"][1]["metadata"]["level"] == 2

    def test_task_response_with_unicode_in_json_fields(self) -> None:
        """GIVEN Unicode content in JSON fields WHEN constructing TaskResponse THEN it deserializes correctly."""
        data = {
            "id": "task-123",
            "spec": "Test spec with emoji",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": json.dumps([{"name": "Task with emoji"}]),
            "config": json.dumps({"description": "Config with special chars: <>"}),
        }

        result = TaskResponse.model_validate(data)

        assert result.subtasks[0]["name"] == "Task with emoji"
        assert result.config["description"] == "Config with special chars: <>"

    def test_attempt_response_with_large_test_output(self) -> None:
        """GIVEN large test_output JSON WHEN constructing AttemptResponse THEN it deserializes correctly."""
        large_output = {
            "tests": [{"name": f"test_{i}", "passed": i % 2 == 0} for i in range(100)]
        }
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "completed",
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "test_output": json.dumps(large_output),
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        assert len(result.test_output["tests"]) == 100
        assert result.test_output["tests"][0]["name"] == "test_0"
        assert result.test_output["tests"][99]["name"] == "test_99"

    def test_task_response_subtasks_null_json_string(self) -> None:
        """GIVEN 'null' as JSON string for subtasks WHEN constructing TaskResponse THEN it is handled appropriately."""
        data = {
            "id": "task-123",
            "spec": "Test spec",
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "subtasks": "null",
            "config": "{}",
        }

        result = TaskResponse.model_validate(data)

        # null JSON deserializes to None; implementation may convert to empty list or keep as None
        assert result.subtasks is None or result.subtasks == []

    def test_attempt_response_test_output_null_json_string(self) -> None:
        """GIVEN 'null' as JSON string for test_output WHEN constructing AttemptResponse THEN it is handled appropriately."""
        data = {
            "id": "attempt-456",
            "task_id": "task-123",
            "attempt_number": 1,
            "status": "pending",
            "started_at": datetime.now(timezone.utc),
            "finished_at": None,
            "test_output": "null",
            "error_info": None,
        }

        result = AttemptResponse.model_validate(data)

        # null JSON deserializes to None; implementation may convert to empty dict or keep as None
        assert result.test_output is None or result.test_output == {}
