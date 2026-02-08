"""Tests for API request/query models with Pydantic validation."""

import uuid

import pytest
from pydantic import ValidationError

from src.tdd_orchestrator.api.models.requests import (
    CircuitResetRequest,
    TaskFilterParams,
    TaskRetryRequest,
)


class TestTaskFilterParams:
    """Tests for TaskFilterParams query model."""

    def test_valid_params_with_all_fields(self) -> None:
        """TaskFilterParams with valid parameters produces correct attributes."""
        params = TaskFilterParams(status="pending", limit=10, offset=0)

        assert params.status == "pending"
        assert params.limit == 10
        assert params.offset == 0

    def test_valid_params_with_different_status_values(self) -> None:
        """TaskFilterParams accepts all valid status enum values."""
        valid_statuses = ["pending", "running", "completed", "failed"]

        for status in valid_statuses:
            params = TaskFilterParams(status=status, limit=50, offset=5)
            assert params.status == status

    def test_defaults_applied_for_omitted_optional_fields(self) -> None:
        """TaskFilterParams applies sensible defaults for omitted fields."""
        params = TaskFilterParams()

        assert params.status is None or isinstance(params.status, str)
        assert params.limit is not None
        assert params.limit >= 1
        assert params.offset is not None
        assert params.offset >= 0

    def test_invalid_status_raises_validation_error(self) -> None:
        """TaskFilterParams rejects status not in allowed enum set."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFilterParams(status="invalid_status", limit=10, offset=0)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "status" in field_names

    def test_limit_below_minimum_raises_validation_error(self) -> None:
        """TaskFilterParams rejects limit < 1."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFilterParams(status="pending", limit=0, offset=0)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "limit" in field_names

    def test_limit_above_maximum_raises_validation_error(self) -> None:
        """TaskFilterParams rejects limit > 100."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFilterParams(status="pending", limit=101, offset=0)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "limit" in field_names

    def test_negative_offset_raises_validation_error(self) -> None:
        """TaskFilterParams rejects offset < 0."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFilterParams(status="pending", limit=10, offset=-1)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "offset" in field_names

    def test_limit_boundary_values_accepted(self) -> None:
        """TaskFilterParams accepts limit at boundaries (1 and 100)."""
        params_min = TaskFilterParams(limit=1)
        params_max = TaskFilterParams(limit=100)

        assert params_min.limit == 1
        assert params_max.limit == 100

    def test_offset_zero_accepted(self) -> None:
        """TaskFilterParams accepts offset of 0."""
        params = TaskFilterParams(offset=0)

        assert params.offset == 0

    def test_rejects_extra_fields(self) -> None:
        """TaskFilterParams rejects unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFilterParams(status="pending", limit=10, offset=0, unknown_field=1)

        errors = exc_info.value.errors()
        assert len(errors) >= 1


class TestTaskRetryRequest:
    """Tests for TaskRetryRequest model."""

    def test_valid_task_id_string(self) -> None:
        """TaskRetryRequest with valid task_id string produces valid model."""
        request = TaskRetryRequest(task_id="abc123")

        assert request.task_id == "abc123"

    def test_valid_task_id_uuid(self) -> None:
        """TaskRetryRequest with valid UUID task_id produces valid model."""
        task_uuid = str(uuid.uuid4())
        request = TaskRetryRequest(task_id=task_uuid)

        assert request.task_id == task_uuid

    def test_max_retries_default_value(self) -> None:
        """TaskRetryRequest falls back to sensible default for max_retries."""
        request = TaskRetryRequest(task_id="abc123")

        assert request.max_retries is not None
        assert request.max_retries == 3

    def test_valid_max_retries_positive_int(self) -> None:
        """TaskRetryRequest accepts positive max_retries."""
        request = TaskRetryRequest(task_id="abc123", max_retries=5)

        assert request.max_retries == 5

    def test_max_retries_zero_raises_validation_error(self) -> None:
        """TaskRetryRequest rejects max_retries=0."""
        with pytest.raises(ValidationError) as exc_info:
            TaskRetryRequest(task_id="abc123", max_retries=0)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "max_retries" in field_names

    def test_max_retries_negative_raises_validation_error(self) -> None:
        """TaskRetryRequest rejects negative max_retries."""
        with pytest.raises(ValidationError) as exc_info:
            TaskRetryRequest(task_id="abc123", max_retries=-1)

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "max_retries" in field_names

    def test_empty_task_id_raises_validation_error(self) -> None:
        """TaskRetryRequest rejects empty task_id."""
        with pytest.raises(ValidationError) as exc_info:
            TaskRetryRequest(task_id="")

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "task_id" in field_names

    def test_whitespace_task_id_raises_validation_error(self) -> None:
        """TaskRetryRequest rejects whitespace-only task_id."""
        with pytest.raises(ValidationError) as exc_info:
            TaskRetryRequest(task_id="   ")

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "task_id" in field_names

    def test_rejects_extra_fields(self) -> None:
        """TaskRetryRequest rejects unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            TaskRetryRequest(task_id="abc", unknown_field=1)

        errors = exc_info.value.errors()
        assert len(errors) >= 1


class TestCircuitResetRequest:
    """Tests for CircuitResetRequest model."""

    def test_valid_service_name(self) -> None:
        """CircuitResetRequest with valid service_name produces valid model."""
        request = CircuitResetRequest(service_name="payment-service")

        assert request.service_name == "payment-service"

    def test_reason_defaults_to_none(self) -> None:
        """CircuitResetRequest reason defaults to None when omitted."""
        request = CircuitResetRequest(service_name="auth-service")

        assert request.reason is None

    def test_reason_accepts_string(self) -> None:
        """CircuitResetRequest accepts any string for reason."""
        request = CircuitResetRequest(
            service_name="cache-service", reason="Manual reset after deployment"
        )

        assert request.reason == "Manual reset after deployment"

    def test_empty_service_name_raises_validation_error(self) -> None:
        """CircuitResetRequest rejects empty service_name."""
        with pytest.raises(ValidationError) as exc_info:
            CircuitResetRequest(service_name="")

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "service_name" in field_names

    def test_whitespace_service_name_raises_validation_error(self) -> None:
        """CircuitResetRequest rejects whitespace-only service_name."""
        with pytest.raises(ValidationError) as exc_info:
            CircuitResetRequest(service_name="   ")

        errors = exc_info.value.errors()
        field_names = [err["loc"][0] for err in errors]
        assert "service_name" in field_names

    def test_rejects_extra_fields(self) -> None:
        """CircuitResetRequest rejects unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            CircuitResetRequest(service_name="my-service", unknown_field=1)

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_reason_with_empty_string_accepted(self) -> None:
        """CircuitResetRequest accepts empty string for reason field."""
        request = CircuitResetRequest(service_name="my-service", reason="")

        assert request.reason == ""

    def test_service_name_with_special_characters(self) -> None:
        """CircuitResetRequest accepts service_name with valid special characters."""
        request = CircuitResetRequest(service_name="my-service_v2.0")

        assert request.service_name == "my-service_v2.0"
